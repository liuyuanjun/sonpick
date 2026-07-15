from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

import time
from app.config import get_settings
from app.services.library_layout import (
    find_album_cover_file,
    find_lrc_sidecar,
    find_track_cover_file,
    is_generic_dir_name,
    library_relative_dir,
    preferred_album_cover_path,
)

# song_id -> expire_ts for cover miss (avoid concurrent WebDAV stampede)
_COVER_MISS_CACHE: dict[int, float] = {}
_COVER_MISS_TTL = 120.0

AUDIO_EXTS = {".mp3", ".flac", ".m4a", ".wav", ".ogg", ".aac", ".ape", ".wma", ".opus"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def covers_root() -> Path:
    root = Path(get_settings().data_dir) / "covers"
    root.mkdir(parents=True, exist_ok=True)
    (root / "songs").mkdir(parents=True, exist_ok=True)
    (root / "cache").mkdir(parents=True, exist_ok=True)
    return root


def _sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()


def song_cover_cache_path(song_id: int, ext: str = ".jpg") -> Path:
    ext = ext if ext.startswith(".") else f".{ext}"
    return covers_root() / "songs" / f"{int(song_id)}{ext}"


def path_cover_cache_path(source_key: str, ext: str = ".jpg") -> Path:
    ext = ext if ext.startswith(".") else f".{ext}"
    return covers_root() / "cache" / f"{_sha1_text(source_key)}{ext}"


def _guess_image_ext(data: bytes, fallback: str = ".jpg") -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data[:3] == b"GIF":
        return ".gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:2] == b"\xff\xd8":
        return ".jpg"
    return fallback


def write_cover_bytes(data: bytes, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() not in IMAGE_EXTS:
        target = target.with_suffix(_guess_image_ext(data))
    target.write_bytes(data)
    return target


def is_local_file(path: Optional[str]) -> bool:
    if not path:
        return False
    p = Path(path)
    try:
        return p.is_file()
    except Exception:
        return False


def looks_like_remote_rel(path: Optional[str]) -> bool:
    """Heuristic: relative path without filesystem existence => remote/webdav candidate."""
    if not path:
        return False
    p = Path(path)
    if p.is_absolute():
        return False
    # Windows drive / UNC not expected in container paths
    s = str(path).replace("\\", "/")
    if s.startswith("/") or s.startswith("./") or s.startswith("../"):
        # could still be relative-ish; if not exists treat remote-ish only when no abs root
        return not Path(path).exists()
    return not Path(path).exists()


def read_audio_duration(path: str | Path) -> Optional[int]:
    p = Path(path)
    if not p.is_file():
        return None

    # 1) mutagen
    try:
        from mutagen import File as MutagenFile

        audio = MutagenFile(str(p))
        if audio is not None:
            length = getattr(audio, "info", None)
            if length is not None and getattr(length, "length", None):
                sec = int(round(float(length.length)))
                if sec > 0:
                    return sec
    except Exception:
        pass

    # 2) tinytag
    try:
        from tinytag import TinyTag

        tag = TinyTag.get(str(p))
        if tag and tag.duration:
            sec = int(round(float(tag.duration)))
            if sec > 0:
                return sec
    except Exception:
        pass

    # 3) ffprobe
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(p),
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            sec = int(round(float(proc.stdout.strip())))
            if sec > 0:
                return sec
    except Exception:
        pass
    return None


def extract_embedded_cover_bytes(path: str | Path) -> Optional[bytes]:
    p = Path(path)
    if not p.is_file():
        return None
    try:
        from mutagen import File as MutagenFile
        from mutagen.flac import FLAC, Picture
        from mutagen.id3 import ID3
        from mutagen.mp4 import MP4

        audio = MutagenFile(str(p))
        if audio is None:
            return None

        # FLAC pictures
        if isinstance(audio, FLAC) and audio.pictures:
            data = audio.pictures[0].data
            if data:
                return bytes(data)

        # MP3 APIC via tags
        tags = getattr(audio, "tags", None)
        if tags is not None:
            # ID3
            try:
                if isinstance(tags, ID3) or hasattr(tags, "getall"):
                    apics = []
                    if hasattr(tags, "getall"):
                        apics = tags.getall("APIC") or []
                    for pic in apics:
                        data = getattr(pic, "data", None)
                        if data:
                            return bytes(data)
            except Exception:
                pass

            # MP4 covr
            try:
                if isinstance(audio, MP4) or (isinstance(tags, dict) and "covr" in tags):
                    covr = tags.get("covr") if hasattr(tags, "get") else None
                    if covr:
                        item = covr[0]
                        data = bytes(item)
                        if data:
                            return data
            except Exception:
                pass

            # generic picture keys (ogg/opus etc.)
            for key in list(getattr(tags, "keys", lambda: [])()):
                lk = str(key).lower()
                if "cover" in lk or "pict" in lk or key in {"APIC:", "APIC", "covr", "METADATA_BLOCK_PICTURE"}:
                    try:
                        val = tags[key]
                        if hasattr(val, "data"):
                            return bytes(val.data)
                        if isinstance(val, (list, tuple)) and val:
                            v0 = val[0]
                            if hasattr(v0, "data"):
                                return bytes(v0.data)
                            return bytes(v0)
                        if isinstance(val, (bytes, bytearray)):
                            # maybe base64 flac picture block; try mutagen Picture
                            try:
                                pic = Picture(bytes(val))
                                if pic.data:
                                    return bytes(pic.data)
                            except Exception:
                                return bytes(val)
                    except Exception:
                        continue
    except Exception:
        pass

    # tinytag images
    try:
        from tinytag import TinyTag

        tag = TinyTag.get(str(p), image=True)
        images = getattr(tag, "images", None)
        if images:
            # tinytag 2.x
            any_img = getattr(images, "any", None)
            if callable(any_img):
                img = any_img()
                if img and getattr(img, "data", None):
                    return bytes(img.data)
            front = getattr(images, "front_cover", None) or getattr(images, "cover", None)
            if front and getattr(front, "data", None):
                return bytes(front.data)
        # older API
        img = getattr(tag, "get_image", None)
        if callable(img):
            data = img()
            if data:
                return bytes(data)
    except Exception:
        pass
    return None


def extract_and_cache_embedded_cover(
    audio_path: str | Path,
    *,
    song_id: Optional[int] = None,
    source_key: Optional[str] = None,
) -> Optional[str]:
    data = extract_embedded_cover_bytes(audio_path)
    if not data:
        return None
    ext = _guess_image_ext(data)
    if song_id is not None:
        target = song_cover_cache_path(song_id, ext)
    else:
        key = source_key or str(Path(audio_path).resolve())
        target = path_cover_cache_path(key, ext)
    write_cover_bytes(data, target)
    return str(target)


def ensure_local_cover_from_sidecar(sidecar_path: str | Path, *, song_id: Optional[int] = None) -> Optional[str]:
    p = Path(sidecar_path)
    if not p.is_file():
        return None
    if song_id is None:
        return str(p)
    ext = p.suffix.lower() if p.suffix.lower() in IMAGE_EXTS else ".jpg"
    target = song_cover_cache_path(song_id, ext)
    if not target.exists() or target.stat().st_size == 0:
        shutil.copyfile(str(p), str(target))
    return str(target)



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
            if val is None and key in getattr(tags, "keys", lambda: [])():
                val = tags[key]
        except Exception:
            val = None
        if val is None:
            continue
        # mutagen frames / lists
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
            if s and s not in {"None", "null"}:
                return s
        except Exception:
            continue
    return None


def _clean_meta_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"none", "null", "unknown", "未知", "未知艺术家", "未知专辑"}:
        return None
    return s


def read_audio_tags(path: str | Path) -> dict[str, Optional[str]]:
    """Read title/artist/album (and optional embedded lyrics) from local audio tags."""
    result: dict[str, Optional[str]] = {
        "title": None,
        "artist": None,
        "album": None,
        "lyrics": None,
    }
    p = Path(path)
    if not p.is_file():
        return result

    # 1) mutagen tags
    try:
        from mutagen import File as MutagenFile

        audio = MutagenFile(str(p), easy=False)
        if audio is not None:
            tags = getattr(audio, "tags", None) or audio
            title = _first_tag_value(tags, [
                "TIT2", "TITLE", "©nam", "title",
            ])
            artist = _first_tag_value(tags, [
                "TPE1", "ARTIST", "©ART", "artist", "ALBUMARTIST", "TPE2", "albumartist",
            ])
            album = _first_tag_value(tags, [
                "TALB", "ALBUM", "©alb", "album",
            ])
            # embedded lyrics
            lyrics = None
            try:
                if hasattr(tags, "getall"):
                    for frame in tags.getall("USLT") or []:
                        text = getattr(frame, "text", None)
                        if text:
                            lyrics = str(text).strip()
                            break
                if not lyrics:
                    lyrics = _first_tag_value(tags, [
                        "USLT", "LYRICS", "©lyr", "lyrics", "UNSYNCEDLYRICS",
                    ])
            except Exception:
                lyrics = None
            result["title"] = _clean_meta_text(title)
            result["artist"] = _clean_meta_text(artist)
            result["album"] = _clean_meta_text(album)
            if lyrics and str(lyrics).strip():
                result["lyrics"] = str(lyrics).strip()
    except Exception:
        pass

    # 2) tinytag fallback for missing fields
    if not (result["title"] and result["artist"] and result["album"]):
        try:
            from tinytag import TinyTag

            tag = TinyTag.get(str(p))
            if tag:
                if not result["title"]:
                    result["title"] = _clean_meta_text(getattr(tag, "title", None))
                if not result["artist"]:
                    result["artist"] = _clean_meta_text(getattr(tag, "artist", None))
                if not result["album"]:
                    result["album"] = _clean_meta_text(getattr(tag, "album", None))
        except Exception:
            pass

    return result






def write_audio_tags(
    path: str | Path,
    *,
    title: str | None = None,
    artist: str | None = None,
    album: str | None = None,
    lyrics: str | None = None,
    year: str | int | None = None,
    track: str | int | None = None,
    cover_path: str | Path | None = None,
    cover_bytes: bytes | None = None,
    cover_mime: str | None = None,
) -> dict[str, Any]:
    """Write tags (+ optional lyrics/year/track/cover) into local audio file."""
    p = Path(path) if not isinstance(path, Path) else path
    if not p.is_file():
        return {}
    written: dict[str, Any] = {}

    pic_data = None
    pic_mime = cover_mime or "image/jpeg"
    if cover_bytes:
        pic_data = cover_bytes
    elif cover_path:
        try:
            cp = Path(cover_path)
            if cp.is_file():
                pic_data = cp.read_bytes()
                if cp.suffix.lower() in {".png"}:
                    pic_mime = "image/png"
                elif cp.suffix.lower() in {".webp"}:
                    pic_mime = "image/webp"
        except Exception:
            pic_data = None

    year_s = str(year).strip() if year not in (None, "") else None
    track_s = str(track).strip() if track not in (None, "") else None
    lyrics_s = str(lyrics).strip() if lyrics else None

    try:
        from mutagen import File as MutagenFile
        from mutagen.easyid3 import EasyID3
        from mutagen.id3 import ID3, ID3NoHeaderError, APIC, USLT, TIT2, TPE1, TALB, TDRC, TRCK, error as ID3Error
        from mutagen.flac import FLAC, Picture
        from mutagen.mp4 import MP4, MP4Cover
    except Exception:
        return {}

    def _set_easy(audio_obj, mapping):
        for k, v in mapping.items():
            if not v:
                continue
            try:
                audio_obj[k] = str(v)
                written[k] = str(v)
            except Exception:
                pass

    suffix = p.suffix.lower()
    try:
        if suffix == ".mp3":
            # text tags via EasyID3
            try:
                tags = EasyID3(str(p))
            except ID3NoHeaderError:
                audio = MutagenFile(str(p), easy=True)
                if audio is None:
                    return {}
                try:
                    audio.add_tags()
                except Exception:
                    pass
                tags = audio
            easy_map = {"title": title, "artist": artist, "album": album}
            if year_s:
                easy_map["date"] = year_s
            if track_s:
                easy_map["tracknumber"] = track_s
            _set_easy(tags, easy_map)
            tags.save()
            # lyrics + cover via full ID3
            try:
                id3 = ID3(str(p))
            except ID3NoHeaderError:
                id3 = ID3()
            if lyrics_s:
                try:
                    id3.delall("USLT")
                except Exception:
                    pass
                id3.add(USLT(encoding=3, lang="chi", desc="", text=lyrics_s))
                written["lyrics"] = True
            if pic_data:
                try:
                    id3.delall("APIC")
                except Exception:
                    pass
                id3.add(
                    APIC(
                        encoding=3,
                        mime=pic_mime,
                        type=3,
                        desc="Cover",
                        data=pic_data,
                    )
                )
                written["cover"] = True
            if lyrics_s or pic_data:
                id3.save(str(p))
        elif suffix == ".flac":
            audio = FLAC(str(p))
            if title:
                audio["title"] = title
                written["title"] = title
            if artist:
                audio["artist"] = artist
                written["artist"] = artist
            if album:
                audio["album"] = album
                written["album"] = album
            if year_s:
                audio["date"] = year_s
                written["year"] = year_s
            if track_s:
                audio["tracknumber"] = track_s
                written["track"] = track_s
            if lyrics_s:
                audio["lyrics"] = lyrics_s
                written["lyrics"] = True
            if pic_data:
                pic = Picture()
                pic.type = 3
                pic.mime = pic_mime
                pic.desc = "Cover"
                pic.data = pic_data
                try:
                    audio.clear_pictures()
                except Exception:
                    pass
                audio.add_picture(pic)
                written["cover"] = True
            audio.save()
        elif suffix in {".m4a", ".mp4", ".aac"}:
            audio = MP4(str(p))
            if title:
                audio["\xa9nam"] = [title]
                written["title"] = title
            if artist:
                audio["\xa9ART"] = [artist]
                written["artist"] = artist
            if album:
                audio["\xa9alb"] = [album]
                written["album"] = album
            if year_s:
                audio["\xa9day"] = [year_s]
                written["year"] = year_s
            if track_s:
                try:
                    tn = int(str(track_s).split("/")[0])
                    audio["trkn"] = [(tn, 0)]
                    written["track"] = track_s
                except Exception:
                    pass
            if lyrics_s:
                audio["\xa9lyr"] = [lyrics_s]
                written["lyrics"] = True
            if pic_data:
                fmt = MP4Cover.FORMAT_PNG if "png" in pic_mime else MP4Cover.FORMAT_JPEG
                audio["covr"] = [MP4Cover(pic_data, imageformat=fmt)]
                written["cover"] = True
            audio.save()
        else:
            audio = MutagenFile(str(p), easy=True)
            if audio is None:
                return {}
            try:
                if audio.tags is None:
                    audio.add_tags()
            except Exception:
                pass
            mapping = {"title": title, "artist": artist, "album": album}
            if year_s:
                mapping["date"] = year_s
            if track_s:
                mapping["tracknumber"] = track_s
            _set_easy(audio, mapping)
            if lyrics_s:
                try:
                    audio["lyrics"] = lyrics_s
                    written["lyrics"] = True
                except Exception:
                    pass
            audio.save()
    except Exception:
        return written
    return written

def enrich_local_audio(
    audio_path: str | Path,
    *,
    song_id: Optional[int] = None,
    existing_cover: Optional[str] = None,
) -> dict[str, Any]:
    """Return duration/cover plus title/artist/album tags from a local audio file.

    Cover priority inside this helper:
    1) existing_cover if local
    2) embedded picture
    3) track-stem image / album cover.jpg (directory sidecar)
    """
    result: dict[str, Any] = {
        "duration": None,
        "cover_path": None,
        "title": None,
        "artist": None,
        "album": None,
        "lyrics": None,
        "lrc_path": None,
    }
    p = Path(audio_path)
    if not p.is_file():
        return result

    result["duration"] = read_audio_duration(p)
    tags = read_audio_tags(p)
    for key in ("title", "artist", "album", "lyrics"):
        if tags.get(key):
            result[key] = tags[key]

    lrc = find_lrc_sidecar(p)
    if lrc:
        result["lrc_path"] = str(lrc)

    if existing_cover and is_local_file(existing_cover):
        result["cover_path"] = (
            ensure_local_cover_from_sidecar(existing_cover, song_id=song_id) or existing_cover
        )
        return result

    cached = extract_and_cache_embedded_cover(p, song_id=song_id, source_key=str(p.resolve()))
    if cached:
        result["cover_path"] = cached
        return result

    # directory sidecars
    side = find_track_cover_file(p) or find_album_cover_file(p.parent)
    if side and side.is_file():
        result["cover_path"] = (
            ensure_local_cover_from_sidecar(str(side), song_id=song_id) or str(side)
        )
    return result


def materialize_song_cover(song, db=None) -> Optional[str]:
    """Ensure song.cover_path points to a local image file when possible.

    Order:
    1) existing local cover_path
    2) embedded cover from local_path
    2b) directory sidecars (track image / cover.jpg)
    3) WebDAV download of cover_path / sibling sidecar if cover_path looks remote

    Network I/O is done without holding a DB transaction open longer than necessary.
    """
    if song is None:
        return None

    song_id = getattr(song, "id", None)
    if song_id is not None:
        exp = _COVER_MISS_CACHE.get(int(song_id))
        if exp and exp > time.time():
            # recently failed; still allow local paths below
            pass

    def _persist_cover(path: str) -> str:
        song.cover_path = path
        if db is not None:
            try:
                db.add(song)
                db.commit()
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass
        if song_id is not None:
            _COVER_MISS_CACHE.pop(int(song_id), None)
        return path

    # 1) local cover
    if is_local_file(getattr(song, "cover_path", None)):
        local = ensure_local_cover_from_sidecar(song.cover_path, song_id=song_id)
        if local:
            if local != song.cover_path:
                return _persist_cover(local)
            return local

    # 2) embedded from local audio
    if is_local_file(getattr(song, "local_path", None)):
        cached = extract_and_cache_embedded_cover(
            song.local_path,
            song_id=song_id,
            source_key=str(Path(song.local_path).resolve()),
        )
        if cached:
            return _persist_cover(cached)

        # 2b) directory sidecars: track image / album cover.jpg
        try:
            audio = Path(song.local_path)
            side = find_track_cover_file(audio) or find_album_cover_file(audio.parent)
            if side and side.is_file():
                local = ensure_local_cover_from_sidecar(str(side), song_id=song_id) or str(side)
                if local and is_local_file(local):
                    return _persist_cover(local)
        except Exception:
            pass

    # miss cache: skip remote attempt for a while
    if song_id is not None:
        exp = _COVER_MISS_CACHE.get(int(song_id))
        if exp and exp > time.time():
            return None

    # 3) webdav remote cover/audio sidecar
    remote_candidates = []
    cover = getattr(song, "cover_path", None)
    if cover and looks_like_remote_rel(cover):
        remote_candidates.append(cover.replace("\\", "/").lstrip("/"))
    webdav_path = getattr(song, "webdav_path", None)
    if webdav_path:
        stem = str(webdav_path).rsplit(".", 1)[0]
        parent = str(webdav_path).rsplit("/", 1)[0]
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            remote_candidates.append(stem + ext)
        if parent and parent != str(webdav_path):
            remote_candidates.append(f"{parent}/cover.jpg")
            remote_candidates.append(f"{parent}/cover.png")
            remote_candidates.append(f"{parent}/folder.jpg")

    seen = set()
    uniq = []
    for c in remote_candidates:
        c = (c or "").replace("\\", "/").lstrip("/")
        if c and c not in seen:
            seen.add(c)
            uniq.append(c)

    if not uniq:
        if song_id is not None:
            _COVER_MISS_CACHE[int(song_id)] = time.time() + _COVER_MISS_TTL
        return None

    try:
        from app.services.webdav_service import WebDAVService

        # Use provided session only for reading WebDAV config; download is network-bound.
        ws = WebDAVService(db)
        for rel in uniq[:8]:
            try:
                data = ws.download_bytes(rel, max_bytes=4 * 1024 * 1024)
            except Exception:
                continue
            if not data or len(data) < 24:
                continue
            ext = _guess_image_ext(data, fallback="")
            if not ext:
                continue
            target = (
                song_cover_cache_path(int(song_id), ext)
                if song_id is not None
                else path_cover_cache_path(rel, ext)
            )
            write_cover_bytes(data, target)
            return _persist_cover(str(target))
    except Exception:
        pass

    if song_id is not None:
        _COVER_MISS_CACHE[int(song_id)] = time.time() + _COVER_MISS_TTL
    return None



def enrich_song_record(song, db=None, *, force: bool = False) -> dict[str, Any]:
    """Fill duration/cover for an existing Song row when possible."""
    changed = False
    info: dict[str, Any] = {"duration": song.duration, "cover_path": song.cover_path}

    if is_local_file(getattr(song, "local_path", None)):
        need_duration = force or not song.duration
        need_cover = force or not is_local_file(getattr(song, "cover_path", None))
        if need_duration or need_cover:
            meta = enrich_local_audio(
                song.local_path,
                song_id=getattr(song, "id", None),
                existing_cover=song.cover_path if is_local_file(song.cover_path) else None,
            )
            if need_duration and meta.get("duration"):
                song.duration = int(meta["duration"])
                changed = True
            if need_cover and meta.get("cover_path"):
                song.cover_path = meta["cover_path"]
                changed = True
            info.update({k: v for k, v in meta.items() if v})

    if force or not is_local_file(getattr(song, "cover_path", None)):
        cover = materialize_song_cover(song, db=None)  # avoid double commit
        if cover and cover != info.get("cover_path"):
            song.cover_path = cover
            changed = True
            info["cover_path"] = cover

    if changed and db is not None:
        try:
            db.add(song)
            db.commit()
        except Exception:
            db.rollback()
    return info


def resolve_song_meta(
    song=None,
    *,
    audio_path: str | Path | None = None,
    db=None,
    allow_network: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Unified metadata pipeline for scan / play / reorganize.

    Priority:
      1) embedded tags / embedded cover / embedded lyrics
      2) directory sidecars (cover.jpg, same-stem .lrc, track image)
      3) existing DB paths on the Song row
      4) optional network enrich via scrape pipeline (MusicBrainz → musicdl)

    Returns a dict with keys:
      title, artist, album, duration, cover_path, lrc_path, lyrics, sources
    """
    sources: dict[str, str] = {}
    out: dict[str, Any] = {
        "title": None,
        "artist": None,
        "album": None,
        "duration": None,
        "cover_path": None,
        "lrc_path": None,
        "lyrics": None,
        "sources": sources,
    }

    local = None
    if audio_path and is_local_file(str(audio_path)):
        local = Path(audio_path)
    elif song is not None and is_local_file(getattr(song, "local_path", None)):
        local = Path(song.local_path)

    # --- 1+2 local file ---
    if local and local.is_file():
        meta = enrich_local_audio(
            local,
            song_id=getattr(song, "id", None) if song is not None else None,
            existing_cover=None,
        )
        for key in ("title", "artist", "album", "duration", "lyrics"):
            if meta.get(key):
                out[key] = meta[key]
                sources[key] = "embedded" if key != "duration" else "local"
        if meta.get("cover_path"):
            out["cover_path"] = meta["cover_path"]
            sources["cover_path"] = "embedded_or_sidecar"
        if meta.get("lrc_path"):
            out["lrc_path"] = meta["lrc_path"]
            sources["lrc_path"] = "sidecar"
        elif meta.get("lyrics"):
            # materialize embedded lyrics next to audio when missing sidecar
            try:
                target = local.with_suffix(".lrc")
                if not target.exists():
                    text_lrc = str(meta["lyrics"]).replace("\r\n", "\n").strip()
                    if text_lrc:
                        target.write_text(
                            text_lrc + ("\n" if not text_lrc.endswith("\n") else ""),
                            encoding="utf-8",
                        )
                if target.exists():
                    out["lrc_path"] = str(target)
                    sources["lrc_path"] = "embedded"
            except Exception:
                out["lyrics"] = meta.get("lyrics")
                sources["lyrics"] = "embedded"

        # explicit sidecar cover if still missing
        if not out.get("cover_path"):
            side = find_track_cover_file(local) or find_album_cover_file(local.parent)
            if side:
                out["cover_path"] = str(side)
                sources["cover_path"] = "sidecar"

    # --- 3 DB fields ---
    if song is not None:
        if not out.get("title") and getattr(song, "title", None):
            out["title"] = song.title
            sources["title"] = "db"
        if not out.get("artist") and getattr(song, "artist", None) and not is_generic_dir_name(song.artist):
            out["artist"] = song.artist
            sources["artist"] = "db"
        elif out.get("artist") is None and getattr(song, "artist", None) and not is_generic_dir_name(song.artist):
            out["artist"] = song.artist
            sources["artist"] = "db"
        if not out.get("album") and getattr(song, "album", None) and not is_generic_dir_name(song.album):
            out["album"] = song.album
            sources["album"] = "db"
        if not out.get("duration") and getattr(song, "duration", None):
            out["duration"] = song.duration
            sources["duration"] = "db"
        if not out.get("cover_path") and is_local_file(getattr(song, "cover_path", None)):
            out["cover_path"] = song.cover_path
            sources["cover_path"] = "db"
        if not out.get("lrc_path") and getattr(song, "lrc_path", None):
            # keep path even if remote; caller may stream
            out["lrc_path"] = song.lrc_path
            sources["lrc_path"] = "db"

        # try materialize cover from remote/db without network search
        if force or not out.get("cover_path"):
            try:
                cover = materialize_song_cover(song, db=None)
                if cover and is_local_file(cover):
                    out["cover_path"] = cover
                    sources["cover_path"] = sources.get("cover_path") or "materialize"
            except Exception:
                pass

        # lyrics discovery via service (local/remote sidecar)
        if force or not out.get("lrc_path") or not out.get("lyrics"):
            try:
                from app.services.lyrics_service import load_lyrics_for_song

                lines, raw, resolved = load_lyrics_for_song(song, db=db, persist=False)
                if resolved:
                    out["lrc_path"] = resolved
                    sources["lrc_path"] = sources.get("lrc_path") or "discover"
                if raw and not out.get("lyrics"):
                    out["lyrics"] = raw
                    sources["lyrics"] = sources.get("lyrics") or "discover"
            except Exception:
                pass

    # scrub generic artist/album
    if out.get("artist") and is_generic_dir_name(out["artist"]):
        out["artist"] = None
        sources.pop("artist", None)
    if out.get("album") and is_generic_dir_name(out["album"]):
        out["album"] = None
        sources.pop("album", None)

    # --- 4 network (optional multi-provider) ---
    if allow_network and song is not None:
        try:
            missing = (
                not out.get("album")
                or not out.get("artist")
                or not out.get("cover_path")
                or not out.get("lrc_path")
                or not out.get("duration")
            )
            if missing:
                from app.services.scrape import enrich_song_via_pipeline

                if db is None:
                    raise RuntimeError("network enrich requires db session")
                enriched = enrich_song_via_pipeline(
                    song,
                    db=db,
                    timeout_per_provider=8.0,
                    total_timeout=20.0,
                ) or {}
                for key in ("artist", "album", "duration", "cover_path", "lrc_path"):
                    val = enriched.get(key) if isinstance(enriched, dict) else None
                    if val and not out.get(key):
                        out[key] = val
                        sources[key] = f"network:{(enriched.get('provider') or 'pipeline')}"
                for key in ("artist", "album", "duration", "cover_path", "lrc_path"):
                    val = getattr(song, key, None)
                    if val and not out.get(key):
                        out[key] = val
                        sources[key] = "network"
        except Exception:
            sources["network_error"] = "1"


    return out


def write_album_cover_file(album_dir: str | Path, data: bytes) -> Optional[Path]:
    """Write cover bytes as standard cover.jpg under album directory."""
    if not data:
        return None
    target = preferred_album_cover_path(album_dir, _guess_image_ext(data, ".jpg"))
    try:
        write_cover_bytes(data, target)
        return target
    except Exception:
        return None