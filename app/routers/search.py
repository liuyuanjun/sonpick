import json
import queue
import threading
import time
from typing import Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.routers.auth import get_current_user
from app.routers.tasks import _auth_user
from app.schemas import LibraryMatchOut, SearchPageOut, SearchResultItem
from app.services.library_match_service import match_search_results
from app.services.musicdl_service import (
    DEFAULT_DOWNLOAD_SOURCES,
    SOURCE_LABELS,
    MusicDLService,
    SearchCancelled,
)

router = APIRouter(prefix="/search", tags=["search"])

_HEARTBEAT_SECONDS = 5


def _build_search_page(
    q: str,
    page: int,
    page_size: int,
    source: str,
    db: Session,
    on_event: Optional[Callable[[dict], None]] = None,
    cancelled=None,
) -> SearchPageOut:
    """执行搜索并组装分页结果；on_event 非空时逐源推送进度事件。"""
    service = MusicDLService(db)
    requested_source = (source or "all").strip()
    music_sources = None if requested_source == "all" else [requested_source]
    if music_sources and requested_source not in DEFAULT_DOWNLOAD_SOURCES:
        raise HTTPException(status_code=422, detail="不支持的音乐源")
    source_label = SOURCE_LABELS.get(requested_source, requested_source)
    try:
        items = service.search(
            q,
            music_sources=music_sources,
            on_event=on_event,
            cancelled=cancelled,
        )
    except SearchCancelled:
        raise
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
                song_id=str(getattr(item, "song_id", "") or "") or None,
            )
        )
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
    return SearchPageOut(
        items=out_items,
        total=total,
        page=page,
        page_size=page_size,
    )


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


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
        return _build_search_page(q, page, page_size, source, db)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stream")
def search_stream(
    request: Request,
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source: str = Query("all"),
    token: Optional[str] = Query(None, description="JWT；EventSource 无法设 Header 时用 query"),
):
    """SSE 搜索：逐源推送 progress/heartbeat 事件，最终以 result/error 收尾。

    搜索在后台线程执行并持有独立 DB 会话；客户端断开后通过 cancelled
    事件在重试边界取消后续尝试（进行中的 HTTP 请求无法强杀）。
    """
    auth = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    bearer = None
    if auth.lower().startswith("bearer "):
        bearer = auth.split(" ", 1)[1].strip()
    _auth_user(credentials_token=bearer, query_token=token)

    events: queue.Queue = queue.Queue()
    cancelled = threading.Event()
    done = object()

    def run_search():
        db = SessionLocal()
        try:
            page_out = _build_search_page(
                q, page, page_size, source, db,
                on_event=events.put,
                cancelled=cancelled,
            )
            events.put({"type": "result", "data": page_out.model_dump(mode="json")})
        except SearchCancelled:
            pass
        except HTTPException as exc:
            events.put({"type": "error", "message": str(exc.detail)})
        except Exception as exc:
            events.put({"type": "error", "message": f"搜索失败：{exc}"})
        finally:
            db.close()
            events.put(done)

    def event_gen():
        threading.Thread(target=run_search, daemon=True).start()
        started = time.monotonic()
        pending: list[str] = []
        try:
            while True:
                try:
                    ev = events.get(timeout=_HEARTBEAT_SECONDS)
                except queue.Empty:
                    yield _sse({
                        "type": "heartbeat",
                        "elapsed": int(time.monotonic() - started),
                        "pending": list(pending),
                    })
                    continue
                if ev is done:
                    yield "event: end\ndata: {}\n\n"
                    break
                if ev.get("type") == "progress":
                    label = ev.get("label")
                    status = ev.get("status")
                    if status in ("start", "retry"):
                        if label and label not in pending:
                            pending.append(label)
                    elif status in ("done", "fail") and label in pending:
                        pending.remove(label)
                yield _sse(ev)
        finally:
            cancelled.set()

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
