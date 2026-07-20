"""iTunes Search API scrape provider."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, Optional

from app.services.scrape.base import ScrapeQuery, ScrapeResult
from app.services.scrape.match import score_candidate

NAME = "itunes"


def _row_score(query: ScrapeQuery, row: dict[str, Any]) -> float:
    return float(score_candidate(
        query_title=query.title, query_artist=query.artist, query_duration=query.duration,
        cand_title=row.get("title"), cand_artist=row.get("artist"), cand_album=row.get("album"), cand_duration=row.get("duration"),
    ).get("total") or 0)


def _artwork_url(value: str | None) -> str | None:
    if not value:
        return None
    return str(value).replace("100x100bb.jpg", "600x600bb.jpg")


def search_itunes(keyword: str, *, country: str = "hk", limit: int = 8, timeout: float = 12.0) -> list[dict[str, Any]]:
    term = (keyword or "").strip()
    if not term:
        return []
    params = {
        "term": term,
        "entity": "song",
        "country": (country or "hk").lower(),
        "limit": max(1, min(int(limit), 20)),
    }
    request = urllib.request.Request(
        f"https://itunes.apple.com/search?{urllib.parse.urlencode(params)}",
        headers={"Accept": "application/json", "User-Agent": "Sonpick/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    for item in data.get("results") or []:
        track_name = str(item.get("trackName") or "").strip()
        if not track_name:
            continue
        duration = item.get("trackTimeMillis")
        try:
            duration = int(round(int(duration) / 1000)) if duration else None
        except (TypeError, ValueError):
            duration = None
        rows.append({
            "id": item.get("trackId") or item.get("collectionId"),
            "title": track_name,
            "artist": item.get("artistName"),
            "album": item.get("collectionName"),
            "duration": duration,
            "cover_url": _artwork_url(item.get("artworkUrl100")),
            "year": str(item.get("releaseDate") or "")[:4],
            "genre": item.get("primaryGenreName"),
            "source": NAME,
            "country": params["country"],
        })
    return rows


class ITunesProvider:
    name = NAME
    priority = 200

    def __init__(self, *, country: str = "hk"):
        self.country = country or "hk"

    def lookup(self, query: ScrapeQuery, *, timeout: float = 8.0) -> Optional[ScrapeResult]:
        keyword = " ".join(part for part in (query.title, query.artist) if part).strip()
        rows = search_itunes(keyword, country=self.country, timeout=timeout)
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
