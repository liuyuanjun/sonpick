from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil
import tempfile
from typing import Any

from sqlalchemy.orm import Session

from app.models import Song, SongFile
from app.services.media_meta_service import (
    materialize_cover_to_l0,
    tag_write_capability,
    write_audio_tags,
)
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


def _store_l0_cover(
    *,
    cover_url: str | None,
    cover_source_path: str | None,
) -> dict[str, Any]:
    """下载或复制封面到 L0 by-hash。无 URL/源路径时表示清空封面。"""
    if cover_url:
        tmp_dir = Path(tempfile.mkdtemp(prefix="sonpick-cover-"))
        try:
            tmp_path = tmp_dir / "cover.bin"
            raw = download_cover_with_diagnostics(cover_url, tmp_path, timeout=20)
            if not raw.get("ok") or not raw.get("path"):
                return {"ok": False, "path": None, "error": raw.get("error") or "封面下载失败"}
            l0 = materialize_cover_to_l0(raw["path"])
            if not l0:
                return {"ok": False, "path": None, "error": "封面固化到 L0 失败"}
            return {"ok": True, "path": l0, "source": "url"}
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    if cover_source_path and Path(cover_source_path).is_file():
        l0 = materialize_cover_to_l0(cover_source_path)
        if not l0:
            return {"ok": False, "path": None, "error": "本地封面固化到 L0 失败"}
        return {"ok": True, "path": l0, "source": "file", "copied": True}

    return {"ok": True, "path": None, "cleared": True}


def _write_sidecar_cover(target: Path, l0_path: str | None, *, clear: bool) -> dict[str, Any]:
    try:
        if clear or not l0_path:
            if target.is_file():
                target.unlink()
            return {"ok": True, "cleared": True, "path": None}
        target.parent.mkdir(parents=True, exist_ok=True)
        src = Path(l0_path)
        if src.resolve() != target.resolve():
            shutil.copy2(src, target)
        return {"ok": True, "path": str(target), "copied": True}
    except OSError as exc:
        return {"ok": False, "error": str(exc), "path": None}


def apply_metadata_to_song_files(
    db: Session,
    song: Song,
    *,
    selected_fields: set[str],
    cover_url: str | None,
    cover_source_path: str | None = None,
    write_file_tags: bool = True,
) -> dict[str, Any]:
    """把 Song L0 元信息写穿到各 SongFile。

    成功语义：
    - 封面 L0（by-hash）在本函数内写入；文本 L0 由调用方先写 Song 列
    - 版本 status: written | skipped | unsupported | failed
    - unsupported（格式不支持内嵌）不计入 failed，不影响 ok
    - ok = failed == 0 且（未选封面或 L0 封面成功）
    """
    resolver = SongFileResolver(db)
    all_files = resolver.all_files(song)
    writable_files = resolver.writable_local_files(song)
    writable_ids = {item.id for item in writable_files}
    cover_selected = "cover" in selected_fields
    text_selected = bool(selected_fields & set(METADATA_FIELDS))

    l0_cover: dict[str, Any] | None = None
    if cover_selected:
        l0_cover = _store_l0_cover(cover_url=cover_url, cover_source_path=cover_source_path)
        if l0_cover.get("ok"):
            song.cover_path = l0_cover.get("path")

    cover_targets: dict[Path, dict[str, Any]] = {}
    if cover_selected and l0_cover and l0_cover.get("ok"):
        clear = bool(l0_cover.get("cleared")) or not l0_cover.get("path")
        for song_file in writable_files:
            target = Path(song_file.local_path).parent / "cover.jpg"
            if target in cover_targets:
                continue
            cover_targets[target] = _write_sidecar_cover(target, l0_cover.get("path"), clear=clear)
    elif cover_selected and l0_cover and not l0_cover.get("ok"):
        for song_file in writable_files:
            target = Path(song_file.local_path).parent / "cover.jpg"
            if target not in cover_targets:
                cover_targets[target] = {
                    "ok": False,
                    "error": l0_cover.get("error") or "L0 封面写入失败",
                    "path": None,
                }

    results: list[dict[str, Any]] = []
    for song_file in all_files:
        result = _base_result(song_file)
        if song_file.id not in writable_ids:
            result.update({
                "status": "skipped",
                "reason": "远端只读，未写入" if song_file.webdav_path else "本地文件不可用",
            })
            results.append(result)
            continue

        cover_result = None
        sidecar_cover_path = None
        if cover_selected:
            target = Path(song_file.local_path).parent / "cover.jpg"
            cover_result = cover_targets.get(target) or {"ok": False, "error": "无侧车结果", "path": None}
            sidecar_cover_path = cover_result.get("path") if cover_result.get("ok") else None
            if cover_result.get("ok"):
                # 侧车路径优先；清空时回落到 L0（可能为 None）
                song_file.cover_path = sidecar_cover_path or getattr(song, "cover_path", None)
            result["cover"] = cover_result
            if cover_result.get("ok") and sidecar_cover_path:
                result["sidecar"] = {"cover": "written"}
            elif cover_result.get("ok") and cover_result.get("cleared"):
                result["sidecar"] = {"cover": "cleared"}
            else:
                result["sidecar"] = {"cover": "failed"}

        cap = tag_write_capability(song_file.local_path or song_file.format)
        embed_cover = sidecar_cover_path or (
            l0_cover.get("path") if l0_cover and l0_cover.get("ok") else None
        )
        # 本轮：不在 full 列表的格式视为完全不支持内嵌
        fully_unsupported = not (cap["text"] or cap["cover"] or cap["lyrics"])

        try:
            if cover_selected and cover_result and not cover_result.get("ok"):
                raise RuntimeError(cover_result.get("error") or "封面侧车写入失败")

            tags: dict[str, Any] = {}
            if write_file_tags and not fully_unsupported:
                tags = write_audio_tags(
                    song_file.local_path,
                    title=song.title if "title" in selected_fields else None,
                    artist=song.artist if "artist" in selected_fields else None,
                    album=song.album if "album" in selected_fields else None,
                    year=song.year if "year" in selected_fields else None,
                    genre=song.genre if "genre" in selected_fields else None,
                    cover_path=embed_cover if cover_selected else None,
                    clear_fields={
                        key for key in selected_fields
                        if key in METADATA_FIELDS and not getattr(song, key, None)
                    } | ({"cover"} if cover_selected and not embed_cover else set()),
                )
                if (text_selected or cover_selected) and not tags:
                    raise RuntimeError("音频标签写入未生效")
                result.update({"status": "written", "tags": tags, "cover": cover_result})
            elif write_file_tags and fully_unsupported:
                reason = "格式不支持内嵌标签"
                if cover_selected and cover_result and cover_result.get("ok") and sidecar_cover_path:
                    reason = "格式不支持内嵌标签，已写侧车"
                result.update({
                    "status": "unsupported",
                    "reason": reason,
                    "tags": tags,
                    "cover": cover_result,
                })
            else:
                # write_file_tags=False：只写侧车/L0
                result.update({"status": "written", "tags": tags, "cover": cover_result})
        except Exception as exc:
            result.update({"status": "failed", "error": str(exc), "cover": cover_result, "tags": {}})
        results.append(result)
        db.add(song_file)

    song.updated_at = datetime.now(timezone.utc)
    db.add(song)
    db.commit()

    written = sum(item["status"] == "written" for item in results)
    failed = sum(item["status"] == "failed" for item in results)
    skipped = sum(item["status"] == "skipped" for item in results)
    unsupported = sum(item["status"] == "unsupported" for item in results)
    l0_ok = (not cover_selected) or bool(l0_cover and l0_cover.get("ok"))
    ok = failed == 0 and l0_ok
    return {
        "ok": ok,
        "partial": failed > 0 and (written > 0 or unsupported > 0),
        "written": written,
        "failed": failed,
        "skipped": skipped,
        "unsupported": unsupported,
        "versions": results,
        "cover_path": song.cover_path,
        "cover_paths": [str(path) for path, item in cover_targets.items() if item.get("ok") and item.get("path")],
        "l0_cover": l0_cover,
    }
