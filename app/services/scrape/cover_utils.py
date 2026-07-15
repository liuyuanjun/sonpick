"""Cover URL extraction and download diagnostics for scrape candidates."""
from __future__ import annotations

import json
import mimetypes
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def _as_dict(obj: Any) -> dict:
    if isinstance(obj, dict):
        return obj
    if obj is None:
        return {}
    return getattr(obj, "__dict__", {}) or {}


def _get_path(data: Any, path: list[str]) -> Any:
    cur = data
    for key in path:
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(key)
        else:
            cur = getattr(cur, key, None)
    return cur


def qq_album_cover_url(album_mid: Any, *, size: int = 800) -> str | None:
    mid = str(album_mid or "").strip()
    if not mid:
        return None
    return f"https://y.gtimg.cn/music/photo_new/T002R{size}x{size}M000{mid}.jpg"


def extract_cover_url(obj: Any) -> tuple[str | None, str | None]:
    """Return (cover_url, source_hint) from SongInfo/dict/raw_data."""
    candidates: list[tuple[Any, str]] = []
    for key in ("cover_url", "album_pic", "album_pic_url", "pic", "pic_url", "picUrl", "album_img", "cover", "coverUrl"):
        candidates.append((getattr(obj, key, None), key))
        if isinstance(obj, dict):
            candidates.append((obj.get(key), key))
    raw = getattr(obj, "raw_data", None)
    if raw is None and isinstance(obj, dict):
        raw = obj.get("raw_data") or obj.get("raw")
    for base, base_name in ((raw, "raw_data"), (obj, "obj")):
        for path in (
            ["search", "al", "picUrl"],
            ["search", "album", "picUrl"],
            ["search", "album", "pic_url"],
            ["search", "album", "cover"],
            ["search", "album", "albumPic"],
            ["search", "album", "pmid"],
            ["download", "cover"],
            ["download", "cover_url"],
            ["album", "picUrl"],
            ["album", "pic_url"],
            ["al", "picUrl"],
        ):
            candidates.append((_get_path(base, path), f"{base_name}." + ".".join(path)))
        for path in (
            ["search", "album", "mid"],
            ["search", "album", "albumMid"],
            ["search", "album", "album_mid"],
            ["search", "album", "albummid"],
            ["album", "mid"],
            ["albumMid"],
            ["albummid"],
            ["album_mid"],
        ):
            mid = _get_path(base, path)
            url = qq_album_cover_url(mid)
            candidates.append((url, f"qq_album_mid:{'.'.join(path)}"))
    for val, source in candidates:
        if not val:
            continue
        s = str(val).strip()
        if not s or s.lower() in {"null", "none"}:
            continue
        if s.startswith("//"):
            s = "https:" + s
        if s.startswith("http://") or s.startswith("https://"):
            return s, source
    return None, None


def enrich_cover_fields(row: dict, obj: Any | None = None) -> dict:
    item = dict(row or {})
    url, source = extract_cover_url(item)
    if not url and obj is not None:
        url, source = extract_cover_url(obj)
    if url:
        item["cover_url"] = url
        item["cover_source"] = source
        item["has_cover"] = True
    else:
        item.setdefault("cover_url", None)
        item["cover_source"] = source
        item["has_cover"] = False
    return item


def _referer_for_url(url: str) -> str:
    host = urllib.parse.urlparse(str(url)).netloc.lower()
    if "126.net" in host or "music.163.com" in host:
        return "https://music.163.com/"
    if "gtimg" in host or "qq.com" in host:
        return "https://y.qq.com/"
    if "migu" in host:
        return "https://music.migu.cn/"
    return "https://music.163.com/"


def _image_mime_from_magic(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    return None


def download_cover_with_diagnostics(url: str | None, dest: str | Path, *, timeout: float = 15.0) -> dict:
    if not url:
        return {"ok": False, "path": None, "error": "missing cover_url"}
    path = Path(dest)
    path.parent.mkdir(parents=True, exist_ok=True)
    url_s = str(url).strip()
    req = urllib.request.Request(
        url_s,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Sonpick/1.0",
            "Referer": _referer_for_url(url_s),
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            content_type = resp.headers.get("Content-Type", "")
            data = resp.read()
        if status >= 400:
            return {"ok": False, "path": None, "error": f"HTTP {status}", "status": status, "content_type": content_type}
        if not data:
            return {"ok": False, "path": None, "error": "empty response", "status": status, "content_type": content_type}
        magic_mime = _image_mime_from_magic(data)
        if "image" not in (content_type or "").lower():
            guess = mimetypes.guess_type(url_s)[0] or ""
            if "image" not in guess and not magic_mime:
                return {"ok": False, "path": None, "error": f"not image: {content_type}", "status": status, "content_type": content_type, "size": len(data), "url": url_s}
        path.write_bytes(data)
        return {"ok": True, "path": str(path), "error": None, "status": status, "content_type": content_type or magic_mime, "size": len(data), "url": url_s}
    except Exception as e:
        return {"ok": False, "path": None, "error": f"{type(e).__name__}: {e}", "url": str(url)}


def extract_qq_songmid(value: Any) -> str | None:
    import re

    s = str(value or "")
    # QQ songmid commonly starts with 00 and is 14 chars, e.g. 003NbMHZ0nu9eI
    m = re.search(r"\b(00[0-9A-Za-z]{10,14})\b", s)
    return m.group(1) if m else None


def qq_song_detail_cover(songmid: str | None, *, timeout: float = 12.0) -> dict:
    """Fetch QQ song detail to recover album mid/cover for remote files."""
    mid = extract_qq_songmid(songmid)
    if not mid:
        return {"ok": False, "error": "missing qq songmid"}
    payload = {"songinfo": {"method": "get_song_detail_yqq", "module": "music.pf_song_detail_svr", "param": {"song_mid": mid}}}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://u.y.qq.com/cgi-bin/musicu.fcg",
        data=data,
        headers={
            "User-Agent": "Mozilla/5.0 Sonpick/1.0",
            "Referer": "https://y.qq.com/",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
        track = _get_path(body, ["songinfo", "data", "track_info"]) or {}
        album_mid = _get_path(track, ["album", "mid"]) or track.get("albummid") or track.get("albumMid")
        cover_url = qq_album_cover_url(album_mid)
        return {"ok": bool(cover_url), "songmid": mid, "album_mid": album_mid, "cover_url": cover_url, "source": "qq.song_detail.album_mid", "raw_title": track.get("title") or track.get("name")}
    except Exception as e:
        return {"ok": False, "songmid": mid, "error": f"{type(e).__name__}: {e}"}

