from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import OperationLog
from app.routers.auth import get_current_user
from app.schemas import OperationLogOut

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("", response_model=list[OperationLogOut])
def list_logs(
    action: str | None = Query(None, description="download/upload/delete/convert"),
    status: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(OperationLog)
    if action:
        query = query.filter(OperationLog.action == action)
    if status:
        query = query.filter(OperationLog.status == status)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (OperationLog.title.ilike(like))
            | (OperationLog.message.ilike(like))
            | (OperationLog.local_path.ilike(like))
            | (OperationLog.remote_path.ilike(like))
        )
    rows = (
        query.order_by(desc(OperationLog.id))
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [OperationLogOut(**row.to_dict()) for row in rows]


@router.delete("")
def clear_logs(
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    count = db.query(OperationLog).delete()
    db.commit()
    return {"deleted": count}
