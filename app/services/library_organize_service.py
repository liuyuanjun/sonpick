"""曲库整理与元数据刮削（整合进 Sonpick）。

- preview: 只生成计划
- apply: 移动到 艺术家/专辑/歌名；失败进 _failed/
- scrape: 内嵌→侧车→网络补全/纠正元数据
"""

from __future__ import annotations

import re
import shutil
import traceback
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import AppSettings, MediaSource, Song, SongFile
from app.services.library_layout import (
    UNKNOWN_ALBUM,
    UNKNOWN_ARTIST,
    find_album_cover_file,
    find_lrc_sidecar,
    find_track_cover_file,
    is_generic_dir_name,
    library_relative_dir,
    parse_filename_meta,
    preferred_album_cover_path,
    track_stem,
)
from app.services.media_meta_service import (
    extract_embedded_cover_bytes,
    is_local_file,
    read_audio_duration,
    read_audio_tags,
    resolve_song_meta,
    write_album_cover_file,
)
from app.services.operation_log_service import write_log
from app.services.scrape.query_normalize import clean_artist, clean_title, split_title_artist

AUDIO_EXTS = {".mp3", ".flac", ".m4a", ".wav", ".ogg", ".aac", ".ape", ".wma", ".opus"}
FAILED_DIR_NAME = "_failed"
SKIP_DIR_NAMES = {
    ".git",
    ".musicdl_work",
    "@eaDir",
    "#recycle",
    "covers",
    FAILED_DIR_NAME.lower(),
    "node_modules",
    "venv",
    ".venv",
}


def _safe_rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return str(path)


def _unique_path(dst: Path) -> Path:
    if not dst.exists():
        return dst
    stem, ext = dst.stem, dst.suffix
    i = 1
    while True:
        cand = dst.with_name(f"{stem}_{i}{ext}")
        if not cand.exists():
            return cand
        i += 1


def _move_local(src: Path, dst: Path) -> Path:
    dst = _unique_path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return dst


def _copy_local(src: Path, dst: Path) -> Path:
    dst = _unique_path(dst) if dst.exists() else dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), str(dst))
    return dst


def _sync_song_file_path(db: Session, song: Song, old_candidates: set[str], new_path: Path) -> None:
    """整理移动文件后同步更新 SongFile 版本行（0.6.0 起转换/播放以 SongFile 为准）。"""
    normalized = {c.replace("\\", "/") for c in old_candidates if c}
    rows = (
        db.query(SongFile)
        .filter(SongFile.song_id == song.id, SongFile.local_path.isnot(None))
        .all()
    )
    for sf in rows:
        lp = (sf.local_path or "").replace("\\", "/")
        if lp in normalized or (lp.endswith(new_path.name) and not Path(lp).exists()):
            owner = (
                db.query(SongFile)
                .filter(SongFile.local_path == str(new_path), SongFile.id != sf.id)
                .first()
            )
            if owner is not None:
                # 已有版本行指向新路径（local_path 唯一约束），当前行冗余
                db.delete(sf)
                continue
            sf.local_path = str(new_path)
            if new_path.exists():
                sf.file_size = new_path.stat().st_size
            db.add(sf)


def _parse_filename_meta(path: Path) -> dict[str, Optional[str]]:
    return parse_filename_meta(path)



def _source_root_local(source: MediaSource) -> Path:
    root = (source.root_path or "").strip()
    if not root:
        raise ValueError("本地源未配置 root_path")
    p = Path(root).expanduser()
    if not p.is_dir():
        raise ValueError(f"本地源目录不可用: {root}")
    return p.resolve()


def _resolve_local_subdir(root: Path, relative_dir: str = "") -> Path:
    root = root.resolve()
    rel = (relative_dir or "").strip().strip("/").replace("\\", "/")
    if not rel:
        return root
    if ".." in Path(rel).parts:
        raise ValueError("目录路径非法")
    base = (root / rel).resolve()
    try:
        base.relative_to(root)
    except Exception as exc:
        raise ValueError("目录越界") from exc
    if not base.is_dir():
        raise ValueError(f"目录不存在: {rel}")
    return base


def _iter_local_audio(
    root: Path,
    *,
    relative_dir: str = "",
    include_failed: bool = False,
    max_files: int = 0,
) -> list[Path]:
    """Walk audio files under root/relative_dir.

    max_files>0: stop after collecting that many matches (important for large NAS trees).
    """
    root = root.resolve()
    base = _resolve_local_subdir(root, relative_dir)
    skip = set(SKIP_DIR_NAMES)
    if include_failed:
        skip.discard(FAILED_DIR_NAME.lower())

    out: list[Path] = []
    # os.walk is usually faster/more controllable than Path.rglob on huge trees
    import os

    for dirpath, dirnames, filenames in os.walk(base):
        # prune skipped dirs in-place
        pruned = []
        for name in list(dirnames):
            low = name.lower()
            if name.startswith(".") or low in skip:
                continue
            pruned.append(name)
        dirnames[:] = sorted(pruned, key=str.lower)
        filenames = sorted(filenames, key=str.lower)
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix.lower() not in AUDIO_EXTS:
                continue
            try:
                rel_parts = p.relative_to(root).parts
            except Exception:
                continue
            mid = rel_parts[:-1]
            if any(part.lower() in skip or part.startswith(".") for part in mid):
                continue
            out.append(p)
            if max_files and max_files > 0 and len(out) >= max_files:
                return out
    return out


def _list_local_subdirs(root: Path, *, relative_dir: str = "") -> list[dict[str, Any]]:
    root = root.resolve()
    base = _resolve_local_subdir(root, relative_dir)
    items: list[dict[str, Any]] = []
    try:
        entries = sorted(base.iterdir(), key=lambda p: p.name.lower())
    except Exception:
        return items
    for entry in entries:
        if not entry.is_dir():
            continue
        name = entry.name
        if name.startswith("."):
            continue
        if name.lower() in SKIP_DIR_NAMES and name.lower() != FAILED_DIR_NAME.lower():
            continue
        try:
            rel = entry.resolve().relative_to(root).as_posix()
        except Exception:
            continue
        items.append({"name": name, "path": rel})
    return items


def _meta_for_local_file(
    path: Path,
    song: Song | None = None,
    *,
    read_duration: bool = False,
    read_tags: bool = True,
) -> dict[str, Any]:
    """Priority for reorganize: DB (scraped) → embedded tags → filename.

    刮削结果写在 Song 行上；若写标签失败/权限不足，内嵌仍可能没有专辑。
    整理必须以 DB 专辑为准，否则会出现「刮削成功但整理全缺专辑」。
    """
    path_guess = parse_filename_meta(path)
    tags = read_audio_tags(path) if read_tags else {}
    sources: list[str] = []

    title = None
    artist = None
    album = None

    # 1) DB first
    if song and song.title and str(song.title).strip():
        title = str(song.title).strip()
        sources.append("db")
    if song and song.artist and str(song.artist).strip() and not is_generic_dir_name(song.artist):
        artist = str(song.artist).strip()
        sources.append("db")
    if song and song.album and str(song.album).strip() and not is_generic_dir_name(song.album):
        album = str(song.album).strip()
        sources.append("db")

    # 2) embedded fills gaps
    emb_title = tags.get("title")
    emb_artist = tags.get("artist")
    emb_album = tags.get("album")
    if emb_title or emb_artist or emb_album:
        sources.append("embedded")
    if not title and emb_title:
        title = emb_title
    if (not artist or is_generic_dir_name(artist)) and emb_artist and not is_generic_dir_name(emb_artist):
        artist = emb_artist
    if (not album or is_generic_dir_name(album)) and emb_album and not is_generic_dir_name(emb_album):
        album = emb_album

    # 3) path / filename fills gaps
    if not title and path_guess.get("title"):
        title = path_guess.get("title")
        sources.append("path")
    if (not artist or is_generic_dir_name(artist)) and path_guess.get("artist"):
        artist = path_guess.get("artist")
        sources.append("path")

    # 清洗 mid / 拆分「画 赵雷」
    if title or artist:
        st, sa = split_title_artist(title, artist)
        if st:
            title = st
        if sa:
            artist = sa

    if is_generic_dir_name(artist):
        artist = None
    if is_generic_dir_name(album):
        album = None

    duration = None
    if song and song.duration:
        try:
            duration = int(song.duration)
        except Exception:
            duration = None
    if read_duration and (not duration or duration <= 0):
        try:
            duration = read_audio_duration(path)
        except Exception:
            duration = None

    return {
        "title": title or path.stem,
        "artist": artist,
        "album": album,
        "lyrics": tags.get("lyrics"),
        "duration": duration,
        "source": "+".join(dict.fromkeys(sources)) if sources else "path",
    }


def _plan_item(
    *,
    song_id: int | None,
    from_path: str,
    to_path: str,
    title: str,
    artist: str | None,
    album: str | None,
    actions: list[str],
    status: str = "planned",
    error: str | None = None,
    meta_source: str | None = None,
    duration: int | None = None,
    changed: bool | None = None,
) -> dict[str, Any]:
    # 缺专辑跳过时不要伪装成 Unknown Album
    if status == "skipped":
        artist_out = artist or ""
        album_out = album or ""
    else:
        artist_out = artist or UNKNOWN_ARTIST
        album_out = album or UNKNOWN_ALBUM
    return {
        "song_id": song_id,
        "from_path": from_path,
        "to_path": to_path,
        "title": title,
        "artist": artist_out,
        "album": album_out,
        "actions": actions,
        "status": status,
        "error": error,
        "changed": (from_path != to_path) if changed is None else bool(changed),
        "meta_source": meta_source,
        "duration": duration,
    }


def _album_missing(album: str | None) -> bool:
    if not album or not str(album).strip():
        return True
    return is_generic_dir_name(str(album)) or str(album).strip() in {UNKNOWN_ALBUM, "Unknown Album"}


class LibraryOrganizeService:
    def __init__(self, db: Session):
        self.db = db

    def get_source(self, source_id: int) -> MediaSource:
        source = self.db.get(MediaSource, source_id)
        if not source:
            raise ValueError("源不存在")
        return source

    def _format_base_dirs(self) -> dict[str, Path]:
        """无损/MP3 存放目录（绝对路径），用于按格式归档整理。"""
        from app.services.convert_service import (
            resolve_lossless_output_dir,
            resolve_mp3_output_dir,
        )

        settings = self.db.get(AppSettings, 1)
        storage = getattr(settings, "storage_path", None) if settings else None
        return {
            "lossless": Path(resolve_lossless_output_dir(
                getattr(settings, "lossless_output_path", None) if settings else None,
                storage,
            )),
            "mp3": Path(resolve_mp3_output_dir(
                getattr(settings, "mp3_output_path", None) if settings else None,
                storage,
            )),
        }

    @staticmethod
    def _target_base(fmt_dirs: dict[str, Path] | None, ext: str, root: Path) -> Path:
        if fmt_dirs is None:
            return root
        from app.services.convert_service import LOSSLESS_FORMATS

        return fmt_dirs["lossless" if (ext or "").lower().lstrip(".") in LOSSLESS_FORMATS else "mp3"]


    def _scrape_album_if_missing(
        self,
        meta: dict[str, Any],
        *,
        allow_network: bool = False,
    ) -> dict[str, Any]:
        """Optional network album fill.

        Preview must stay fast: even when allow_network=True we only do a short
        MusicBrainz probe with cleaned title/artist. Prefer dedicated scrape job.
        """
        if not allow_network:
            return meta
        title = clean_title(meta.get("title")) or meta.get("title")
        artist = clean_artist(meta.get("artist")) if meta.get("artist") else meta.get("artist")
        album = meta.get("album")
        if title and title != meta.get("title"):
            meta["title"] = title
        if artist and artist != meta.get("artist"):
            meta["artist"] = artist
        if not title:
            return meta
        # artist optional after cleanup; MB works better with artist but title-only ok
        if artist and is_generic_dir_name(artist):
            artist = None
        if album and not is_generic_dir_name(album):
            return meta
        try:
            # 整理路径只走稳定源（MusicBrainz），避免 musicdl 拖垮预览/应用
            from app.services.scrape.base import ScrapeQuery
            from app.services.scrape.pipeline import ScrapePipeline
            from app.services.scrape.providers.musicbrainz import MusicBrainzProvider

            pipe = ScrapePipeline(
                providers=[MusicBrainzProvider()],
                timeout_per_provider=4.0,
                total_timeout=5.0,
            )
            hit = pipe.lookup(
                ScrapeQuery(
                    title=str(title),
                    artist=str(artist) if artist else None,
                    duration=meta.get("duration"),
                ),
                need_fields={"album", "artist", "title", "duration"},
            )
            found = {}
            if hit:
                if hit.album:
                    found["album"] = hit.album
                if hit.artist:
                    found["artist"] = hit.artist
                if hit.title:
                    found["title"] = hit.title
                if hit.duration:
                    found["duration"] = hit.duration
                found["provider"] = hit.provider
            if found.get("album") and not is_generic_dir_name(found["album"]):
                meta["album"] = found["album"]
                meta["source"] = (meta.get("source") or "") + "+network"
            if found.get("title") and not meta.get("title"):
                meta["title"] = found["title"]
            if found.get("artist") and (not meta.get("artist") or is_generic_dir_name(meta.get("artist"))):
                meta["artist"] = found["artist"]
            if found.get("duration") and not meta.get("duration"):
                meta["duration"] = found["duration"]
            if found.get("album"):
                meta["scraped"] = True
                meta["scrape_provider"] = found.get("provider")
        except Exception:
            meta["scraped"] = False
        return meta

    def list_reorganize_dirs(self, source_id: int, *, relative_dir: str = "") -> dict[str, Any]:
        source = self.get_source(source_id)
        rel = (relative_dir or "").strip().strip("/")
        if source.type == "local":
            root = _source_root_local(source)
            dirs = _list_local_subdirs(root, relative_dir=rel)
            return {
                "source_id": source.id,
                "type": source.type,
                "path": rel,
                "dirs": dirs,
            }
        if source.type == "webdav":
            return self._list_webdav_dirs(source, relative_dir=rel)
        raise ValueError(f"不支持的源类型: {source.type}")

    def preview_reorganize(
        self,
        source_id: int,
        *,
        limit: int = 20,
        relative_dir: str = "",
        include_failed: bool = False,
        allow_network: bool = False,
        relocate_format_dirs: bool = False,
    ) -> dict[str, Any]:
        source = self.get_source(source_id)
        if source.type == "local":
            return self._preview_local(
                source,
                limit=limit,
                relative_dir=relative_dir,
                include_failed=include_failed,
                allow_network=allow_network,
                relocate_format_dirs=relocate_format_dirs,
            )
        if source.type == "webdav":
            return self._preview_webdav(
                source,
                limit=limit,
                relative_dir=relative_dir,
                include_failed=include_failed,
                allow_network=allow_network,
            )
        raise ValueError(f"不支持的源类型: {source.type}")

    def apply_reorganize(
        self,
        source_id: int,
        *,
        limit: int = 20,
        relative_dir: str = "",
        include_failed: bool = False,
        allow_network: bool = False,
        relocate_format_dirs: bool = False,
    ) -> dict[str, Any]:
        source = self.get_source(source_id)
        if source.type == "local":
            result = self._apply_local(
                source,
                limit=limit,
                relative_dir=relative_dir,
                include_failed=include_failed,
                allow_network=allow_network,
                relocate_format_dirs=relocate_format_dirs,
            )
        elif source.type == "webdav":
            result = self._apply_webdav(
                source,
                limit=limit,
                relative_dir=relative_dir,
                include_failed=include_failed,
                allow_network=allow_network,
            )
        else:
            raise ValueError(f"不支持的源类型: {source.type}")
        try:
            write_log(
                self.db,
                action="reorganize",
                target=source.name,
                status="success" if result.get("failed", 0) == 0 else "partial",
                title=f"整理源 #{source.id}",
                message=f"moved={result.get('moved')} failed={result.get('failed')} kept={result.get('kept')}",
                detail={
                    **(result.get("summary") or {}),
                    "relative_dir": (relative_dir or "").strip().strip("/"),
                    "include_failed": bool(include_failed),
                    "limit": int(limit or 0),
                },
                commit=True,
            )
        except Exception:
            pass
        return result

    def _song_by_local(self, source_id: int, path: Path) -> Song | None:
        """Match Song by local_path with NAS-friendly fallbacks.

        Scan stores resolved absolute paths; reorganize walk may produce a different
        string form (symlink, trailing slash, non-resolved). Exact string match alone
        drops DB albums after scrape.
        """
        candidates: list[str] = []
        for cand in (
            str(path),
            path.as_posix(),
            str(path.resolve()) if path.exists() else None,
            path.resolve().as_posix() if path.exists() else None,
        ):
            if cand and cand not in candidates:
                candidates.append(cand)

        q = self.db.query(Song).filter(Song.library_source_id == source_id)
        hit = q.filter(Song.local_path.in_(candidates)).first()
        if hit:
            return hit

        # suffix match: DB path ends with relative tail (Favorite/xxx.flac)
        try:
            name = path.name
            parent = path.parent.name
            suffix = f"{parent}/{name}" if parent else name
        except Exception:
            suffix = path.name
        rows = (
            q.filter(Song.local_path.isnot(None), Song.local_path.like(f"%{path.name}"))
            .limit(30)
            .all()
        )
        for row in rows:
            lp = (row.local_path or "").replace("\\", "/")
            if lp.endswith(path.name) or lp.endswith(suffix.replace("\\", "/")):
                # prefer same parent folder name
                if parent and f"/{parent}/" in f"/{lp}":
                    return row
                if not parent:
                    return row
        for row in rows:
            lp = (row.local_path or "").replace("\\", "/")
            if lp.endswith(path.name):
                return row

        # title+artist fallback from filename
        guess = parse_filename_meta(path)
        title = clean_title(guess.get("title") or path.stem)
        artist = clean_artist(guess.get("artist")) if guess.get("artist") else None
        if title:
            tq = q.filter(Song.title == title)
            if artist:
                tq = tq.filter(Song.artist == artist)
            hit = tq.first()
            if hit:
                return hit
            # loose contains
            hit = q.filter(Song.title.ilike(f"%{title}%")).first()
            if hit:
                return hit
        return None

    def _preview_local(
        self,
        source: MediaSource,
        *,
        limit: int = 20,
        relative_dir: str = "",
        include_failed: bool = False,
        allow_network: bool = False,
        relocate_format_dirs: bool = False,
    ) -> dict[str, Any]:
        import logging
        import time

        log = logging.getLogger("sonpick.reorganize")
        t0 = time.monotonic()
        root = _source_root_local(source)
        fmt_dirs = self._format_base_dirs() if relocate_format_dirs else None
        rel = (relative_dir or "").strip().strip("/")
        # Early-stop walk: only collect up to limit files
        max_files = int(limit) if limit and limit > 0 else 0
        files = _iter_local_audio(
            root,
            relative_dir=rel,
            include_failed=include_failed,
            max_files=max_files,
        )
        scanned = len(files)
        log.info(
            "reorganize preview scan source=%s rel=%s limit=%s files=%s elapsed=%.2fs",
            source.id,
            rel or ".",
            limit,
            scanned,
            time.monotonic() - t0,
        )
        items: list[dict[str, Any]] = []
        for path in files:
            song = self._song_by_local(source.id, path)
            # preview: tags yes, duration no (duration was only for network match)
            meta = _meta_for_local_file(path, song, read_duration=bool(allow_network), read_tags=True)
            meta = self._scrape_album_if_missing(meta, allow_network=allow_network)
            album_missing = _album_missing(meta.get("album"))
            if album_missing:
                log.info(
                    "reorganize skip_no_album path=%s song_id=%s db_album=%r meta_album=%r source=%s",
                    _safe_rel(path, root),
                    getattr(song, "id", None),
                    getattr(song, "album", None) if song else None,
                    meta.get("album"),
                    meta.get("source"),
                )
                items.append(
                    _plan_item(
                        song_id=song.id if song else None,
                        from_path=_safe_rel(path, root),
                        to_path=_safe_rel(path, root),
                        title=str(meta.get("title") or path.stem),
                        artist=meta.get("artist"),
                        album=meta.get("album"),
                        actions=["skip_missing_album"],
                        status="skipped",
                        changed=False,
                        meta_source=(meta.get("source") or "") + "+skip_no_album",
                    )
                )
                continue
            rel_dir = library_relative_dir(meta.get("artist"), meta.get("album"))
            stem = track_stem(meta.get("title"), path.stem)
            target = self._target_base(fmt_dirs, path.suffix, root) / rel_dir / f"{stem}{path.suffix.lower()}"
            actions = []
            if path.resolve() != target.resolve():
                actions.append("move_audio")
                if fmt_dirs is not None:
                    actions.append("relocate_format_dir")
            else:
                actions.append("keep_audio")
            if meta.get("scraped"):
                actions.append("scrape_album")
            if find_lrc_sidecar(path) or meta.get("lyrics"):
                actions.append("sync_lrc")
            if find_track_cover_file(path) or find_album_cover_file(path.parent) or extract_embedded_cover_bytes(path):
                actions.append("sync_cover")
            items.append(
                _plan_item(
                    song_id=song.id if song else None,
                    from_path=_safe_rel(path, root),
                    to_path=_safe_rel(target, root),
                    title=str(meta.get("title") or path.stem),
                    artist=meta.get("artist"),
                    album=meta.get("album"),
                    actions=actions,
                    meta_source=meta.get("source"),
                    duration=meta.get("duration"),
                )
            )
        return {
            "source_id": source.id,
            "source_type": source.type,
            "root": str(root),
            "relative_dir": rel,
            "include_failed": bool(include_failed),
            "allow_network": bool(allow_network),
            "relocate_format_dirs": bool(relocate_format_dirs),
            "limit": int(limit or 0),
            "scanned": scanned,
            "total": len(items),
            "changed": sum(1 for i in items if i["changed"]),
            "skipped": sum(1 for i in items if i.get("status") == "skipped"),
            "items": items,
            "mode": "preview",
            "skip_missing_album": True,
            "elapsed_ms": int((time.monotonic() - t0) * 1000),
        }

    def _apply_local(
        self,
        source: MediaSource,
        *,
        limit: int = 20,
        relative_dir: str = "",
        include_failed: bool = False,
        allow_network: bool = False,
        relocate_format_dirs: bool = False,
    ) -> dict[str, Any]:
        import logging
        import time

        log = logging.getLogger("sonpick.reorganize")
        t0 = time.monotonic()
        root = _source_root_local(source)
        fmt_dirs = self._format_base_dirs() if relocate_format_dirs else None
        rel = (relative_dir or "").strip().strip("/")
        max_files = int(limit) if limit and limit > 0 else 0
        files = _iter_local_audio(
            root,
            relative_dir=rel,
            include_failed=include_failed,
            max_files=max_files,
        )
        log.info(
            "reorganize apply scan source=%s rel=%s limit=%s files=%s elapsed=%.2fs",
            source.id,
            rel or ".",
            limit,
            len(files),
            time.monotonic() - t0,
        )
        results: list[dict[str, Any]] = []
        moved = kept = failed = 0
        failed_root = root / FAILED_DIR_NAME

        for path in list(files):
            song = self._song_by_local(source.id, path)
            original_path = path
            try:
                if not path.is_file():
                    raise FileNotFoundError(str(path))
                meta = _meta_for_local_file(path, song)
                try:
                    resolved = resolve_song_meta(
                        song, audio_path=path, db=self.db, allow_network=False
                    )
                    if resolved.get("artist") and not is_generic_dir_name(resolved["artist"]):
                        meta["artist"] = resolved["artist"]
                    if resolved.get("album") and not is_generic_dir_name(resolved["album"]):
                        meta["album"] = resolved["album"]
                    if resolved.get("title"):
                        meta["title"] = resolved["title"]
                    if resolved.get("lyrics") and not meta.get("lyrics"):
                        meta["lyrics"] = resolved["lyrics"]
                except Exception:
                    pass

                if not meta.get("title"):
                    raise ValueError("缺少标题，无法整理")

                meta = self._scrape_album_if_missing(meta, allow_network=allow_network)
                if _album_missing(meta.get("album")):
                    kept += 1
                    results.append(
                        _plan_item(
                            song_id=song.id if song else None,
                            from_path=_safe_rel(original_path, root),
                            to_path=_safe_rel(original_path, root),
                            title=str(meta.get("title") or path.stem),
                            artist=meta.get("artist"),
                            album=meta.get("album"),
                            actions=["skip_missing_album"],
                            status="skipped",
                            changed=False,
                            meta_source="skip_no_album",
                        )
                    )
                    continue

                rel_dir = library_relative_dir(meta.get("artist"), meta.get("album"))
                stem = track_stem(meta.get("title"), path.stem)
                target = self._target_base(fmt_dirs, path.suffix, root) / rel_dir / f"{stem}{path.suffix.lower()}"

                lrc_src = find_lrc_sidecar(path)
                track_cover = find_track_cover_file(path)
                album_cover = find_album_cover_file(path.parent)
                emb_cover = extract_embedded_cover_bytes(path)
                emb_lyrics = meta.get("lyrics")

                actions: list[str] = []
                if path.resolve() != target.resolve():
                    new_audio = _move_local(path, target)
                    actions.append("moved_audio")
                    if fmt_dirs is not None:
                        actions.append("relocate_format_dir")
                    moved += 1
                else:
                    new_audio = path
                    actions.append("kept_audio")
                    kept += 1

                new_lrc = new_audio.with_suffix(".lrc")
                if lrc_src and lrc_src.is_file():
                    if lrc_src.resolve() != new_lrc.resolve():
                        _move_local(lrc_src, new_lrc)
                        actions.append("moved_lrc")
                elif emb_lyrics:
                    body = str(emb_lyrics).replace("\r\n", "\n").strip()
                    new_lrc.parent.mkdir(parents=True, exist_ok=True)
                    new_lrc.write_text(
                        body + ("\n" if not body.endswith("\n") else ""), encoding="utf-8"
                    )
                    actions.append("wrote_lrc")

                cover_dst = preferred_album_cover_path(new_audio.parent)
                if not cover_dst.is_file():
                    if emb_cover:
                        write_album_cover_file(new_audio.parent, emb_cover)
                        actions.append("wrote_cover")
                    else:
                        side = track_cover or album_cover
                        if side and side.is_file() and side.resolve() != cover_dst.resolve():
                            _copy_local(side, cover_dst)
                            actions.append("copied_cover")

                if song:
                    old_path_candidates = {
                        str(original_path),
                        str(original_path.resolve()),
                        song.local_path or "",
                    }
                    song.local_path = str(new_audio)
                    song.title = str(meta.get("title") or song.title)
                    if meta.get("artist") and not is_generic_dir_name(meta["artist"]):
                        song.artist = meta["artist"]
                    elif song.artist and is_generic_dir_name(song.artist):
                        song.artist = None
                    if meta.get("album") and not is_generic_dir_name(meta["album"]):
                        song.album = meta["album"]
                    elif song.album and is_generic_dir_name(song.album):
                        song.album = None
                    if new_lrc.is_file():
                        song.lrc_path = str(new_lrc)
                    if cover_dst.is_file():
                        song.cover_path = str(cover_dst)
                    self.db.add(song)
                    _sync_song_file_path(self.db, song, old_path_candidates, new_audio)

                results.append(
                    _plan_item(
                        song_id=song.id if song else None,
                        from_path=_safe_rel(original_path, root),
                        to_path=_safe_rel(new_audio, root),
                        title=str(meta.get("title")),
                        artist=meta.get("artist"),
                        album=meta.get("album"),
                        actions=actions,
                        status="ok",
                    )
                )
            except Exception as e:
                failed += 1
                fail_target = None
                try:
                    try:
                        rel = original_path.relative_to(root)
                    except Exception:
                        rel = Path(original_path.name)
                    fail_target = failed_root / rel
                    if original_path.is_file():
                        fail_target = _move_local(original_path, fail_target)
                    for side in (find_lrc_sidecar(original_path), find_track_cover_file(original_path)):
                        if side and side.is_file():
                            try:
                                _move_local(side, fail_target.parent / side.name)
                            except Exception:
                                pass
                    try:
                        note = Path(str(fail_target) + ".error.txt")
                        note.parent.mkdir(parents=True, exist_ok=True)
                        note.write_text(f"{e}\n\n{traceback.format_exc()}", encoding="utf-8")
                    except Exception:
                        pass
                except Exception:
                    pass
                results.append(
                    _plan_item(
                        song_id=song.id if song else None,
                        from_path=str(original_path),
                        to_path=str(fail_target) if fail_target else "",
                        title=original_path.stem,
                        artist=None,
                        album=None,
                        actions=["moved_to_failed"],
                        status="failed",
                        error=str(e),
                    )
                )
                if song and fail_target and Path(str(fail_target)).exists():
                    _sync_song_file_path(
                        self.db,
                        song,
                        {str(original_path), str(original_path.resolve()), song.local_path or ""},
                        Path(str(fail_target)),
                    )
                    song.local_path = str(fail_target)
                    self.db.add(song)

        self.db.commit()
        return {
            "source_id": source.id,
            "source_type": source.type,
            "root": str(root),
            "relative_dir": rel,
            "include_failed": bool(include_failed),
            "relocate_format_dirs": bool(relocate_format_dirs),
            "limit": int(limit or 0),
            "mode": "apply",
            "total": len(results),
            "moved": moved,
            "kept": kept,
            "failed": failed,
            "skipped": sum(1 for i in results if i.get("status") == "skipped"),
            "items": results,
            "summary": {"moved": moved, "kept": kept, "failed": failed, "skipped": sum(1 for i in results if i.get("status") == "skipped")},
        }

    def _list_webdav_dirs(self, source: MediaSource, *, relative_dir: str = "") -> dict[str, Any]:
        from app.services.webdav_service import WebDAVService

        rel = (relative_dir or "").strip().strip("/")
        ws = WebDAVService(db=self.db, source_id=source.id)
        try:
            entries = ws.list(rel)
        except Exception as exc:
            raise ValueError(f"列出 WebDAV 目录失败: {exc}") from exc
        dirs: list[dict[str, Any]] = []
        for entry in entries or []:
            if not entry.get("is_dir"):
                continue
            name = str(entry.get("name") or "").strip()
            path = str(entry.get("path") or "").strip().strip("/")
            if not name or name.startswith("."):
                continue
            if name.lower() in SKIP_DIR_NAMES and name.lower() != FAILED_DIR_NAME.lower():
                continue
            dirs.append({"name": name, "path": path or name})
        dirs.sort(key=lambda x: x["name"].lower())
        return {
            "source_id": source.id,
            "type": source.type,
            "path": rel,
            "dirs": dirs,
        }

    def _preview_webdav(
        self,
        source: MediaSource,
        *,
        limit: int = 20,
        relative_dir: str = "",
        include_failed: bool = False,
        allow_network: bool = False,
    ) -> dict[str, Any]:
        rel = (relative_dir or "").strip().strip("/")
        q = (
            self.db.query(Song)
            .filter(Song.library_source_id == source.id, Song.webdav_path.isnot(None))
            .order_by(Song.id.asc())
        )
        songs = q.all()
        items: list[dict[str, Any]] = []
        for song in songs:
            remote = (song.webdav_path or "").lstrip("/")
            if not remote:
                continue
            parts = remote.split("/")
            if parts and parts[0].lower() == FAILED_DIR_NAME.lower() and not include_failed:
                continue
            if rel:
                if not (remote == rel or remote.startswith(rel + "/")):
                    continue
            title = song.title or Path(remote).stem
            artist = song.artist if not is_generic_dir_name(song.artist) else None
            album = song.album if not is_generic_dir_name(song.album) else None
            guess = parse_filename_meta(Path(remote))
            if not artist:
                artist = guess.get("artist")
            if (not title or title == Path(remote).stem) and guess.get("title"):
                title = guess.get("title") or title
            meta = {
                "title": title,
                "artist": artist,
                "album": album,
                "duration": song.duration,
                "source": "db" if song.artist or song.album else "path",
            }
            meta = self._scrape_album_if_missing(meta, allow_network=allow_network)
            title, artist, album = meta.get("title"), meta.get("artist"), meta.get("album")
            if _album_missing(album):
                items.append(
                    _plan_item(
                        song_id=song.id,
                        from_path=remote,
                        to_path=remote,
                        title=title,
                        artist=artist,
                        album=album,
                        actions=["skip_missing_album"],
                        status="skipped",
                        changed=False,
                        meta_source="skip_no_album",
                    )
                )
                continue
            rel_dir = library_relative_dir(artist, album)
            stem = track_stem(title, Path(remote).stem)
            ext = Path(remote).suffix.lower() or ".mp3"
            to_path = f"{rel_dir.as_posix()}/{stem}{ext}"
            actions = ["move_remote_audio"] if remote != to_path else ["keep_remote_audio"]
            actions.append("sync_remote_sidecars")
            items.append(
                _plan_item(
                    song_id=song.id,
                    from_path=remote,
                    to_path=to_path,
                    title=title,
                    artist=artist,
                    album=album,
                    actions=actions,
                )
            )
        scanned = len(items)
        if limit and limit > 0:
            items = items[:limit]
        return {
            "source_id": source.id,
            "source_type": source.type,
            "root": source.webdav_url or "",
            "relative_dir": rel,
            "include_failed": bool(include_failed),
            "limit": int(limit or 0),
            "scanned": scanned,
            "total": len(items),
            "changed": sum(1 for i in items if i["changed"]),
            "skipped": sum(1 for i in items if i.get("status") == "skipped"),
            "items": items,
            "mode": "preview",
            "skip_missing_album": True,
            "note": "WebDAV 整理基于已入库歌曲的 webdav_path 与元数据；缺专辑默认跳过，请先刮削。",
        }

    def _apply_webdav(
        self,
        source: MediaSource,
        *,
        limit: int = 20,
        relative_dir: str = "",
        include_failed: bool = False,
        allow_network: bool = False,
    ) -> dict[str, Any]:
        from app.services.webdav_service import WebDAVService

        preview = self._preview_webdav(
            source,
            limit=limit,
            relative_dir=relative_dir,
            include_failed=include_failed,
            allow_network=allow_network,
        )
        ws = WebDAVService(db=self.db, source_id=source.id)
        results: list[dict[str, Any]] = []
        moved = kept = failed = 0

        for item in preview.get("items") or []:
            song = self.db.get(Song, item["song_id"]) if item.get("song_id") else None
            src = item["from_path"]
            dst = item["to_path"]
            try:
                if src == dst:
                    kept += 1
                    results.append({**item, "status": "ok", "actions": ["kept_remote_audio"]})
                    continue
                ws.move_path(src, dst)
                src_stem = src.rsplit(".", 1)[0]
                dst_parent = "/".join(dst.split("/")[:-1])
                dst_stem = dst.rsplit(".", 1)[0]
                for ext in (".lrc", ".txt"):
                    side_src = src_stem + ext
                    try:
                        if ws.exists_path(side_src):
                            ws.move_path(side_src, dst_stem + ext)
                    except Exception:
                        pass
                for cname in ("cover.jpg", "folder.jpg", "front.jpg"):
                    csrc = f"{old_parent}/{cname}" if (old_parent := "/".join(src.split("/")[:-1])) else cname
                    cdst = f"{dst_parent}/cover.jpg" if dst_parent else "cover.jpg"
                    try:
                        if ws.exists_path(csrc) and not ws.exists_path(cdst):
                            ws.copy_path(csrc, cdst)
                            break
                    except Exception:
                        pass

                if song:
                    song.webdav_path = dst
                    if item.get("title"):
                        song.title = item["title"]
                    if item.get("artist") and not is_generic_dir_name(item["artist"]):
                        song.artist = item["artist"]
                    if item.get("album") and not is_generic_dir_name(item["album"]):
                        song.album = item["album"]
                    self.db.add(song)
                moved += 1
                results.append({**item, "status": "ok", "actions": ["moved_remote_audio"]})
            except Exception as e:
                failed += 1
                fail_path = f"{FAILED_DIR_NAME}/{src}"
                try:
                    ws.move_path(src, fail_path)
                    if song:
                        song.webdav_path = fail_path
                        self.db.add(song)
                except Exception:
                    fail_path = src
                results.append(
                    {
                        **item,
                        "status": "failed",
                        "error": str(e),
                        "to_path": fail_path,
                        "actions": ["moved_to_failed"],
                    }
                )

        self.db.commit()
        return {
            "source_id": source.id,
            "source_type": source.type,
            "root": source.webdav_url or "",
            "relative_dir": (relative_dir or "").strip().strip("/"),
            "include_failed": bool(include_failed),
            "limit": int(limit or 0),
            "mode": "apply",
            "total": len(results),
            "moved": moved,
            "kept": kept,
            "failed": failed,
            "items": results,
            "summary": {"moved": moved, "kept": kept, "failed": failed},
        }

    def scrape_songs(
        self,
        *,
        source_id: int | None = None,
        song_ids: list[int] | None = None,
        allow_network: bool = False,
        overwrite: bool = False,
        limit: int = 20,
    ) -> dict[str, Any]:
        q = self.db.query(Song)
        if source_id is not None:
            q = q.filter(Song.library_source_id == source_id)
        if song_ids:
            q = q.filter(Song.id.in_(song_ids))
        q = q.order_by(Song.id.asc())
        songs = q.limit(limit).all() if limit and limit > 0 else q.all()

        from app.services.scrape import enrich_song_via_pipeline

        updated = skipped = failed = 0
        details: list[dict[str, Any]] = []

        for song in songs:
            try:
                changes: dict[str, Any] = {}
                meta = resolve_song_meta(
                    song,
                    audio_path=song.local_path if is_local_file(song.local_path) else None,
                    db=self.db,
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
                    if overwrite or not cur or (key in ("artist", "album") and is_generic_dir_name(cur)):
                        if str(cur or "") != str(val):
                            setattr(song, key, val)
                            changes[key] = val

                if allow_network:
                    filled = enrich_song_via_pipeline(
                        song,
                        db=self.db,
                        timeout_per_provider=8.0,
                        total_timeout=20.0,
                    ) or {}
                    for key, val in (filled.items() if isinstance(filled, dict) else []):
                        if key == "provider":
                            changes["provider"] = val
                            continue
                        if val is not None:
                            changes[key] = val

                # clean generic junk if we now have better data
                if song.artist and is_generic_dir_name(song.artist):
                    song.artist = None
                    changes["artist"] = None
                if song.album and is_generic_dir_name(song.album):
                    song.album = None
                    changes["album"] = None

                if changes:
                    self.db.add(song)
                    updated += 1
                    details.append(
                        {
                            "song_id": song.id,
                            "title": song.title,
                            "status": "updated",
                            "changes": changes,
                        }
                    )
                else:
                    skipped += 1
                    details.append({"song_id": song.id, "title": song.title, "status": "skipped"})
            except Exception as e:
                failed += 1
                details.append(
                    {
                        "song_id": song.id,
                        "title": getattr(song, "title", None),
                        "status": "failed",
                        "error": str(e),
                    }
                )

        self.db.commit()
        try:
            write_log(
                self.db,
                action="scrape",
                target=f"source:{source_id}" if source_id else "songs",
                status="success" if failed == 0 else "partial",
                title="刮削元数据",
                message=f"updated={updated} skipped={skipped} failed={failed}",
                detail={"updated": updated, "skipped": skipped, "failed": failed},
                commit=True,
            )
        except Exception:
            pass

        return {
            "total": len(songs),
            "updated": updated,
            "skipped": skipped,
            "failed": failed,
            "items": details[:200],
            "allow_network": allow_network,
            "overwrite": overwrite,
            "providers": ["musicbrainz", "musicdl"],
        }
