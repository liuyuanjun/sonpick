"""Cover URL extraction and download diagnostics for scrape candidates."""
from __future__ import annotations

import http.client
import json
import logging
import mimetypes
import socket
import ssl
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger("sonpick.meta")


class _IPv4HTTPSConnection(http.client.HTTPSConnection):
    """Prefer IPv4: many NAS/Docker setups resolve AAAA but cannot route IPv6 (Errno 101)."""

    def connect(self) -> None:
        last_err: OSError | None = None
        infos = socket.getaddrinfo(self.host, self.port, socket.AF_INET, socket.SOCK_STREAM)
        if not infos:
            # fall back to default dual-stack behavior
            return super().connect()
        for res in infos:
            af, socktype, proto, _canon, sa = res
            sock = None
            try:
                sock = socket.socket(af, socktype, proto)
                if self.timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:  # type: ignore[attr-defined]
                    sock.settimeout(self.timeout)
                sock.connect(sa)
                if self._tunnel_host:
                    self.sock = sock
                    self._tunnel()
                self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
                return
            except OSError as exc:
                last_err = exc
                if sock is not None:
                    sock.close()
        if last_err is not None:
            raise last_err
        raise OSError(f"no IPv4 route to {self.host}")


class _IPv4HTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):  # noqa: ANN001
        return self.do_open(_IPv4HTTPSConnection, req)


_IPV4_OPENER = urllib.request.build_opener(_IPv4HTTPSHandler())


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


def _humanize_download_error(exc: BaseException, url: str) -> str:
    msg = f"{type(exc).__name__}: {exc}"
    low = msg.lower()
    if "network is unreachable" in low or "errno 101" in low:
        return (
            f"服务器无法访问封面地址（网络不可达，常见于容器 IPv6/出网限制）: {url}。"
            "可改用网易/QQ 候选，或由浏览器提交已预览的封面图"
        )
    if "timed out" in low or "timeout" in low:
        return f"下载封面超时: {url}"
    if "name or service not known" in low or "nodename nor servname" in low:
        return f"封面域名解析失败: {url}"
    return msg


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
        # Prefer IPv4 opener; fall back to default urlopen if needed.
        try:
            resp_cm = _IPV4_OPENER.open(req, timeout=timeout)
        except Exception as ipv4_exc:
            log.info("cover download IPv4 path failed url=%s err=%s; trying default", url_s, ipv4_exc)
            resp_cm = urllib.request.urlopen(req, timeout=timeout)
        with resp_cm as resp:
            status = getattr(resp, "status", 200)
            content_type = resp.headers.get("Content-Type", "")
            data = resp.read()
        if status >= 400:
            return {"ok": False, "path": None, "error": f"HTTP {status}", "status": status, "content_type": content_type, "url": url_s}
        if not data:
            return {"ok": False, "path": None, "error": "empty response", "status": status, "content_type": content_type, "url": url_s}
        magic_mime = _image_mime_from_magic(data)
        if "image" not in (content_type or "").lower():
            guess = mimetypes.guess_type(url_s)[0] or ""
            if "image" not in guess and not magic_mime:
                return {"ok": False, "path": None, "error": f"not image: {content_type}", "status": status, "content_type": content_type, "size": len(data), "url": url_s}
        path.write_bytes(data)
        return {"ok": True, "path": str(path), "error": None, "status": status, "content_type": content_type or magic_mime, "size": len(data), "url": url_s}
    except Exception as e:
        err = _humanize_download_error(e, url_s)
        log.warning("cover download failed url=%s error=%s", url_s, err)
        return {"ok": False, "path": None, "error": err, "url": url_s}


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

