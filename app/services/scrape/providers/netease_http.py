"""Lightweight NetEase search/lyrics via public HTTP APIs (no musicdl)."""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

log = logging.getLogger("sonpick.scrape")

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _http_json(
    url: str,
    *,
    method: str = "GET",
    data: Optional[dict[str, Any]] = None,
    timeout: float = 12.0,
    headers: Optional[dict[str, str]] = None,
) -> Any:
    hdrs = {
        "User-Agent": _UA,
        "Referer": "https://music.163.com/",
        "Accept": "application/json,text/plain,*/*",
    }
    if headers:
        hdrs.update(headers)
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8", errors="replace"))


def search_netease(keyword: str, *, limit: int = 8, timeout: float = 12.0) -> list[dict[str, Any]]:
    kw = (keyword or "").strip()
    if not kw:
        return []
    # Public search endpoint (unencrypted). Falls back to cloudsearch form.
    endpoints = [
        (
            "GET",
            "https://music.163.com/api/search/get/web?"
            + urllib.parse.urlencode({"s": kw, "type": 1, "offset": 0, "total": "true", "limit": int(limit)}),
            None,
        ),
        (
            "POST",
            "https://music.163.com/api/search/get/web",
            {"s": kw, "type": 1, "offset": 0, "total": "true", "limit": int(limit)},
        ),
        (
            "GET",
            "https://music.163.com/api/cloudsearch/pc?"
            + urllib.parse.urlencode({"s": kw, "type": 1, "limit": int(limit), "offset": 0}),
            None,
        ),
    ]
    last_err = None
    payload = None
    for method, url, data in endpoints:
        try:
            payload = _http_json(url, method=method, data=data, timeout=timeout)
            if payload:
                break
        except Exception as e:
            last_err = e
            payload = None
    if not payload:
        if last_err:
            log.warning("netease search failed keyword=%r err=%s", kw, last_err)
        return []

    result = payload.get("result") or payload.get("data") or {}
    songs = result.get("songs") or result.get("songCount") and result.get("songs") or []
    if not isinstance(songs, list):
        songs = []

    out: list[dict[str, Any]] = []
    for s in songs[: max(1, int(limit))]:
        try:
            artists = s.get("artists") or s.get("ar") or []
            if isinstance(artists, list):
                artist = ",".join(
                    str(a.get("name") or "").strip() for a in artists if isinstance(a, dict) and a.get("name")
                )
            else:
                artist = str(artists or "")
            album_obj = s.get("album") or s.get("al") or {}
            album = ""
            cover = None
            if isinstance(album_obj, dict):
                album = str(album_obj.get("name") or "")
                cover = album_obj.get("picUrl") or album_obj.get("pic_str") or album_obj.get("blurPicUrl")
            duration_ms = s.get("duration") or s.get("dt") or 0
            try:
                duration = int(round(int(duration_ms) / 1000)) if int(duration_ms) > 1000 else int(duration_ms)
            except Exception:
                duration = None
            year = None
            pub = None
            if isinstance(album_obj, dict):
                pub = album_obj.get("publishTime") or album_obj.get("publish_time")
            if pub:
                try:
                    # ms timestamp
                    import datetime as _dt

                    year = str(_dt.datetime.utcfromtimestamp(int(pub) / 1000).year)
                except Exception:
                    year = None
            out.append(
                {
                    "id": s.get("id"),
                    "title": s.get("name") or s.get("songName"),
                    "artist": artist,
                    "album": album,
                    "cover_url": cover,
                    "duration": duration if duration and duration > 0 else None,
                    "year": year,
                    "source": "netease",
                }
            )
        except Exception:
            continue
    return out


def fetch_netease_song_cover(song_id: Any, *, timeout: float = 12.0) -> dict[str, Any]:
    """Fetch a NetEase song detail when search results omit album artwork."""
    if not song_id:
        return {"ok": False, "error": "missing netease song id"}
    url = "https://music.163.com/api/song/detail/?" + urllib.parse.urlencode({"ids": f"[{song_id}]"})
    try:
        payload = _http_json(url, timeout=timeout)
        song = (payload.get("songs") or [{}])[0]
        album = song.get("album") or song.get("al") or {}
        cover_url = album.get("picUrl") or album.get("blurPicUrl") or album.get("pic_str") if isinstance(album, dict) else None
        return {
            "ok": bool(cover_url),
            "song_id": song_id,
            "cover_url": cover_url,
            "album": album.get("name") if isinstance(album, dict) else None,
            "source": "netease.song_detail.album.picUrl",
        }
    except Exception as exc:
        return {"ok": False, "song_id": song_id, "error": f"{type(exc).__name__}: {exc}"}


def fetch_netease_lyric(song_id: Any, *, timeout: float = 10.0) -> str:
    if not song_id:
        return ""
    url = "https://music.163.com/api/song/lyric?" + urllib.parse.urlencode(
        {"id": song_id, "lv": -1, "kv": -1, "tv": -1}
    )
    try:
        data = _http_json(url, timeout=timeout)
        lrc = (data.get("lrc") or {}).get("lyric") or ""
        return str(lrc).strip()
    except Exception as e:
        log.warning("netease lyric failed id=%s err=%s", song_id, e)
        return ""
