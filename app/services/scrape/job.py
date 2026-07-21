"""Async scrape job execution: fill DB + optional write tags/cover."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from app.models import Song
from app.services.library_layout import is_generic_dir_name
from app.services.media_meta_service import is_local_file, read_audio_duration, resolve_song_meta, write_audio_tags
from app.services.operation_log_service import write_log
from app.services.song_file_resolver import NoPlayableSongFileError, SongFileResolver
from app.services.scrape import enrich_song_via_pipeline
from app.services.scrape.query_normalize import clean_artist, clean_title, looks_like_opaque_id, repair_shifted_meta, split_title_artist
from app.services.scrape.cache import cache_get, cache_put

log = logging.getLogger("sonpick.scrape")


def run_scrape_job(
    db: Session,
    *,
    source_id: int | None = None,
    song_ids: list[int] | None = None,
    allow_network: bool = True,
    overwrite: bool = False,
    write_file_tags: bool = True,
    limit: int = 20,
    emit: Optional[Callable[[str, int], None]] = None,
) -> dict[str, Any]:
    def _emit(msg: str, pct: int = 0):
        log.info("%s (%s%%)", msg, pct)
        if emit:
            try:
                emit(msg, pct)
            except Exception:
                pass

    q = db.query(Song)
    if source_id is not None:
        q = q.filter(Song.library_source_id == source_id)
    if song_ids:
        q = q.filter(Song.id.in_(song_ids))
    q = q.order_by(Song.id.asc())
    songs = q.limit(limit).all() if limit and limit > 0 else q.all()
    total = len(songs)
    updated = skipped = failed = 0
    details: list[dict[str, Any]] = []

    _emit(f"开始刮削 {total} 首", 1)
    for idx, song in enumerate(songs):
        pct = int((idx / max(total, 1)) * 100)
        try:
            if getattr(song, "meta_locked", False) and not overwrite:
                skipped += 1
                details.append({"song_id": song.id, "title": song.title, "status": "locked"})
                continue

            changes: dict[str, Any] = {}
            # 先修复字段串位 + 清洗 mid + 拆「画 赵雷」
            raw_title = (song.title or "").strip()
            raw_artist = (song.artist or "").strip() if song.artist else ""
            raw_album = (song.album or "").strip() if song.album else ""
            rt, ra, ral = repair_shifted_meta(raw_title, raw_artist, raw_album)
            if rt and rt != raw_title:
                song.title = rt
                changes["title"] = rt
            if ra and ra != raw_artist:
                song.artist = ra
                changes["artist"] = ra
            if ral != raw_album and raw_title and looks_like_opaque_id(raw_title):
                song.album = ral or None
                changes["album"] = song.album

            raw_title = (song.title or "").strip()
            raw_artist = (song.artist or "").strip() if song.artist else ""
            st, sa = split_title_artist(raw_title, raw_artist or None)
            if st and st != raw_title:
                song.title = st
                changes["title"] = st
            if sa and sa != raw_artist:
                song.artist = sa
                changes["artist"] = sa
            elif raw_artist:
                ca = clean_artist(raw_artist)
                if ca and ca != raw_artist:
                    song.artist = ca
                    changes["artist"] = ca
                elif looks_like_opaque_id(raw_artist) or is_generic_dir_name(raw_artist):
                    song.artist = None
                    changes["artist"] = None

            # local first
            try:
                local_file = SongFileResolver(db).resolve_local(song)
            except NoPlayableSongFileError:
                local_file = None
            meta = resolve_song_meta(
                song,
                audio_path=local_file.local_path if local_file else None,
                db=db,
                allow_network=False,
                force=overwrite,
            )
            for key in ("title", "artist", "album", "duration", "cover_path", "lrc_path"):
                val = meta.get(key)
                if not val:
                    continue
                if key in ("artist", "album") and is_generic_dir_name(str(val)):
                    continue
                cur = getattr(song, key, None)
                if overwrite or not cur or (key in ("artist", "album") and is_generic_dir_name(str(cur or ""))):
                    if str(cur or "") != str(val):
                        setattr(song, key, val)
                        changes[key] = val

            # 本地时长：从选中的 SongFile 读取
            if (not song.duration or int(song.duration or 0) <= 0) and local_file:
                local_dur = read_audio_duration(local_file.local_path)
                if local_dur and int(local_dur) > 0:
                    song.duration = int(local_dur)
                    changes["duration"] = song.duration
                    log.info("本地时长 song_id=%s duration=%ss", song.id, song.duration)

            if allow_network:
                # cache first
                cached = cache_get(db, song.title or "", song.artist, song.duration)
                if cached.get("album") and (overwrite or not song.album or is_generic_dir_name(str(song.album or ""))):
                    song.album = cached["album"]
                    changes["album"] = cached["album"]
                    if cached.get("artist") and (overwrite or not song.artist):
                        song.artist = cached["artist"]
                        changes["artist"] = cached["artist"]
                    if cached.get("duration") and (overwrite or not song.duration):
                        song.duration = int(cached["duration"])
                        changes["duration"] = song.duration
                    changes["provider"] = cached.get("provider") or "cache"
                    song.meta_provider = changes.get("provider")
                    song.meta_confidence = int(cached.get("score") or 60)
                else:
                    log.info(
                        "联网刮削 song_id=%s title=%r artist=%r album=%r duration=%s (local)",
                        song.id,
                        song.title,
                        song.artist,
                        song.album,
                        song.duration,
                    )
                    filled = enrich_song_via_pipeline(
                        song,
                        db=db,
                        timeout_per_provider=80.0,
                        total_timeout=160.0,
                    ) or {}
                    log.info("联网刮削结果 song_id=%s filled=%s", song.id, filled)
                    for key, val in list(filled.items()):
                        if key == "provider":
                            changes["provider"] = val
                            song.meta_provider = str(val)
                            continue
                        if val is not None:
                            changes[key] = val
                    if filled.get("album"):
                        cache_put(
                            db,
                            title=song.title or "",
                            artist=song.artist,
                            duration=song.duration,
                            album=filled.get("album"),
                            cover_url=filled.get("cover_url"),
                            provider=filled.get("provider"),
                            score=int(filled.get("score") or 50),
                            payload=filled,
                        )
                        song.meta_confidence = int(filled.get("score") or 50)

            # cleanup generic
            if song.artist and is_generic_dir_name(song.artist):
                song.artist = None
                changes["artist"] = None
            if song.album and is_generic_dir_name(song.album):
                song.album = None
                changes["album"] = None

            # write embedded tags for the selected local SongFile
            if write_file_tags and local_file:
                lyrics_path = local_file.lrc_path or song.lrc_path
                lyrics_text = None
                if lyrics_path and Path(str(lyrics_path)).is_file():
                    try:
                        lyrics_text = Path(str(lyrics_path)).read_text(encoding="utf-8", errors="ignore")
                    except Exception:
                        lyrics_text = None
                cover_file = local_file.cover_path or song.cover_path
                cover_file = cover_file if cover_file and Path(str(cover_file)).is_file() else None
                tag_written = write_audio_tags(
                    local_file.local_path,
                    title=song.title,
                    artist=song.artist,
                    album=song.album,
                    lyrics=lyrics_text,
                    cover_path=cover_file,
                )
                if tag_written:
                    changes["file_tags"] = tag_written

            if changes:
                song.scrape_status = "done" if (song.album and not is_generic_dir_name(str(song.album))) else "partial"
                song.updated_at = datetime.now(timezone.utc)
                db.add(song)
                updated += 1
                details.append({"song_id": song.id, "title": song.title, "status": "updated", "changes": changes})
                _emit(f"已更新: {song.title}", pct)
            else:
                song.scrape_status = song.scrape_status or "done"
                skipped += 1
                details.append({"song_id": song.id, "title": song.title, "status": "skipped"})
            if idx % 5 == 0:
                db.commit()
        except Exception as e:
            failed += 1
            try:
                song.scrape_status = "failed"
                db.add(song)
            except Exception:
                pass
            details.append({"song_id": getattr(song, "id", None), "title": getattr(song, "title", None), "status": "failed", "error": str(e)})
            _emit(f"失败: {getattr(song,'title',None)} {e}", pct)

    db.commit()
    result = {
        "total": total,
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "items": details[:200],
        "allow_network": allow_network,
        "write_file_tags": write_file_tags,
        "providers": ["musicbrainz", "smart_cn", "musicdl:netease", "musicdl:qq", "musicdl:migu"],
    }
    try:
        write_log(
            db,
            action="scrape",
            target=f"source:{source_id}" if source_id else "songs",
            status="success" if failed == 0 else "partial",
            title="刮削元数据",
            message=f"updated={updated} skipped={skipped} failed={failed}",
            detail=result,
            commit=True,
        )
    except Exception:
        pass
    _emit(f"刮削完成 updated={updated} skipped={skipped} failed={failed}", 100)
    return result
