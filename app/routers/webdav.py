from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers.auth import get_current_user
from app.services.webdav_service import WebDAVService

router = APIRouter(prefix="/webdav", tags=["webdav"])


@router.get("/list")
def list_webdav(
    path: str = Query(""),
    source_id: int | None = Query(None),
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        service = WebDAVService(db, source_id=source_id)
        return service.list(path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/item")
def delete_webdav_item(
    path: str = Query(...),
    source_id: int | None = Query(None),
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        service = WebDAVService(db, source_id=source_id)
        return service.delete(path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"删除失败: {e}")


@router.get("/stream")
async def stream_webdav(
    request: Request,
    path: str = Query(...),
    source_id: int | None = Query(None),
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        service = WebDAVService(db, source_id=source_id)
        range_header = request.headers.get("range")
        return await service.stream(path, range_header)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
