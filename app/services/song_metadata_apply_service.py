from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil
from typing import Any

from sqlalchemy.orm import Session

from app.models import Song, SongFile
from app.services.media_meta_service import write_audio_tags
from app.services.scrape.cover_utils import download_cover_with_diagnostics
from app.services.song_file_resolver import SongFileResolver


METADATA_FIELDS = ("title", "artist", "album", "year", "genre")


def _base_result(song_file: SongFile) -> dict[str, Any]:
    return {
        "song_file_id": song_file.id,
        "format": song_file.format,
        "path": song_file.local_path or song_file.webdav_path,
        "location": "local" if song_file.local_path else "webdav",
    }


def apply_metadata_to_song_files(
    db: Session,
    song: Song,
    *,
    selected_fields: set[str],
    cover_url: str | None,
    cover_source_path: str | None = None,
    write_file_tags: bool = True,
) -> dict[str, Any]:
    resolver = SongFileResolver(db)
    all_files = resolver.all_files(song)
    writable_files = resolver.writable_local_files(song)
    writable_ids = {item.id for item in writable_files}
    cover_selected = "cover" in selected_fields
    cover_targets: dict[Path, dict[str, Any]] = {}

    if cover_selected:
        for song_file in writable_files:
            target = Path(song_file.local_path).parent / "cover.jpg"
            if target in cover_targets:
                continue
            if cover_url:
                cover_targets[target] = download_cover_with_diagnostics(cover_url, target, timeout=20)
            elif cover_source_path and Path(cover_source_path).is_file():
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if Path(cover_source_path).resolve() != target.resolve():
                        shutil.copy2(cover_source_path, target)
                    cover_targets[target] = {"ok": True, "path": str(target), "copied": True}
                except OSError as exc:
                    cover_targets[target] = {"ok": False, "error": str(exc), "path": None}
            else:
                try:
                    if target.is_file():
                        target.unlink()
                    cover_targets[target] = {"ok": True, "cleared": True, "path": None}
                except OSError as exc:
                    cover_targets[target] = {"ok": False, "error": str(exc), "path": None}

    results: list[dict[str, Any]] = []
    aggregate_cover = None
    for song_file in all_files:
        result = _base_result(song_file)
        if song_file.id not in writable_ids:
            result.update({"status": "skipped", "reason": "远端只读，未写入" if song_file.webdav_path else "本地文件不可用"})
            results.append(result)
            continue

        cover_result = None
        cover_path = None
        if cover_selected:
            target = Path(song_file.local_path).parent / "cover.jpg"
            cover_result = cover_targets[target]
            cover_path = cover_result.get("path") if cover_result.get("ok") else None
            if cover_result.get("ok"):
                song_file.cover_path = cover_path
                if cover_path and aggregate_cover is None:
                    aggregate_cover = cover_path

        try:
            tags = {}
            if write_file_tags:
                tags = write_audio_tags(
                    song_file.local_path,
                    title=song.title if "title" in selected_fields else None,
                    artist=song.artist if "artist" in selected_fields else None,
                    album=song.album if "album" in selected_fields else None,
                    year=song.year if "year" in selected_fields else None,
                    genre=song.genre if "genre" in selected_fields else None,
                    cover_path=cover_path if cover_selected else None,
                    clear_fields={
                        key for key in selected_fields
                        if key in METADATA_FIELDS and not getattr(song, key, None)
                    } | ({"cover"} if cover_selected and not cover_url and not cover_source_path else set()),
                )
                if not tags:
                    raise RuntimeError("音频标签写入未生效")
            if cover_result and not cover_result.get("ok"):
                raise RuntimeError(cover_result.get("error") or "封面侧车写入失败")
            result.update({"status": "written", "tags": tags, "cover": cover_result})
        except Exception as exc:
            result.update({"status": "failed", "error": str(exc), "cover": cover_result})
        results.append(result)
        db.add(song_file)

    if cover_selected:
        song.cover_path = aggregate_cover
    song.updated_at = datetime.now(timezone.utc)
    db.add(song)
    db.commit()

    written = sum(item["status"] == "written" for item in results)
    failed = sum(item["status"] == "failed" for item in results)
    skipped = sum(item["status"] == "skipped" for item in results)
    return {
        "ok": failed == 0,
        "partial": failed > 0 and written > 0,
        "written": written,
        "failed": failed,
        "skipped": skipped,
        "versions": results,
        "cover_paths": [str(path) for path, item in cover_targets.items() if item.get("ok") and item.get("path")],
    }
