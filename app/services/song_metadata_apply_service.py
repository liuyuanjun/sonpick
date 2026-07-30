from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import logging
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


log = logging.getLogger("sonpick.meta")

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
                err = raw.get("error") or "封面下载失败"
                log.warning("L0 cover download failed url=%s error=%s detail=%s", cover_url, err, raw)
                return {"ok": False, "path": None, "error": err, "detail": raw}
            l0 = materialize_cover_to_l0(raw["path"])
            if not l0:
                log.warning("L0 cover materialize failed url=%s tmp=%s", cover_url, raw.get("path"))
                return {"ok": False, "path": None, "error": "封面固化到 L0 失败", "detail": raw}
            log.info("L0 cover stored path=%s url=%s", l0, cover_url)
            return {"ok": True, "path": l0, "source": "url"}
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    if cover_source_path and Path(cover_source_path).is_file():
        l0 = materialize_cover_to_l0(cover_source_path)
        if not l0:
            log.warning("L0 cover materialize failed source=%s", cover_source_path)
            return {"ok": False, "path": None, "error": "本地封面固化到 L0 失败"}
        log.info("L0 cover stored path=%s source=%s", l0, cover_source_path)
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
        if not src.is_file():
            return {"ok": False, "error": f"L0 封面文件不存在: {l0_path}", "path": None}
        if src.resolve() != target.resolve():
            shutil.copy2(src, target)
        return {"ok": True, "path": str(target), "copied": True}
    except OSError as exc:
        log.warning("sidecar cover write failed target=%s err=%s", target, exc)
        return {"ok": False, "error": str(exc), "path": None}


def _tag_payload_without_meta(tags: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in (tags or {}).items() if not str(k).startswith("_")}


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
    - 封面失败与标签失败分开统计；封面失败不再阻断文本标签写穿
    - unsupported（格式不支持内嵌）不计入 failed
    - ok = tag failed == 0 且（未选封面或 L0 封面成功）
      （侧车失败单独在 cover/sidecar 字段体现，不把整版本打成 failed，除非标签也失败）
    """
    resolver = SongFileResolver(db)
    all_files = resolver.all_files(song)
    writable_files = resolver.writable_local_files(song)
    writable_ids = {item.id for item in writable_files}
    cover_selected = "cover" in selected_fields
    text_selected = bool(selected_fields & set(METADATA_FIELDS))

    log.info(
        "apply metadata song_id=%s fields=%s write_file_tags=%s files=%s writable=%s cover_url=%s",
        getattr(song, "id", None),
        sorted(selected_fields),
        write_file_tags,
        len(all_files),
        len(writable_files),
        bool(cover_url),
    )

    l0_cover: dict[str, Any] | None = None
    if cover_selected:
        l0_cover = _store_l0_cover(cover_url=cover_url, cover_source_path=cover_source_path)
        if l0_cover.get("ok"):
            song.cover_path = l0_cover.get("path")
        else:
            log.warning(
                "apply metadata L0 cover failed song_id=%s error=%s",
                getattr(song, "id", None),
                l0_cover.get("error"),
            )

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
        sidecar_ok = True
        if cover_selected:
            target = Path(song_file.local_path).parent / "cover.jpg"
            cover_result = cover_targets.get(target) or {"ok": False, "error": "无侧车结果", "path": None}
            sidecar_ok = bool(cover_result.get("ok"))
            sidecar_cover_path = cover_result.get("path") if sidecar_ok else None
            if sidecar_ok:
                song_file.cover_path = sidecar_cover_path or getattr(song, "cover_path", None)
            result["cover"] = cover_result
            if sidecar_ok and sidecar_cover_path:
                result["sidecar"] = {"cover": "written"}
            elif sidecar_ok and cover_result.get("cleared"):
                result["sidecar"] = {"cover": "cleared"}
            else:
                result["sidecar"] = {"cover": "failed"}
                result["cover_error"] = cover_result.get("error")

        cap = tag_write_capability(song_file.local_path or song_file.format)
        # 内嵌封面：侧车 → L0（即使侧车失败，只要 L0 在仍可 embed）
        embed_cover = sidecar_cover_path or (
            l0_cover.get("path") if l0_cover and l0_cover.get("ok") else None
        )
        fully_unsupported = not (cap["text"] or cap["cover"] or cap["lyrics"])

        try:
            tags: dict[str, Any] = {}
            tag_error = None

            if write_file_tags and fully_unsupported:
                reason = "格式不支持内嵌标签"
                if cover_selected and sidecar_ok and sidecar_cover_path:
                    reason = "格式不支持内嵌标签，已写侧车"
                elif cover_selected and not sidecar_ok:
                    reason = f"格式不支持内嵌标签；侧车失败: {cover_result.get('error') if cover_result else 'unknown'}"
                result.update({
                    "status": "unsupported",
                    "reason": reason,
                    "tags": {},
                    "cover": cover_result,
                })
            elif write_file_tags and not fully_unsupported:
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
                ) or {}
                tag_error = tags.get("_error")
                clean_tags = _tag_payload_without_meta(tags)

                if tag_error:
                    raise RuntimeError(tag_error)

                if (text_selected or cover_selected) and not clean_tags:
                    # 区分：要写封面但 cover 文件读不到 / 仅 clear 等
                    detail = []
                    if text_selected:
                        detail.append("文本标签")
                    if cover_selected:
                        detail.append("封面内嵌")
                        if cover_selected and not embed_cover:
                            detail.append("(无可用封面文件)")
                    raise RuntimeError(
                        "音频标签写入未生效: " + "、".join(detail) if detail else "音频标签写入未生效"
                    )

                # 标签成功；侧车失败只作为警告，不把整版本标 failed
                status = "written"
                warnings: list[str] = []
                if cover_selected and not sidecar_ok:
                    warnings.append(f"侧车封面失败: {cover_result.get('error') if cover_result else 'unknown'}")
                result.update({
                    "status": status,
                    "tags": clean_tags,
                    "cover": cover_result,
                })
                if warnings:
                    result["warnings"] = warnings
                    result["reason"] = "；".join(warnings)
            else:
                # write_file_tags=False：只写侧车/L0
                result.update({"status": "written", "tags": {}, "cover": cover_result})
                if cover_selected and not sidecar_ok:
                    result["warnings"] = [f"侧车封面失败: {cover_result.get('error') if cover_result else 'unknown'}"]
        except Exception as exc:
            err = str(exc)
            log.warning(
                "apply metadata version failed song_id=%s file_id=%s path=%s format=%s error=%s",
                getattr(song, "id", None),
                song_file.id,
                song_file.local_path,
                song_file.format,
                err,
            )
            result.update({
                "status": "failed",
                "error": err,
                "cover": cover_result,
                "tags": {},
            })
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

    errors = [
        {
            "song_file_id": item.get("song_file_id"),
            "format": item.get("format"),
            "path": item.get("path"),
            "error": item.get("error") or item.get("cover_error") or item.get("reason"),
            "status": item.get("status"),
        }
        for item in results
        if item.get("status") in {"failed", "unsupported"} or item.get("warnings") or item.get("cover_error")
    ]
    if not l0_ok and l0_cover:
        errors.insert(0, {
            "song_file_id": None,
            "format": None,
            "path": None,
            "error": f"L0 封面失败: {l0_cover.get('error')}",
            "status": "l0_cover_failed",
        })

    log.info(
        "apply metadata done song_id=%s ok=%s written=%s failed=%s unsupported=%s skipped=%s l0_ok=%s errors=%s",
        getattr(song, "id", None),
        ok,
        written,
        failed,
        unsupported,
        skipped,
        l0_ok,
        [e.get("error") for e in errors],
    )

    return {
        "ok": ok,
        "partial": (failed > 0 and (written > 0 or unsupported > 0)) or (not l0_ok and written > 0),
        "written": written,
        "failed": failed,
        "skipped": skipped,
        "unsupported": unsupported,
        "versions": results,
        "cover_path": song.cover_path,
        "cover_paths": [str(path) for path, item in cover_targets.items() if item.get("ok") and item.get("path")],
        "l0_cover": l0_cover,
        "errors": errors,
        "error_summary": "；".join(
            f"{e.get('format') or 'L0'}: {e.get('error')}" for e in errors if e.get("error")
        )[:500],
    }
