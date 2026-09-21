from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers.auth import get_current_user
from app.schemas import (
    LibraryMatchOut,
    ResolveOut,
    ResolveRequest,
    ResolvedFormatOut,
    SearchFormatOut,
    SearchPageOut,
    SearchResultItem,
)
from app.services.library_match_service import match_search_results
from app.services.light_search_service import (
    DEFAULT_DOWNLOAD_SOURCES,
    SOURCE_LABELS,
    LightSearchService,
)

router = APIRouter(prefix="/search", tags=["search"])


def _to_result_item(item) -> SearchResultItem:
    size = getattr(item, "file_size_bytes", None)
    formats = [
        SearchFormatOut(**f) for f in (getattr(item, "formats_meta", None) or []) if isinstance(f, dict)
    ]
    return SearchResultItem(
        song_name=item.song_name or "",
        singers=getattr(item, "singers", None),
        album=getattr(item, "album", None),
        ext=getattr(item, "ext", None),
        filesize=str(size) if size is not None else None,
        file_size=str(size) if size is not None else None,
        duration=getattr(item, "duration", None),
        source=getattr(item, "_sonpick_source", None) or getattr(item, "source", None),
        song_id=str(getattr(item, "identifier", "") or "") or None,
        formats=formats,
    )


@router.get("", response_model=SearchPageOut)
def search(
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source: str = Query("all"),
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """轻量搜索：每源一次请求，不解析下载地址（在 /search/resolve 按需验证）。

    `source` 支持逗号分隔的多源（如 `QQMusicClient,NeteaseMusicClient`），`all` 表示全部。
    """
    requested_source = (source or "all").strip()
    if requested_source == "all":
        music_sources = None
    else:
        music_sources = [s.strip() for s in requested_source.split(",") if s.strip()]
        invalid = [s for s in music_sources if s not in DEFAULT_DOWNLOAD_SOURCES]
        if invalid:
            raise HTTPException(status_code=422, detail=f"不支持的音乐源: {', '.join(invalid)}")
        if not music_sources:
            raise HTTPException(status_code=422, detail="请至少选择一个音乐源")
    try:
        items, errors = LightSearchService(db).search(q, music_sources=music_sources)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"搜索失败：{exc}") from exc
    if not items and errors:
        raise HTTPException(status_code=502, detail="音乐源搜索失败：" + "；".join(errors))
    total = len(items)
    start = (page - 1) * page_size
    page_items = items[start:start + page_size]
    out_items = [_to_result_item(it) for it in page_items]
    # 与本地曲库批量比对（Song + SongFile），一次性组装，避免 N+1
    matches = match_search_results(db, [
        {
            "song_name": it.song_name,
            "singers": it.singers,
            "album": it.album,
            "duration": it.duration,
            "song_id": it.song_id,
        }
        for it in out_items
    ])
    for it, match in zip(out_items, matches):
        if match:
            it.library_match = LibraryMatchOut(**match)
    return SearchPageOut(items=out_items, total=total, page=page, page_size=page_size)


@router.post("/resolve", response_model=ResolveOut)
def resolve(req: ResolveRequest, user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    """单曲格式验证：对锁定的一首歌并行验证三档格式（官方接口 + 链接探测）。

    返回「已验证可下」的格式列表，供前端在确认弹窗里展示；为空不代表不能下，
    前端仍可直接入队，由 worker 按原有链路尝试。
    """
    service = LightSearchService(db)
    item = service.find_item(req.q, req.source, req.song_id)
    if item is None:
        raise HTTPException(status_code=404, detail="未找到该歌曲，请重新搜索后再试")
    formats = service.resolve_formats(item)
    return ResolveOut(
        song_name=item.song_name or "",
        singers=getattr(item, "singers", None),
        album=getattr(item, "album", None),
        duration=getattr(item, "duration", None),
        formats=[ResolvedFormatOut(**f) for f in formats],
        default_tier=formats[0]["tier"] if formats else None,
    )
