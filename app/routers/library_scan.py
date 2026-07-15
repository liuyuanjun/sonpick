from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers.auth import get_current_user
from app.schemas import LibraryScanRequest, LibraryScanResponse
from app.services.library_scan_service import LibraryScanService

router = APIRouter(prefix="/library", tags=["library-scan"])

_last_scan: dict | None = None


@router.post("/scan", response_model=LibraryScanResponse)
def scan_library(
    req: LibraryScanRequest | None = None,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """同步扫描本地 / WebDAV 曲库并入库。"""
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


@router.get("/scan/status")
def scan_status(user: str = Depends(get_current_user)):
    return {
        "running": False,
        "last": _last_scan,
    }
