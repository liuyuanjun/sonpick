from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers.auth import get_current_user
from app.schemas import SearchPageOut, SearchResultItem
from app.services.musicdl_service import MusicDLService

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchPageOut)
def search(
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        service = MusicDLService(db)
        items = service.search(q)
        total = len(items)
        start = (page - 1) * page_size
        end = start + page_size
        page_items = items[start:end]
        out_items = []
        for item in page_items:
            size = getattr(item, "file_size", None) or getattr(item, "filesize", None)
            out_items.append(
                SearchResultItem(
                    song_name=item.song_name or "",
                    singers=getattr(item, "singers", None),
                    album=getattr(item, "album", None),
                    ext=getattr(item, "ext", None),
                    filesize=str(size) if size is not None else None,
                    file_size=str(size) if size is not None else None,
                    duration=getattr(item, "duration", None),
                    source=getattr(item, "source", None),
                )
            )
        return SearchPageOut(
            items=out_items,
            total=total,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
