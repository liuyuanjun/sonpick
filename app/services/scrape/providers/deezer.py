"""Deezer public search scrape provider."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, Optional

from app.services.scrape.base import ScrapeQuery, ScrapeResult
from app.services.scrape.match import score_candidate

NAME = "deezer"


def _row_score(query: ScrapeQuery, row: dict[str, Any]) -> float:
    return float(score_candidate(
        query_title=query.title, query_artist=query.artist, query_duration=query.duration,
        cand_title=row.get("title"), cand_artist=row.get("artist"), cand_album=row.get("album"), cand_duration=row.get("duration"),
    ).get("total") or 0)


def search_deezer(keyword: str, *, limit: int = 8, timeout: float = 12.0) -> list[dict[str, Any]]:
    term = (keyword or "").strip()
    if not term:
        return []
    url = f"https://api.deezer.com/search?{urllib.parse.urlencode({'q': term, 'limit': max(1, min(int(limit), 20))})}"
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Sonpick/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    for item in data.get("data") or []:
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        album = item.get("album") or {}
        artist = item.get("artist") or {}
        rows.append({
            "id": item.get("id"),
            "title": title,
            "artist": artist.get("name"),
            "album": album.get("title"),
            "duration": item.get("duration"),
            "cover_url": album.get("cover_xl") or album.get("cover_big") or album.get("cover_medium"),
            "genre": album.get("genre_id"),
            "source": NAME,
        })
    return rows


class DeezerProvider:
    name = NAME
    priority = 210

    def lookup(self, query: ScrapeQuery, *, timeout: float = 8.0) -> Optional[ScrapeResult]:
        keyword = " ".join(part for part in (query.title, query.artist) if part).strip()
        rows = search_deezer(keyword, timeout=timeout)
        if not rows:
            return None
        best = max(rows, key=lambda row: _row_score(query, row))
        score = _row_score(query, best)
        if score <= 0:
            return None
        return ScrapeResult(
            title=best.get("title"), artist=best.get("artist"), album=best.get("album"),
            duration=best.get("duration"), cover_url=best.get("cover_url"), provider=NAME,
            score=float(score), raw=best,
        )
