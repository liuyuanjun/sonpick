from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.models import Task
from app.routers.auth import get_current_user
from app.schemas import TaskOut
from app.security import decode_token
from app.services.task_worker import task_event_hub

router = APIRouter(prefix="/tasks", tags=["tasks"])

_TERMINAL = {"completed", "failed", "cancelled"}


def _auth_user(credentials_token: Optional[str] = None, query_token: Optional[str] = None) -> str:
    token = credentials_token or query_token
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        payload = decode_token(token)
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(status_code=401, detail="Invalid token")
        return str(sub)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.get("", response_model=list[TaskOut])
def list_tasks(
    status: Optional[str] = Query(None),
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Task)
    if status:
        q = q.filter(Task.status == status)
    tasks = q.order_by(Task.id.desc()).limit(200).all()
    return [TaskOut(**t.to_dict()) for t in tasks]


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: int, user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskOut(**task.to_dict())


@router.get("/{task_id}/events")
async def task_events(
    task_id: int,
    request: Request,
    token: Optional[str] = Query(None, description="JWT；EventSource 无法设 Header 时用 query"),
    db: Session = Depends(get_db),
):
    """SSE 推送任务进度。事件 data 为 TaskOut JSON。"""
    # Prefer Authorization header when present (fetch/stream clients)
    auth = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    bearer = None
    if auth.lower().startswith("bearer "):
        bearer = auth.split(" ", 1)[1].strip()
    _auth_user(credentials_token=bearer, query_token=token)

    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    async def event_gen():
        last_sig = None
        queue = task_event_hub.subscribe(task_id)
        try:
            # initial snapshot
            db0 = SessionLocal()
            try:
                t0 = db0.get(Task, task_id)
                if not t0:
                    yield f"event: error\ndata: {json.dumps({'detail': 'Task not found'}, ensure_ascii=False)}\n\n"
                    return
                data = t0.to_dict()
            finally:
                db0.close()
            last_sig = (data.get("status"), data.get("updated_at"), json.dumps(data.get("progress") or {}, sort_keys=True, ensure_ascii=False))
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
            if data.get("status") in _TERMINAL:
                yield "event: end\ndata: {}\n\n"
                return

            while True:
                if await request.is_disconnected():
                    break
                payload = None
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=12.0)
                except asyncio.TimeoutError:
                    # keepalive + DB refresh in case we missed an in-process event
                    db1 = SessionLocal()
                    try:
                        t1 = db1.get(Task, task_id)
                        if t1:
                            payload = t1.to_dict()
                    finally:
                        db1.close()
                    yield ": keepalive\n\n"
                    if not payload:
                        continue

                if not isinstance(payload, dict):
                    continue
                # if payload is partial, reload full task
                if "id" not in payload or "status" not in payload:
                    db2 = SessionLocal()
                    try:
                        t2 = db2.get(Task, task_id)
                        if t2:
                            payload = t2.to_dict()
                        else:
                            continue
                    finally:
                        db2.close()

                sig = (
                    payload.get("status"),
                    payload.get("updated_at"),
                    json.dumps(payload.get("progress") or {}, sort_keys=True, ensure_ascii=False),
                )
                if sig != last_sig:
                    last_sig = sig
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                if payload.get("status") in _TERMINAL:
                    yield "event: end\ndata: {}\n\n"
                    break
        finally:
            task_event_hub.unsubscribe(task_id, queue)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/{task_id}")
def delete_task(task_id: int, user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = "cancelled"
    task.updated_at = datetime.now(timezone.utc)
    db.commit()
    # notify SSE listeners
    try:
        from app.services.task_worker import worker
        if worker.loop:
            task_event_hub.publish_threadsafe(task_id, task.to_dict(), worker.loop)
    except Exception:
        pass
    return {"ok": True}
