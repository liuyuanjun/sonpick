from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers.auth import get_current_user
from app.schemas import SearchPageOut, SearchResultItem
from app.services.musicdl_service import DEFAULT_DOWNLOAD_SOURCES, SOURCE_LABELS, MusicDLService

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchPageOut)
def search(
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source: str = Query("all"),
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        service = MusicDLService(db)
        requested_source = (source or "all").strip()
        music_sources = None if requested_source == "all" else [requested_source]
        if music_sources and requested_source not in DEFAULT_DOWNLOAD_SOURCES:
            raise HTTPException(status_code=422, detail="不支持的音乐源")
        source_label = SOURCE_LABELS.get(requested_source, requested_source)
        try:
            items = service.search(q, music_sources=music_sources)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"{source_label} 搜索失败：{exc}") from exc
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
