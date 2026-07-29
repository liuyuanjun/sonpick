from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Task
from app.routers.auth import get_current_user
from app.schemas import CleanupPreviewOut, LibraryScanRequest
from app.services.library_cleanup_service import LibraryCleanupService
from app.services.library_scan_service import LibraryScanService

router = APIRouter(prefix="/library", tags=["library-scan"])

_last_scan: dict | None = None


@router.post("/scan")
def scan_library(
    req: LibraryScanRequest | None = None,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """异步扫描本地 / WebDAV 曲库并入库，立即返回 task_id。"""
    body = req or LibraryScanRequest()
    source = body.source or "all"
    if body.all:
        source = "all"
    payload = {
        "source": source,
        "source_ids": body.source_ids,
    }
    task = Task(
        type="scan",
        status="pending",
        payload_json=json.dumps(payload, ensure_ascii=False),
        progress_json=json.dumps({"percent": 0, "message": "等待扫描..."}, ensure_ascii=False),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return {
        "task_id": task.id,
        "status": "pending",
        "message": "扫描任务已创建",
        "source": source,
        "source_ids": body.source_ids,
    }


@router.get("/scan/status")
def scan_status(user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    running = (
        db.query(Task)
        .filter(Task.type == "scan", Task.status.in_(["pending", "running"]))
        .order_by(Task.id.desc())
        .first()
    )
    last_completed = (
        db.query(Task)
        .filter(Task.type == "scan", Task.status.in_(["completed", "failed", "cancelled"]))
        .order_by(Task.id.desc())
        .first()
    )
    last = None
    if last_completed and last_completed.result_json:
        try:
            last = json.loads(last_completed.result_json)
        except Exception:
            last = {"task_id": last_completed.id, "status": last_completed.status}
    elif _last_scan is not None:
        last = _last_scan
    return {
        "running": running is not None,
        "running_task_id": running.id if running else None,
        "last": last,
    }


@router.post("/scan/sync")
def scan_library_sync(
    req: LibraryScanRequest | None = None,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """兼容旧同步调用（调试用）。"""
    global _last_scan
    body = req or LibraryScanRequest()
    try:
        source = body.source or "all"
        if body.all:
            source = "all"
        result = LibraryScanService(db).scan(source, source_ids=body.source_ids)
        _last_scan = result
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"扫描失败: {e}")


@router.post("/cleanup/preview", response_model=CleanupPreviewOut)
def cleanup_preview(user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    """分析"全部版本失效"的死 Song，分类为可恢复 / 可清理 / 存储不可达。"""
    try:
        return CleanupPreviewOut(**LibraryCleanupService(db).analyze())
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"分析失败: {type(e).__name__}: {e}")


@router.post("/cleanup")
def cleanup_library(user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    """创建异步清理任务：恢复误标失效的记录，删除确认失联的死 Song（仅删记录，不动磁盘）。"""
    running = (
        db.query(Task)
        .filter(Task.type == "cleanup", Task.status.in_(["pending", "running"]))
        .first()
    )
    if running:
        return {"task_id": running.id, "status": running.status, "message": "已有清理任务在进行中"}
    task = Task(
        type="cleanup",
        status="pending",
        payload_json=json.dumps({}, ensure_ascii=False),
        progress_json=json.dumps({"percent": 0, "message": "等待清理..."}, ensure_ascii=False),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return {"task_id": task.id, "status": "pending", "message": "清理任务已创建"}
