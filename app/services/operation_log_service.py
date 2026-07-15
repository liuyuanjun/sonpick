import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import OperationLog


def write_log(
    db: Session,
    *,
    action: str,
    target: str = "file",
    status: str = "success",
    title: Optional[str] = None,
    message: Optional[str] = None,
    local_path: Optional[str] = None,
    remote_path: Optional[str] = None,
    song_id: Optional[int] = None,
    task_id: Optional[int] = None,
    detail: Optional[dict[str, Any]] = None,
    commit: bool = True,
) -> OperationLog:
    row = OperationLog(
        action=action,
        target=target,
        status=status,
        title=title,
        message=message,
        local_path=local_path,
        remote_path=remote_path,
        song_id=song_id,
        task_id=task_id,
        detail_json=json.dumps(detail or {}, ensure_ascii=False),
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row
