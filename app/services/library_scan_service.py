from __future__ import annotations

import fnmatch
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import AppSettings, MediaSource, Song, SongFile
from app.routers.settings import (
    DEFAULT_SCAN_EXCLUDE,
    DEFAULT_SCAN_EXTS,
    _ensure_settings,
    _parse_json_list,
)
from app.services.library_layout import (
    find_album_cover_file,
    find_lrc_sidecar,
    find_track_cover_file,
    is_generic_dir_name,
)
from app.services.media_meta_service import enrich_local_audio, is_local_file, read_audio_tags, resolve_song_meta
from app.services.operation_log_service import write_log
from app.services.webdav_service import WebDAVService


SIDE_COVER_EXTS = (".jpg", ".jpeg", ".png", ".webp")
SIDE_LRC_EXTS = (".lrc", ".txt")


def _now():
    return datetime.now(timezone.utc)


def _parse_exts(raw: Optional[str]) -> set[str]:
    text = (raw or DEFAULT_SCAN_EXTS).lower()
    out = set()
    for part in text.replace(";", ",").split(","):
        s = part.strip().lstrip(".")
        if s:
            out.add(s)
    return out or set(DEFAULT_SCAN_EXTS.split(","))


def _normalize_globs(globs: list[str]) -> list[str]:
    cleaned = []
    for g in globs or []:
        s = str(g).strip()
        if s:
            cleaned.append(s.replace("\\", "/"))
    return cleaned or list(DEFAULT_SCAN_EXCLUDE)


def _is_excluded(path: str, globs: list[str]) -> bool:
    rel = (path or "").replace("\\", "/").lstrip("/")
    name = rel.split("/")[-1] if rel else ""
    for g in globs:
        gg = g.replace("\\", "/")
        if fnmatch.fnmatch(rel, gg) or fnmatch.fnmatch(name, gg):
            return True
        if not gg.startswith("**/") and fnmatch.fnmatch(rel, f"**/{gg}"):
            return True
        if gg.endswith("/**") and (rel.startswith(gg[:-3]) or f"/{gg[:-3]}" in f"/{rel}"):
            return True
    return False


# Directory names that must never be treated as artist/album metadata.
_GENERIC_DIR_NAMES = {
    "music", "songs", "audio", "download", "downloads", "flac", "mp3", "m4a",
    "wav", "media", "library", "music library", "musiclibrary", "favorite",
    "favorites", "favourite", "favourites", "liked", "liked songs", "all",
    "misc", "various", "various artists", "va", "inbox", "import", "imports",
    "new", "temp", "tmp", "cache", "shared", "public", "data", "storage",
}


def _is_generic_dir_name(name: Optional[str]) -> bool:
    return is_generic_dir_name(name)



def _parse_meta_from_path(path: str) -> dict[str, Optional[str]]:
    """Best-effort path heuristic only. Prefer embedded tags when available."""
    p = Path(path)
    stem = p.stem.strip()
    parent = p.parent.name if p.parent else ""
    grand = p.parent.parent.name if p.parent and p.parent.parent else ""

    title = stem
    artist = None
    album = None

    for sep in (" - ", " – ", " — ", "_-", " | "):
        if sep in stem:
            left, right = stem.split(sep, 1)
            if left.strip() and right.strip():
                artist = left.strip()
                title = right.strip()
                break

    parent_ok = parent and not _is_generic_dir_name(parent)
    grand_ok = grand and not _is_generic_dir_name(grand)

    # Only treat directories as Artist/Album when they look like a real library layout,
    # never use collection folders such as Favorite/Downloads as artist.
    if parent_ok:
        if artist is None and grand_ok:
            artist = grand
            album = parent
        elif album is None and artist:
            album = parent
        # If filename has no artist and only one non-generic parent exists,
        # leave artist empty rather than inventing from a bag/collection folder.

    import re
    title = re.sub(r"^\s*\d{1,3}[\s._-]+", "", title).strip() or stem
    return {"title": title, "artist": artist, "album": album}


def _merge_audio_meta(path_meta: dict[str, Optional[str]], audio_meta: dict[str, Any] | None = None) -> dict[str, Optional[str]]:
    """Prefer embedded tags over path heuristics for title/artist/album."""
    audio_meta = audio_meta or {}
    out = {
        "title": path_meta.get("title"),
        "artist": path_meta.get("artist"),
        "album": path_meta.get("album"),
    }
    for key in ("title", "artist", "album"):
        val = audio_meta.get(key)
        if val and str(val).strip():
            out[key] = str(val).strip()
    return out


def _maybe_write_embedded_lyrics(audio_path: Path, lyrics_text: Optional[str], existing_lrc: Optional[str]) -> Optional[str]:
    """If no sidecar LRC exists, materialize embedded lyrics next to the audio file."""
    if existing_lrc:
        return existing_lrc
    if not lyrics_text or not str(lyrics_text).strip():
        return None
    text = str(lyrics_text).replace("\r\n", "\n").strip()
    if not text:
        return None
    target = audio_path.with_suffix(".lrc")
    try:
        if not target.exists():
            target.write_text(text + ("\n" if not text.endswith("\n") else ""), encoding="utf-8")
        return str(target)
    except Exception:
        return None


def _find_sidecar_local(audio_path: Path, exts: tuple[str, ...]) -> Optional[str]:
    """Find same-stem sidecar using library_layout helpers when possible."""
    # lyrics
    if exts == SIDE_LRC_EXTS or set(e.lower() for e in exts) <= {".lrc", ".txt"}:
        found = find_lrc_sidecar(audio_path)
        return str(found) if found else None

    # covers
    if exts == SIDE_COVER_EXTS or any(e.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif"} for e in exts):
        found = find_track_cover_file(audio_path) or find_album_cover_file(audio_path.parent)
        return str(found) if found else None

    stem = audio_path.with_suffix("")
    for ext in exts:
        cand = Path(str(stem) + ext)
        if cand.is_file():
            return str(cand)
        cand2 = audio_path.with_suffix(ext)
        if cand2.is_file():
            return str(cand2)
    return None




def _find_sidecar_remote(files_by_stem: dict[str, dict[str, str]], remote_path: str, kind: str) -> Optional[str]:
    stem = remote_path.rsplit(".", 1)[0]
    bucket = files_by_stem.get(stem) or {}
    return bucket.get(kind)


class LibraryScanService:
    def __init__(self, db: Session):
        self.db = db
        self.cfg: AppSettings = _ensure_settings(db)

    def _stats(self, source: str, source_id: int | None = None) -> dict[str, Any]:
        return {
            "source": source,
            "source_id": source_id,
            "scanned": 0,
            "added": 0,
            "updated": 0,
            "skipped": 0,
            "errors": 0,
            "message": None,
        }

    def _audio_exts(self, source: MediaSource | None = None) -> set[str]:
        if source:
            return _parse_exts(source.audio_exts)
        return _parse_exts(getattr(self.cfg, "scan_audio_exts", None))

    def _exclude_globs(self, source: MediaSource | None = None) -> list[str]:
        if source:
            return _normalize_globs(_parse_json_list(source.exclude_globs, DEFAULT_SCAN_EXCLUDE))
        return _normalize_globs(
            _parse_json_list(getattr(self.cfg, "scan_exclude_globs", None), DEFAULT_SCAN_EXCLUDE)
        )

    def _mp3_output_globs(self, roots: list[Path]) -> list[str]:
        """Exclude the configured MP3 output directory when it lives inside a scan root."""
        from app.services.convert_service import resolve_mp3_output_dir

        settings = self.db.get(AppSettings, 1)
        mp3_root = resolve_mp3_output_dir(
            getattr(settings, "mp3_output_path", None) if settings else None,
            settings.storage_path if settings else None,
        )
        try:
            mp3_path = Path(mp3_root).expanduser().resolve()
        except Exception:
            return []
        globs: list[str] = []
        for root in roots:
            try:
                rel = mp3_path.relative_to(root.expanduser().resolve())
            except Exception:
                continue
            rel_s = str(rel).replace("\\", "/").strip("/")
            if rel_s:
                globs.append(f"{rel_s}/**")
        return globs

    def _find_logical_song(self, meta: dict[str, Optional[str]], duration: int | None) -> Song | None:
        title = (meta.get("title") or "").strip()
        if not title:
            return None
        query = self.db.query(Song).filter(Song.title == title)
        artist = (meta.get("artist") or "").strip()
        album = (meta.get("album") or "").strip()
        if artist:
            query = query.filter(Song.artist == artist)
        if album:
            query = query.filter(Song.album == album)
        candidates = query.all()
        if duration:
            candidates = [song for song in candidates if not song.duration or abs((song.duration or 0) - duration) <= 3]
        return candidates[0] if candidates else None

    def _upsert_local(self, path: Path, source_id: int, stats: dict[str, Any]) -> None:
        stats["scanned"] += 1
        abs_path = str(path.resolve()) if path.exists() else str(path)
        try:
            if not path.is_file():
                stats["skipped"] += 1
                return
            ext = path.suffix.lower().lstrip(".")
            path_meta = _parse_meta_from_path(str(path))
            size = path.stat().st_size if path.exists() else None
            # unified pipeline: embedded → sidecar (path heuristics only fill gaps)
            resolved = resolve_song_meta(audio_path=path, allow_network=False)
            audio_meta = {
                "duration": resolved.get("duration"),
                "cover_path": resolved.get("cover_path"),
                "title": resolved.get("title"),
                "artist": resolved.get("artist"),
                "album": resolved.get("album"),
                "lyrics": resolved.get("lyrics"),
                "lrc_path": resolved.get("lrc_path"),
            }
            meta = _merge_audio_meta(path_meta, audio_meta)
            duration = audio_meta.get("duration")
            cover = audio_meta.get("cover_path") or _find_sidecar_local(path, SIDE_COVER_EXTS)
            lrc = audio_meta.get("lrc_path") or _find_sidecar_local(path, SIDE_LRC_EXTS)
            lrc = _maybe_write_embedded_lyrics(path, audio_meta.get("lyrics"), lrc)

            song_file = self.db.query(SongFile).filter(SongFile.local_path == abs_path).one_or_none()
            song = self.db.get(Song, song_file.song_id) if song_file else self._find_logical_song(meta, duration)

            if song is None:
                song = Song(
                    title=meta["title"] or path.stem,
                    artist=meta["artist"],
                    album=meta["album"],
                    source="scan-local",
                    format=ext,
                    duration=duration,
                    file_size=size,
                    local_path=abs_path,
                    cover_path=cover,
                    lrc_path=lrc,
                    library_source_id=source_id,
                    status="local",
                    created_at=_now(),
                    updated_at=_now(),
                )
                self.db.add(song)
                self.db.flush()
                song_file = SongFile(song_id=song.id, format=ext, local_path=abs_path, library_source_id=source_id, duration=duration, file_size=size)
                self.db.add(song_file)
                if cover and path.exists():
                    refined = enrich_local_audio(path, song_id=song.id, existing_cover=cover)
                    if refined.get("cover_path"):
                        song.cover_path = refined["cover_path"]
                    if refined.get("duration") and not song.duration:
                        song.duration = refined["duration"]
                stats["added"] += 1
            else:
                if song_file is None:
                    song_file = SongFile(song_id=song.id, format=ext, local_path=abs_path, library_source_id=source_id, duration=duration, file_size=size)
                    self.db.add(song_file)
                else:
                    song_file.format = ext
                    song_file.library_source_id = source_id
                    song_file.duration = duration or song_file.duration
                    song_file.file_size = size or song_file.file_size
                    song_file.updated_at = _now()
                changed = False
                if not song.local_path:
                    song.local_path = abs_path
                    changed = True
                if not song.library_source_id and source_id:
                    song.library_source_id = source_id
                    changed = True
                # Prefer richer tags: fill empty fields, and replace generic/collection-folder names.
                if meta["artist"]:
                    if (not song.artist) or _is_generic_dir_name(song.artist):
                        if song.artist != meta["artist"]:
                            song.artist = meta["artist"]
                            changed = True
                elif song.artist and _is_generic_dir_name(song.artist):
                    song.artist = None
                    changed = True
                if meta["album"]:
                    if (not song.album) or _is_generic_dir_name(song.album):
                        if song.album != meta["album"]:
                            song.album = meta["album"]
                            changed = True
                elif song.album and _is_generic_dir_name(song.album):
                    song.album = None
                    changed = True
                if meta["title"] and meta["title"] != song.title and (not song.title or song.title == path.stem):
                    song.title = meta["title"]
                    changed = True
                if duration and (not song.duration or song.duration <= 0):
                    song.duration = int(duration)
                    changed = True
                if cover and (not song.cover_path or not is_local_file(song.cover_path)):
                    song.cover_path = cover
                    changed = True
                if lrc and (
                    not song.lrc_path
                    or (str(song.lrc_path) != str(lrc) and not Path(str(song.lrc_path)).exists())
                ):
                    song.lrc_path = lrc
                    changed = True
                if size and song.file_size != size:
                    song.file_size = size
                    changed = True
                if ext and not song.format:
                    song.format = ext
                    changed = True
                if song.webdav_path:
                    new_status = "both"
                else:
                    new_status = "local"
                if song.status != new_status:
                    song.status = new_status
                    changed = True
                if (not song.duration or not is_local_file(song.cover_path)) and path.exists():
                    refined = enrich_local_audio(
                        path,
                        song_id=song.id,
                        existing_cover=song.cover_path if is_local_file(song.cover_path) else cover,
                    )
                    if refined.get("duration") and (not song.duration or song.duration <= 0):
                        song.duration = int(refined["duration"])
                        changed = True
                    if refined.get("cover_path") and (not song.cover_path or not is_local_file(song.cover_path)):
                        song.cover_path = refined["cover_path"]
                        changed = True
                if changed:
                    song.updated_at = _now()
                    stats["updated"] += 1
                else:
                    stats["skipped"] += 1
        except Exception:
            stats["errors"] += 1

    def _upsert_remote(self, remote_path: str, size: Optional[int], sidecar_map: dict[str, dict[str, str]], source_id: int, stats: dict[str, Any]) -> None:
        stats["scanned"] += 1
        try:
            rel = remote_path.replace("\\", "/").lstrip("/")
            ext = rel.rsplit(".", 1)[-1].lower() if "." in rel else ""
            meta = _parse_meta_from_path(rel)
            stem = rel.rsplit(".", 1)[0] if "." in rel else rel
            bucket = sidecar_map.get(stem) or {}
            cover = bucket.get("cover")
            lrc = bucket.get("lrc")

            song_file = self.db.query(SongFile).filter(SongFile.webdav_path == rel, SongFile.library_source_id == source_id).one_or_none()
            song = self.db.get(Song, song_file.song_id) if song_file else self._find_logical_song(meta, None)

            if song is None:
                song = Song(
                    title=meta["title"] or Path(rel).stem,
                    artist=meta["artist"],
                    album=meta["album"],
                    source="scan-webdav",
                    format=ext,
                    file_size=size,
                    webdav_path=rel,
                    cover_path=cover,
                    lrc_path=lrc,
                    library_source_id=source_id,
                    status="remote",
                    created_at=_now(),
                    updated_at=_now(),
                )
                self.db.add(song)
                self.db.flush()
                song_file = SongFile(song_id=song.id, format=ext, webdav_path=rel, library_source_id=source_id, file_size=size)
                self.db.add(song_file)
                stats["added"] += 1
            else:
                if song_file is None:
                    song_file = SongFile(song_id=song.id, format=ext, webdav_path=rel, library_source_id=source_id, file_size=size)
                    self.db.add(song_file)
                else:
                    song_file.format = ext
                    song_file.file_size = size or song_file.file_size
                    song_file.updated_at = _now()
                changed = False
                if not song.webdav_path:
                    song.webdav_path = rel
                    changed = True
                if not song.library_source_id and source_id:
                    song.library_source_id = source_id
                    changed = True
                if meta["artist"]:
                    if (not song.artist) or _is_generic_dir_name(song.artist):
                        if song.artist != meta["artist"]:
                            song.artist = meta["artist"]
                            changed = True
                elif song.artist and _is_generic_dir_name(song.artist):
                    song.artist = None
                    changed = True
                if meta["album"]:
                    if (not song.album) or _is_generic_dir_name(song.album):
                        if song.album != meta["album"]:
                            song.album = meta["album"]
                            changed = True
                elif song.album and _is_generic_dir_name(song.album):
                    song.album = None
                    changed = True
                if cover and (not song.cover_path or not is_local_file(song.cover_path)):
                    if not is_local_file(song.cover_path):
                        song.cover_path = cover
                        changed = True
                if lrc and (not song.lrc_path or song.lrc_path != lrc):
                    song.lrc_path = lrc
                    changed = True
                if size and song.file_size != size:
                    song.file_size = size
                    changed = True
                if ext and not song.format:
                    song.format = ext
                    changed = True
                if is_local_file(song.local_path):
                    refined = enrich_local_audio(
                        song.local_path,
                        song_id=song.id,
                        existing_cover=song.cover_path if is_local_file(song.cover_path) else None,
                    )
                    if refined.get("duration") and (not song.duration or song.duration <= 0):
                        song.duration = int(refined["duration"])
                        changed = True
                    if refined.get("cover_path"):
                        song.cover_path = refined["cover_path"]
                        changed = True
                if song.local_path and song.webdav_path:
                    new_status = "both"
                elif song.local_path:
                    new_status = "local"
                elif song.status == "uploaded" and song.webdav_path:
                    new_status = "uploaded"
                else:
                    new_status = "remote"
                if song.status != new_status:
                    song.status = new_status
                    changed = True
                if not song.source:
                    song.source = "scan-webdav"
                    changed = True
                if changed:
                    song.updated_at = _now()
                    stats["updated"] += 1
                else:
                    stats["skipped"] += 1
        except Exception:
            stats["errors"] += 1

    def _scan_local_source(self, source: MediaSource) -> dict[str, Any]:
        stats = self._stats("local", source.id)
        if not source.enabled:
            stats["message"] = "源已禁用"
            return stats

        storage = (source.root_path or "").strip()
        dirs = _parse_json_list(getattr(source, "scan_dirs", None), [])
        roots: list[Path] = []
        for d in dirs:
            s = str(d).strip()
            if s:
                roots.append(Path(s).expanduser())
        if not roots and storage:
            roots.append(Path(storage).expanduser())
        if not roots:
            stats["message"] = "未配置本地扫描目录"
            return stats

        exts = self._audio_exts(source)
        globs = self._exclude_globs(source) + self._mp3_output_globs(roots)
        seen: set[str] = set()

        for root in roots:
            if not root.exists() or not root.is_dir():
                stats["errors"] += 1
                continue
            for dirpath, dirnames, filenames in os.walk(root):
                kept = []
                for dn in dirnames:
                    rel = str((Path(dirpath) / dn).relative_to(root)).replace("\\", "/")
                    if _is_excluded(rel + "/", globs) or _is_excluded(dn, globs):
                        continue
                    kept.append(dn)
                dirnames[:] = kept
                for fn in filenames:
                    full = Path(dirpath) / fn
                    try:
                        rel = str(full.relative_to(root)).replace("\\", "/")
                    except Exception:
                        rel = str(full).replace("\\", "/")
                    if _is_excluded(rel, globs):
                        stats["skipped"] += 1
                        continue
                    ext = full.suffix.lower().lstrip(".")
                    if ext not in exts:
                        continue
                    key = str(full.resolve()) if full.exists() else str(full)
                    if key in seen:
                        continue
                    seen.add(key)
                    self._upsert_local(full, source.id, stats)

        self.db.commit()
        return stats

    def _scan_webdav_source(self, source: MediaSource) -> dict[str, Any]:
        stats = self._stats("webdav", source.id)
        if not source.enabled:
            stats["message"] = "源已禁用"
            return stats
        if not (source.webdav_url or "").strip():
            stats["message"] = "WebDAV 未配置"
            stats["errors"] += 1
            return stats

        dirs = _parse_json_list(getattr(source, "scan_remote_dirs", None), [""])
        if not dirs:
            dirs = [""]
        exts = self._audio_exts(source)
        globs = self._exclude_globs(source)
        service = WebDAVService(self.db, source=source)

        audio_files: list[dict] = []
        sidecar_map: dict[str, dict[str, str]] = {}

        for d in dirs:
            base = (d or "").strip().strip("/")
            try:
                files = service.list_recursive(base)
            except Exception as e:
                stats["errors"] += 1
                stats["message"] = str(e)
                continue
            for item in files:
                rel = (item.get("path") or "").replace("\\", "/").lstrip("/")
                if not rel or _is_excluded(rel, globs):
                    continue
                lower = rel.lower()
                stem = rel.rsplit(".", 1)[0] if "." in rel else rel
                if any(lower.endswith(x) for x in SIDE_COVER_EXTS):
                    sidecar_map.setdefault(stem, {})["cover"] = rel
                    continue
                if any(lower.endswith(x) for x in SIDE_LRC_EXTS):
                    bucket = sidecar_map.setdefault(stem, {})
                    # Prefer .lrc; keep .txt only if no lrc yet
                    if lower.endswith(".lrc"):
                        bucket["lrc"] = rel
                    elif "lrc" not in bucket:
                        bucket["lrc"] = rel
                    continue
                ext = lower.rsplit(".", 1)[-1] if "." in lower else ""
                if ext in exts:
                    audio_files.append(item)

        for item in audio_files:
            rel = (item.get("path") or "").replace("\\", "/").lstrip("/")
            self._upsert_remote(rel, item.get("size"), sidecar_map, source.id, stats)

        self.db.commit()
        return stats

    def _update_source_scan_stats(self, source: MediaSource, stats: dict[str, Any]) -> None:
        source.last_scan_at = _now()
        source.last_scan_added = stats.get("added", 0) or 0
        source.last_scan_updated = stats.get("updated", 0) or 0
        source.song_count = (
            self.db.query(Song).filter(Song.library_source_id == source.id).count()
        )
        self.db.commit()

    def scan(self, source: str = "all", source_ids: list[int] | None = None) -> dict[str, Any]:
        source = (source or "all").lower()
        started = time.time()
        all_stats: list[dict[str, Any]] = []
        total_added = 0
        total_updated = 0
        total_skipped = 0
        total_errors = 0

        # Check if any source exists; if not, seed first
        if self.db.query(MediaSource).count() == 0:
            from app.database import get_engine
            from app.database import _seed_media_sources
            _seed_media_sources(get_engine())
            self.db.expire_all()

        if source_ids:
            sources = self.db.query(MediaSource).filter(MediaSource.id.in_(source_ids)).all()
        elif source == "all":
            sources = self.db.query(MediaSource).order_by(MediaSource.id.asc()).all()
        elif source == "local":
            sources = self.db.query(MediaSource).filter(MediaSource.type == "local").all()
        elif source == "webdav":
            sources = self.db.query(MediaSource).filter(MediaSource.type == "webdav").all()
        else:
            sources = []

        for s in sources:
            if s.type == "local":
                stats = self._scan_local_source(s)
            elif s.type == "webdav":
                stats = self._scan_webdav_source(s)
            else:
                continue
            self._update_source_scan_stats(s, stats)
            all_stats.append(stats)
            total_added += stats.get("added", 0) or 0
            total_updated += stats.get("updated", 0) or 0
            total_skipped += stats.get("skipped", 0) or 0
            total_errors += stats.get("errors", 0) or 0

        try:
            from app.services.convert_service import ConvertService
            ConvertService(self.db).auto_convert_missing_mp3()
        except Exception:
            pass

        duration_ms = int((time.time() - started) * 1000)
        msg_parts = []
        for st in all_stats:
            if st.get("message"):
                msg_parts.append(f"{st['source']}#{st.get('source_id')}: {st['message']}")

        result = {
            "ok": total_errors == 0,
            "source": source,
            "sources": all_stats,
            "total_added": total_added,
            "total_updated": total_updated,
            "total_skipped": total_skipped,
            "total_errors": total_errors,
            "duration_ms": duration_ms,
            "message": "; ".join(msg_parts) if msg_parts else None,
        }
        # keep legacy fields for compat
        local_stats = next((st for st in all_stats if st["source"] == "local"), None)
        webdav_stats = next((st for st in all_stats if st["source"] == "webdav"), None)
        if local_stats:
            result["local"] = local_stats
        if webdav_stats:
            result["webdav"] = webdav_stats

        write_log(
            self.db,
            action="scan",
            target="library",
            status="success" if total_errors == 0 else "partial",
            title="曲库扫描",
            message=result["message"] or f"新增 {total_added}，更新 {total_updated}",
            detail=result,
        )
        return result
