"""Lightweight MiGu search/lyrics via public HTTP APIs (no musicdl)."""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any, Optional

log = logging.getLogger("sonpick.scrape")

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) "
    "Gecko/20100101 Firefox/120.0"
)
_HEADERS = {
    "User-Agent": _UA,
    "Referer": "https://m.music.migu.cn/",
    "Accept": "application/json,text/plain,*/*",
}


def _http_json(url: str, *, timeout: float = 12.0) -> Any:
    req = urllib.request.Request(url, headers=_HEADERS, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8", errors="replace"))


def search_migu(keyword: str, *, limit: int = 8, timeout: float = 12.0) -> list[dict[str, Any]]:
    kw = (keyword or "").strip()
    if not kw:
        return []
    q = urllib.parse.urlencode(
        {
            "rows": max(1, min(int(limit), 20)),
            "type": 2,
            "keyword": kw,
            "pgc": 1,
        }
    )
    url = f"https://m.music.migu.cn/migu/remoting/scr_search_tag?{q}"
    try:
        data = _http_json(url, timeout=timeout)
    except Exception as e:
        log.warning("migu search failed keyword=%r err=%s", kw, e)
        return []

    songs = data.get("musics") or data.get("songs") or []
    if not isinstance(songs, list):
        return []

    out: list[dict[str, Any]] = []
    for s in songs[: max(1, int(limit))]:
        if not isinstance(s, dict):
            continue
        duration = None
        for key in ("duration", "length", "songTimeMinutes"):
            val = s.get(key)
            if val is None:
                continue
            try:
                if isinstance(val, str) and ":" in val:
                    parts = val.split(":")
                    if len(parts) == 2:
                        duration = int(parts[0]) * 60 + int(float(parts[1]))
                        break
                n = int(float(val))
                if n > 10000:
                    n = int(round(n / 1000))
                duration = n if n > 0 else None
                break
            except Exception:
                continue
        out.append(
            {
                "id": s.get("copyrightId") or s.get("id") or s.get("songId"),
                "title": s.get("songName") or s.get("title") or s.get("name"),
                "artist": s.get("singerName") or s.get("artist") or s.get("singer"),
                "album": s.get("albumName") or s.get("album"),
                "cover_url": s.get("cover") or s.get("pic") or s.get("albumImg"),
                "duration": duration,
                "year": s.get("year") or "",
                "source": "migu",
            }
        )
    return out


def fetch_migu_lyric(song_id: Any, *, timeout: float = 10.0) -> str:
    if not song_id:
        return ""
    # primary
    urls = [
        f"https://music.migu.cn/v3/api/music/audioPlayer/getLyric?copyrightId={urllib.parse.quote(str(song_id))}",
        f"https://c.musicapp.migu.cn/MIGUM2.0/strategy/lyric/v1.0?copyrightId={urllib.parse.quote(str(song_id))}",
    ]
    for url in urls:
        try:
            data = _http_json(url, timeout=timeout)
            if isinstance(data, dict):
                lyric = data.get("lyric") or (data.get("data") or {}).get("lyric") or ""
                if lyric:
                    return str(lyric).strip()
        except Exception as e:
            log.debug("migu lyric try failed id=%s err=%s", song_id, e)
            continue
    return ""
