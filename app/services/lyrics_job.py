"""严格串行执行批量歌词获取任务。"""
from __future__ import annotations

import time
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models import Song
from app.services.lrclib_provider import LrclibRateLimitError
from app.services.lyrics_search_service import LyricsApplicationError, LyricsSearchService
from app.services.operation_log_service import write_log


def run_lyrics_job(
    db: Session,
    *,
    song_ids: list[int] | None = None,
    source_id: str = "auto",
    only_missing: bool = True,
    overwrite: bool = False,
    write_file_tags: bool = True,
    library_source_id: int | None = None,
    emit: Callable[[str, int], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    query = db.query(Song)
    if song_ids:
        query = query.filter(Song.id.in_(sorted(set(song_ids))))
    if library_source_id is not None:
        query = query.filter(Song.library_source_id == library_source_id)
    songs = query.order_by(Song.id.asc()).all()
    stats = {
        "total": len(songs),
        "processed": 0,
        "matched": 0,
        "written": 0,
        "instrumental": 0,
        "skipped_existing": 0,
        "not_found": 0,
        "rate_limit_waits": 0,
        "failed": 0,
    }
    items: list[dict[str, Any]] = []
    service = LyricsSearchService(db)

    def progress(message: str, percent: int) -> None:
        if emit:
            emit(message, percent)

    for index, song in enumerate(songs, start=1):
        if is_cancelled and is_cancelled():
            return {"ok": False, "cancelled": True, **stats, "items": items}
        percent = int((index - 1) / max(len(songs), 1) * 100)
        progress(f"正在检索歌词 {index}/{len(songs)}：{song.title}", percent)
        try:
            current = service.current_lyrics(song)
            has_current = bool(current.get("has_lyrics") or current.get("instrumental"))
            if has_current and (only_missing or not overwrite):
                stats["skipped_existing"] += 1
                items.append({"song_id": song.id, "status": "skipped_existing"})
                continue
            result = service.search(song, source=source_id or "auto", limit=20)
            for error in result.get("errors", []):
                if error.get("code") == "rate_limited":
                    stats["rate_limit_waits"] += 1
                    progress(f"触发来源限流，等待 {error.get('retry_after', 0)} 秒", percent)
            candidates = result.get("candidates") or []
            if not candidates:
                stats["not_found"] += 1
                items.append({"song_id": song.id, "status": "not_found"})
                continue
            candidate = candidates[0]
            stats["matched"] += 1
            if not (candidate.get("synced_lyrics") or candidate.get("plain_lyrics") or candidate.get("instrumental")):
                candidate = service.details(candidate.get("source", ""), candidate.get("source_id", ""), candidate)
            if is_cancelled and is_cancelled():
                return {"ok": False, "cancelled": True, **stats, "items": items}
            applied = service.apply(song, candidate, write_file_tags=write_file_tags)
            stats["written"] += 1
            if applied.get("lyrics_type") == "instrumental":
                stats["instrumental"] += 1
            items.append({
                "song_id": song.id,
                "status": "written",
                "source": applied.get("source"),
                "source_id": applied.get("source_id"),
                "lyrics_type": applied.get("lyrics_type"),
                "score": candidate.get("score"),
            })
            write_log(
                db,
                action="lyrics",
                target="local",
                status="success",
                title=f"{song.artist or ''} - {song.title}".strip(" -"),
                message=f"已获取{applied.get('lyrics_type') or '歌词'}",
                local_path=applied.get("lrc_path"),
                song_id=song.id,
                detail={
                    "source": applied.get("source"),
                    "source_id": applied.get("source_id"),
                    "lyrics_type": applied.get("lyrics_type"),
                    "score": candidate.get("score"),
                },
                commit=False,
            )
            db.commit()
        except LrclibRateLimitError as exc:
            stats["rate_limit_waits"] += 1
            progress(f"触发来源限流，等待 {exc.retry_after} 秒", percent)
            time.sleep(min(60, max(1, exc.retry_after)))
            stats["failed"] += 1
            items.append({"song_id": song.id, "status": "failed", "error": {"code": "rate_limited", "message": str(exc), "retry_after": exc.retry_after}})
        except LyricsApplicationError as exc:
            if exc.code == "lyrics_not_found":
                stats["not_found"] += 1
                items.append({"song_id": song.id, "status": "not_found"})
            else:
                stats["failed"] += 1
                items.append({"song_id": song.id, "status": "failed", "error": exc.detail()})
            db.rollback()
        except Exception as exc:
            stats["failed"] += 1
            items.append({"song_id": song.id, "status": "failed", "error": {"code": "lyrics_error", "message": str(exc)}})
            db.rollback()
        finally:
            stats["processed"] += 1
            progress(f"歌词任务进度 {stats['processed']}/{stats['total']}", int(index / max(len(songs), 1) * 100))

    result = {"ok": stats["failed"] == 0, **stats, "items": items[:200]}
    progress(
        f"歌词任务完成：写入 {stats['written']}，纯音乐 {stats['instrumental']}，未命中 {stats['not_found']}，失败 {stats['failed']}",
        100,
    )
    return result
