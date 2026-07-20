#!/usr/bin/env python3
"""整理曲库到「艺术家/专辑/歌名」规范目录（可独立在 NAS 上运行）。

目录规范
--------
  艺术家/
    artist.jpg
    专辑/
      cover.jpg
      歌名.flac
      歌名.lrc

默认行为
--------
- 曲库根目录 = **本脚本所在目录**（可用 --root / -r 覆盖）
- 只整理磁盘文件，**不依赖** Sonpick 应用、数据库
- dry-run（只打印计划）；加 --apply 才真正移动

依赖
----
- 必选：Python 3.9+ 标准库
- 强烈建议：``pip install mutagen``（读内嵌标签/封面/歌词）
- 可选：在 Sonpick 项目环境加 ``--with-db`` 同步更新数据库
- 可选：``--with-db --enrich`` 用 musicdl 网络补全（需完整项目依赖）

NAS 用法示例
------------
  # 把本脚本拷到音乐根目录，例如 /share/Music/
  cd /share/Music
  python3 reorganize_library.py                 # dry-run
  python3 reorganize_library.py --apply         # 真正整理

  # 或指定根目录
  python3 reorganize_library.py -r /share/Music --apply

  # 在 Sonpick 项目里顺带更新 DB
  python3 scripts/reorganize_library.py -r ./downloads --with-db --apply
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Iterable, Optional

# ---------------------------------------------------------------------------
# 内置规范（独立运行时不 import app）
# ---------------------------------------------------------------------------

AUDIO_EXTS = {".mp3", ".flac", ".m4a", ".wav", ".ogg", ".aac", ".ape", ".wma", ".opus"}
LRC_EXTS = {".lrc", ".txt"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

ALBUM_COVER_NAMES = (
    "cover.jpg",
    "cover.jpeg",
    "cover.png",
    "cover.webp",
    "folder.jpg",
    "folder.jpeg",
    "folder.png",
    "Folder.jpg",
    "front.jpg",
    "front.png",
    "AlbumArt.jpg",
    "AlbumArtSmall.jpg",
    "albumart.jpg",
    "album.jpg",
    "Album.jpg",
)

ARTIST_IMAGE_NAMES = (
    "artist.jpg",
    "artist.jpeg",
    "artist.png",
    "artist.webp",
    "Artist.jpg",
    "folder.jpg",
    "folder.png",
    "Folder.jpg",
)

GENERIC_DIR_NAMES = frozenset(
    {
        "music",
        "songs",
        "audio",
        "download",
        "downloads",
        "flac",
        "mp3",
        "m4a",
        "wav",
        "media",
        "library",
        "music library",
        "musiclibrary",
        "favorite",
        "favorites",
        "favourite",
        "favourites",
        "liked",
        "liked songs",
        "all",
        "misc",
        "various",
        "various artists",
        "va",
        "inbox",
        "import",
        "imports",
        "new",
        "temp",
        "tmp",
        "cache",
        "shared",
        "public",
        "data",
        "storage",
        "unknown",
        "unknown artist",
        "unknown album",
        "未知",
        "未知艺术家",
        "未知专辑",
        ".musicdl_work",
        "covers",
    }
)

UNKNOWN_ARTIST = "Unknown Artist"
UNKNOWN_ALBUM = "Unknown Album"

SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".svn",
        ".hg",
        "__pycache__",
        ".musicdl_work",
        "node_modules",
        ".venv",
        "venv",
        "covers",
        "@eaDir",  # QNAP
        "#recycle",
        ".DS_Store",
    }
)

SCRIPT_DIR = Path(__file__).resolve().parent


def sanitize_component(name: Optional[str], fallback: str, *, max_len: int = 120) -> str:
    s = (name or "").strip() or fallback
    for ch in '\\/:*?"<>|\r\n\t':
        s = s.replace(ch, "_")
    s = s.strip(" .")
    if s.upper() in {"CON", "PRN", "AUX", "NUL", "COM1", "LPT1"}:
        s = f"_{s}"
    return (s or fallback)[:max_len]


def is_generic_dir_name(name: Optional[str]) -> bool:
    if not name:
        return True
    s = str(name).strip().lower()
    if not s or s in GENERIC_DIR_NAMES:
        return True
    if s.startswith("playlist") or s.endswith(" playlist"):
        return True
    return False


def artist_dir_name(artist: Optional[str]) -> str:
    if is_generic_dir_name(artist):
        return UNKNOWN_ARTIST
    return sanitize_component(artist, UNKNOWN_ARTIST)


def album_dir_name(album: Optional[str]) -> str:
    if is_generic_dir_name(album):
        return UNKNOWN_ALBUM
    return sanitize_component(album, UNKNOWN_ALBUM)


def track_stem(title: Optional[str], fallback: str = "track") -> str:
    return sanitize_component(title, fallback, max_len=160)


def library_relative_dir(artist: Optional[str], album: Optional[str]) -> Path:
    return Path(artist_dir_name(artist)) / album_dir_name(album)


def preferred_album_cover_path(album_dir: Path) -> Path:
    return album_dir / "cover.jpg"


def preferred_artist_image_path(artist_dir: Path) -> Path:
    return artist_dir / "artist.jpg"


def _first_tag_value(tags, keys) -> Optional[str]:
    if not tags:
        return None
    for key in keys:
        val = None
        try:
            if hasattr(tags, "get"):
                val = tags.get(key)
            if val is None and hasattr(tags, "getall"):
                try:
                    vals = tags.getall(key)
                    if vals:
                        val = vals[0]
                except Exception:
                    pass
        except Exception:
            val = None
        if val is None:
            continue
        try:
            if hasattr(val, "text") and val.text:
                s = str(val.text[0]).strip()
                if s:
                    return s
            if isinstance(val, (list, tuple)) and val:
                item = val[0]
                if hasattr(item, "text") and item.text:
                    s = str(item.text[0]).strip()
                    if s:
                        return s
                s = str(item).strip()
                if s:
                    return s
            s = str(val).strip()
            if s and s.lower() not in {"none", "null"}:
                return s
        except Exception:
            continue
    return None


def _clean_meta(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"none", "null", "unknown", "未知", "未知艺术家", "未知专辑"}:
        return None
    if is_generic_dir_name(s):
        return None
    return s


def read_audio_tags(path: Path) -> dict[str, Optional[str]]:
    """内嵌标签：需要 mutagen；没有则返回空字段。"""
    out: dict[str, Optional[str]] = {
        "title": None,
        "artist": None,
        "album": None,
        "lyrics": None,
    }
    try:
        from mutagen import File as MutagenFile  # type: ignore
    except Exception:
        return out

    try:
        audio = MutagenFile(str(path), easy=False)
        if audio is None:
            return out
        tags = getattr(audio, "tags", None) or audio
        out["title"] = _clean_meta(
            _first_tag_value(tags, ["TIT2", "TITLE", "\xa9nam", "title"])
        )
        out["artist"] = _clean_meta(
            _first_tag_value(
                tags,
                ["TPE1", "ARTIST", "\xa9ART", "artist", "ALBUMARTIST", "TPE2", "albumartist"],
            )
        )
        out["album"] = _clean_meta(
            _first_tag_value(tags, ["TALB", "ALBUM", "\xa9alb", "album"])
        )
        lyrics = None
        try:
            if hasattr(tags, "getall"):
                for frame in tags.getall("USLT") or []:
                    text = getattr(frame, "text", None)
                    if text:
                        lyrics = str(text).strip()
                        break
            if not lyrics:
                lyrics = _first_tag_value(
                    tags, ["USLT", "LYRICS", "\xa9lyr", "lyrics", "UNSYNCEDLYRICS"]
                )
        except Exception:
            lyrics = None
        if lyrics and str(lyrics).strip():
            out["lyrics"] = str(lyrics).strip()
    except Exception:
        pass
    return out


def extract_embedded_cover_bytes(path: Path) -> Optional[bytes]:
    try:
        from mutagen import File as MutagenFile  # type: ignore
    except Exception:
        return None
    try:
        audio = MutagenFile(str(path))
        if audio is None:
            return None
        tags = getattr(audio, "tags", None)
        if tags is None:
            return None
        if hasattr(tags, "getall"):
            for pic in tags.getall("APIC") or []:
                data = getattr(pic, "data", None)
                if data:
                    return bytes(data)
        pictures = getattr(audio, "pictures", None)
        if pictures:
            data = getattr(pictures[0], "data", None)
            if data:
                return bytes(data)
        if hasattr(tags, "get"):
            covr = tags.get("covr")
            if covr:
                item = covr[0] if isinstance(covr, list) else covr
                if isinstance(item, (bytes, bytearray)):
                    return bytes(item)
                data = getattr(item, "data", None)
                if data:
                    return bytes(data)
    except Exception:
        return None
    return None


def parse_meta_from_path(path: Path, root: Path) -> dict[str, Optional[str]]:
    """弱路径启发：仅当目录不像收藏夹时才当 Artist/Album。"""
    stem = path.stem.strip()
    title = stem
    artist = None
    album = None

    for sep in (" - ", " – ", " — ", "_-", " | "):
        if sep in stem:
            left, right = stem.split(sep, 1)
            left_s, right_s = left.strip(), right.strip()
            if left_s and right_s:
                # "01 - Title" / "1. Title" style: track number, not artist
                if re.fullmatch(r"\d{1,3}[.)]?", left_s):
                    title = right_s
                else:
                    artist = _clean_meta(left_s)
                    title = right_s
                break

    title = re.sub(r"^\s*\d{1,3}[\s._-]+", "", title).strip() or stem

    try:
        rel = path.parent.resolve().relative_to(root.resolve())
        parts = [p for p in rel.parts if p not in (".",)]
    except Exception:
        parts = [path.parent.name] if path.parent else []

    parts = [p for p in parts if not is_generic_dir_name(p) and p not in SKIP_DIR_NAMES]

    if len(parts) >= 2:
        if artist is None:
            artist = _clean_meta(parts[-2])
        album = _clean_meta(parts[-1])
    elif len(parts) == 1 and artist is None:
        album = _clean_meta(parts[0])

    return {"title": title, "artist": artist, "album": album}


def find_lrc_sidecar(audio: Path) -> Optional[Path]:
    for ext in (".lrc", ".LRC", ".txt", ".TXT"):
        for cand in (audio.with_suffix(ext), Path(str(audio.with_suffix("")) + ext)):
            if cand.is_file():
                return cand
    try:
        stem_low = audio.stem.lower()
        fuzzy: list[Path] = []
        for child in audio.parent.iterdir():
            if not child.is_file():
                continue
            low = child.name.lower()
            if not low.endswith((".lrc", ".txt")):
                continue
            cstem = child.stem.lower()
            if cstem == stem_low or stem_low in cstem or cstem in stem_low:
                fuzzy.append(child)
        fuzzy.sort(
            key=lambda c: (
                0 if c.suffix.lower() == ".lrc" else 1,
                abs(len(c.stem) - len(audio.stem)),
                c.name,
            )
        )
        if fuzzy:
            return fuzzy[0]
    except Exception:
        pass
    return None


def find_album_cover_file(album_dir: Path) -> Optional[Path]:
    if not album_dir.is_dir():
        return None
    for name in ALBUM_COVER_NAMES:
        p = album_dir / name
        if p.is_file():
            return p
    try:
        wanted = {n.lower() for n in ALBUM_COVER_NAMES}
        for child in album_dir.iterdir():
            if child.is_file() and child.name.lower() in wanted:
                return child
    except Exception:
        pass
    return None


def find_track_cover_file(audio: Path) -> Optional[Path]:
    for ext in IMAGE_EXTS:
        for cand in (Path(str(audio.with_suffix("")) + ext), audio.with_suffix(ext)):
            if cand.is_file():
                return cand
    return None


def find_artist_image_file(artist_dir: Path) -> Optional[Path]:
    if not artist_dir.is_dir():
        return None
    for name in ARTIST_IMAGE_NAMES:
        p = artist_dir / name
        if p.is_file():
            return p
    return None


def resolve_meta_for_file(path: Path, root: Path) -> dict[str, Any]:
    path_meta = parse_meta_from_path(path, root)
    tags = read_audio_tags(path)
    title = tags.get("title") or path_meta.get("title") or path.stem
    artist = tags.get("artist") or path_meta.get("artist")
    album = tags.get("album") or path_meta.get("album")
    if is_generic_dir_name(artist):
        artist = tags.get("artist")
        if is_generic_dir_name(artist):
            artist = None
    if is_generic_dir_name(album):
        album = tags.get("album")
        if is_generic_dir_name(album):
            album = None
    return {
        "title": title,
        "artist": artist,
        "album": album,
        "lyrics": tags.get("lyrics"),
        "tag_source": "mutagen" if any(tags.values()) else "path",
    }


def iter_audio_files(root: Path) -> Iterable[Path]:
    root = root.resolve()
    skip_lower = {x.lower() for x in SKIP_DIR_NAMES}
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in AUDIO_EXTS:
            continue
        try:
            rel_parts = p.relative_to(root).parts
        except Exception:
            continue
        # skip work / system dirs in intermediate path
        mid = rel_parts[:-1]
        if any(part.lower() in skip_lower for part in mid):
            continue
        if any(part.startswith(".") for part in mid):
            continue
        yield p


def _move_file(src: Path, dst: Path, apply: bool) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.resolve() == dst.resolve():
        return dst
    if dst.exists():
        stem, ext = dst.stem, dst.suffix
        i = 1
        while True:
            cand = dst.with_name(f"{stem}_{i}{ext}")
            if not cand.exists():
                dst = cand
                break
            i += 1
    if apply:
        shutil.move(str(src), str(dst))
    return dst


def _copy_if_needed(src: Path, dst: Path, apply: bool) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return dst
    if apply and src.is_file():
        shutil.copy2(str(src), str(dst))
    return dst


def reorganize_file(src_audio: Path, root: Path, apply: bool) -> dict[str, Any]:
    plan: dict[str, Any] = {
        "from": str(src_audio),
        "actions": [],
        "skipped": None,
        "to": None,
        "meta": None,
    }
    if not src_audio.is_file():
        plan["skipped"] = "missing_file"
        return plan

    meta = resolve_meta_for_file(src_audio, root)
    title = meta["title"]
    artist = meta["artist"]
    album = meta["album"]
    rel_dir = library_relative_dir(artist, album)
    target_dir = root / rel_dir
    stem = track_stem(title, src_audio.stem)
    ext = src_audio.suffix.lower() or ".mp3"
    target_audio = target_dir / f"{stem}{ext}"

    plan["meta"] = {
        "title": title,
        "artist": artist or UNKNOWN_ARTIST,
        "album": album or UNKNOWN_ALBUM,
        "source": meta.get("tag_source"),
    }
    plan["to"] = str(target_audio)

    lrc_src = find_lrc_sidecar(src_audio)
    track_cover = find_track_cover_file(src_audio)
    album_cover = find_album_cover_file(src_audio.parent)
    artist_img = None
    try:
        if src_audio.parent.parent and src_audio.parent.parent != root:
            artist_img = find_artist_image_file(src_audio.parent.parent)
    except Exception:
        pass

    if src_audio.resolve() != target_audio.resolve():
        plan["actions"].append(f"MOVE audio -> {rel_dir.as_posix()}/{target_audio.name}")
        new_audio = _move_file(src_audio, target_audio, apply)
    else:
        new_audio = src_audio
        plan["actions"].append("KEEP audio (already laid out)")

    new_lrc = new_audio.with_suffix(".lrc")
    if lrc_src and lrc_src.is_file():
        if lrc_src.resolve() != new_lrc.resolve():
            plan["actions"].append(f"MOVE lrc -> {rel_dir.as_posix()}/{new_lrc.name}")
            _move_file(lrc_src, new_lrc, apply)
        else:
            plan["actions"].append("KEEP lrc")
    elif meta.get("lyrics"):
        plan["actions"].append(f"WRITE embedded lyrics -> {new_lrc.name}")
        if apply:
            body = str(meta["lyrics"]).replace("\r\n", "\n").strip()
            new_lrc.parent.mkdir(parents=True, exist_ok=True)
            new_lrc.write_text(
                body + ("\n" if not body.endswith("\n") else ""), encoding="utf-8"
            )
    else:
        plan["actions"].append("NO lrc")

    track_cover_dst = new_audio.with_suffix(track_cover.suffix.lower()) if track_cover else None
    if track_cover and track_cover.is_file() and track_cover_dst and track_cover.resolve() != track_cover_dst.resolve():
        plan["actions"].append(f"MOVE track cover -> {rel_dir.as_posix()}/{track_cover_dst.name}")
        _move_file(track_cover, track_cover_dst, apply)

    cover_dst = preferred_album_cover_path(new_audio.parent)
    if cover_dst.is_file() or (not apply and find_album_cover_file(new_audio.parent)):
        plan["actions"].append("KEEP cover.jpg")
    else:
        data = extract_embedded_cover_bytes(new_audio if new_audio.exists() else src_audio)
        if data:
            plan["actions"].append("WRITE cover.jpg from embedded")
            if apply:
                cover_dst.parent.mkdir(parents=True, exist_ok=True)
                cover_dst.write_bytes(data)
        else:
            side = track_cover or album_cover
            if side and side.is_file():
                plan["actions"].append(f"COPY cover.jpg from {side.name}")
                _copy_if_needed(side, cover_dst, apply)
            else:
                plan["actions"].append("NO cover")

    dst_artist_dir = new_audio.parent.parent
    art_dst = preferred_artist_image_path(dst_artist_dir)
    if (
        artist_img
        and artist_img.is_file()
        and not art_dst.exists()
        and not find_artist_image_file(dst_artist_dir)
    ):
        plan["actions"].append(f"COPY artist.jpg from {artist_img.name}")
        _copy_if_needed(artist_img, art_dst, apply)

    return plan


def _try_project_root() -> Optional[Path]:
    here = Path(__file__).resolve().parent
    if (here.parent / "app" / "main.py").is_file():
        return here.parent
    cwd = Path.cwd()
    if (cwd / "app" / "main.py").is_file():
        return cwd
    return None


def sync_db_paths(
    root: Path,
    plans: list[dict[str, Any]],
    *,
    apply: bool,
    enrich: bool,
    source_id: Optional[int],
) -> None:
    project = _try_project_root()
    if not project:
        print("[with-db] 未找到 Sonpick 项目根（需含 app/main.py），跳过数据库同步", file=sys.stderr)
        return
    if str(project) not in sys.path:
        sys.path.insert(0, str(project))

    try:
        from app.database import SessionLocal, init_db
        from app.models import Song
    except Exception as e:
        print(f"[with-db] 导入 app 失败: {e}", file=sys.stderr)
        return

    init_db()
    db = SessionLocal()
    try:
        moved_map = {}
        for plan in plans:
            if plan.get("skipped") or not plan.get("to"):
                continue
            moved_map[str(Path(plan["from"]).resolve())] = plan

        q = db.query(Song).filter(Song.local_path.isnot(None))
        if source_id is not None:
            q = q.filter(Song.library_source_id == source_id)
        songs = q.all()
        updated = 0
        for song in songs:
            if not song.local_path:
                continue
            try:
                key = str(Path(song.local_path).resolve())
            except Exception:
                key = song.local_path
            plan = moved_map.get(key)
            if not plan:
                continue
            if enrich:
                try:
                    from app.services.media_meta_service import resolve_song_meta

                    resolve_song_meta(song, db=db, allow_network=True, force=False)
                except Exception as e:
                    print(f"[enrich] song#{song.id} failed: {e}", file=sys.stderr)
            if apply:
                song.local_path = plan["to"]
                m = plan.get("meta") or {}
                if m.get("title"):
                    song.title = m["title"]
                if m.get("artist") and not is_generic_dir_name(m["artist"]):
                    song.artist = m["artist"]
                if m.get("album") and not is_generic_dir_name(m["album"]):
                    song.album = m["album"]
                new_lrc = Path(plan["to"]).with_suffix(".lrc")
                if new_lrc.is_file():
                    song.lrc_path = str(new_lrc)
                cover = preferred_album_cover_path(Path(plan["to"]).parent)
                if cover.is_file():
                    song.cover_path = str(cover)
                db.add(song)
                updated += 1
        if apply:
            db.commit()
            print(f"[with-db] updated songs={updated}")
        else:
            print(f"[with-db dry-run] would update songs≈{len(moved_map)}")
    finally:
        db.close()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="整理音乐目录为 艺术家/专辑/歌名（默认可独立运行）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "依赖:\n"
            "  标准库必选；强烈建议 pip install mutagen\n"
            "  --with-db 需要 Sonpick 项目环境\n"
            "  --enrich 需要 --with-db 且 musicdl 可用\n"
        ),
    )
    parser.add_argument(
        "-r",
        "--root",
        type=str,
        default=None,
        help="曲库根目录（默认：本脚本所在目录）",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真正移动/写入文件（默认仅 dry-run）",
    )
    parser.add_argument(
        "--with-db",
        action="store_true",
        help="同步更新 Sonpick 数据库中的 Song 路径（需项目环境）",
    )
    parser.add_argument(
        "--enrich",
        action="store_true",
        help="网络补全元数据（仅 --with-db 时有效）",
    )
    parser.add_argument(
        "--source-id",
        type=int,
        default=None,
        help="--with-db 时仅更新指定 library_source_id",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="最多处理 N 个音频文件（0=全部）",
    )
    parser.add_argument(
        "--storage-path",
        type=str,
        default=None,
        help="兼容旧参数，等同于 --root",
    )
    args = parser.parse_args(argv)

    root_arg = args.root or args.storage_path
    root = Path(root_arg).expanduser().resolve() if root_arg else SCRIPT_DIR
    if not root.is_dir():
        print(f"[ERROR] 根目录不存在: {root}", file=sys.stderr)
        return 2

    try:
        import mutagen  # noqa: F401

        has_mutagen = True
    except Exception:
        has_mutagen = False

    if args.enrich and not args.with_db:
        print("[WARN] --enrich 需要同时指定 --with-db，已忽略 enrich", file=sys.stderr)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] root={root}")
    print(f"  mutagen: {'yes' if has_mutagen else 'NO (建议: pip install mutagen)'}")
    print(f"  with-db: {args.with_db}  enrich: {args.enrich and args.with_db}")

    files = list(iter_audio_files(root))
    files.sort(key=lambda p: str(p).lower())
    if args.limit and args.limit > 0:
        files = files[: args.limit]

    print(f"  audio files: {len(files)}")

    plans: list[dict[str, Any]] = []
    moved = 0
    skipped = 0
    for audio in files:
        plan = reorganize_file(audio, root, apply=args.apply)
        plans.append(plan)
        if plan.get("skipped"):
            skipped += 1
            print(f"- skip {plan.get('from')}: {plan['skipped']}")
            continue
        moved += 1
        m = plan.get("meta") or {}
        print(f"- {m.get('artist')} / {m.get('album')} / {m.get('title')}  [{m.get('source')}]")
        print(f"    from: {plan.get('from')}")
        print(f"    to:   {plan.get('to')}")
        for a in plan.get("actions") or []:
            print(f"    · {a}")

    if args.with_db:
        sync_db_paths(
            root,
            plans,
            apply=args.apply,
            enrich=bool(args.enrich and args.with_db),
            source_id=args.source_id,
        )

    if args.apply:
        print(f"[DONE] processed={moved} skipped={skipped}")
    else:
        print(f"[DRY-RUN DONE] planned={moved} skipped={skipped}")
        print(f"确认后执行: python3 {Path(__file__).name} -r '{root}' --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
