from datetime import datetime, timezone
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Song, SongFile, Task
from app.routers.auth import get_current_user
from app.schemas import BatchDownloadRequest, DownloadRequest
from app.services.task_worker import worker

router = APIRouter(prefix="/download", tags=["download"])


def _validate_duplicate_decision(req: DownloadRequest, db: Session) -> None:
    """校验曲库重复决策字段；worker 执行前还会再次核对 SongFile。"""
    action = req.duplicate_action
    if not action:
        return
    if action == "replace":
        if not req.replace_song_file_id:
            raise HTTPException(status_code=422, detail="replace 需要提供 replace_song_file_id")
        sf = db.get(SongFile, req.replace_song_file_id)
        if not sf:
            raise HTTPException(status_code=422, detail="要替换的曲库版本不存在")
        if req.matched_song_id and sf.song_id != req.matched_song_id:
            raise HTTPException(status_code=422, detail="要替换的版本不属于匹配的曲库歌曲")
        if not sf.local_path:
            raise HTTPException(status_code=422, detail="远端版本暂不支持替换")
        if not Path(sf.local_path).is_file():
            raise HTTPException(status_code=422, detail="要替换的本地文件已不可访问")
    elif action == "keep_both":
        if req.matched_song_id and not db.get(Song, req.matched_song_id):
            raise HTTPException(status_code=422, detail="匹配的曲库歌曲不存在")


@router.post("")
def download(req: DownloadRequest, user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    _validate_duplicate_decision(req, db)
    task = Task(
        type="search_download",
        status="pending",
        payload_json=json.dumps({
            "keyword": req.keyword,
            "prefer": req.prefer,
            "source": req.source,
            "duplicate_action": req.duplicate_action,
            "replace_song_file_id": req.replace_song_file_id,
            "matched_song_id": req.matched_song_id,
        }),
        progress_json=json.dumps({"message": "等待执行", "percent": 0}),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    worker.enqueue(task.id)
    return {"task_id": task.id}


@router.post("/batch")
def batch_download(req: BatchDownloadRequest, user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    keywords = [line.strip() for line in (req.content or "").splitlines() if line.strip()]
    if not keywords:
        raise HTTPException(status_code=400, detail="歌单为空，请每行填写一首歌曲")
    task = Task(
        type="batch_download",
        status="pending",
        payload_json=json.dumps({
            "keywords": keywords,
            "prefer": req.prefer,
            "source": req.source,
        }),
        progress_json=json.dumps({"message": "等待执行", "percent": 0}),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    worker.enqueue(task.id)
    return {"task_id": task.id}
