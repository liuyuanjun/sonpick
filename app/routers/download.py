from datetime import datetime, timezone
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Task
from app.routers.auth import get_current_user
from app.schemas import BatchDownloadRequest, DownloadRequest
from app.services.task_worker import worker

router = APIRouter(prefix="/download", tags=["download"])


@router.post("")
def download(req: DownloadRequest, user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    task = Task(
        type="search_download",
        status="pending",
        payload_json=json.dumps({
            "keyword": req.keyword,
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
