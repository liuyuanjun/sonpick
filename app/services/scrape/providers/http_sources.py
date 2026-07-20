"""Configured provider adapters for domestic and overseas scrape sources."""
from __future__ import annotations

from typing import Optional

from app.services.scrape.base import ScrapeQuery, ScrapeResult
from app.services.scrape.match import score_candidate
from app.services.scrape.providers.migu_http import search_migu
from app.services.scrape.providers.netease_http import search_netease
from app.services.scrape.providers.smart_cn_provider import _search_qq_via_musicdl


def _result_score(query: ScrapeQuery, row: dict) -> float:
    return float(score_candidate(
        query_title=query.title, query_artist=query.artist, query_duration=query.duration,
        cand_title=row.get("title"), cand_artist=row.get("artist"), cand_album=row.get("album"), cand_duration=row.get("duration"),
    ).get("total") or 0)


def _result_from_rows(name: str, query: ScrapeQuery, rows: list[dict]) -> Optional[ScrapeResult]:
    if not rows:
        return None
    best = max(rows, key=lambda row: _result_score(query, row))
    score = _result_score(query, best)
    if score <= 0:
        return None
    return ScrapeResult(
        title=best.get("title"), artist=best.get("artist"), album=best.get("album"),
        duration=best.get("duration"), cover_url=best.get("cover_url"), provider=name,
        score=float(score), raw=best,
    )


class NetEaseProvider:
    name = "netease"
    priority = 10

    def lookup(self, query: ScrapeQuery, *, timeout: float = 8.0) -> Optional[ScrapeResult]:
        return _result_from_rows(self.name, query, search_netease(" ".join(filter(None, [query.title, query.artist])), timeout=timeout))


class QQProvider:
    name = "qq"
    priority = 30

    def __init__(self, db=None):
        self.db = db

    def lookup(self, query: ScrapeQuery, *, timeout: float = 8.0) -> Optional[ScrapeResult]:
        keyword = " ".join(filter(None, [query.title, query.artist]))
        return _result_from_rows(self.name, query, _search_qq_via_musicdl(keyword, timeout=timeout, db=self.db))


class MiguProvider:
    name = "migu"
    priority = 20

    def lookup(self, query: ScrapeQuery, *, timeout: float = 8.0) -> Optional[ScrapeResult]:
        return _result_from_rows(self.name, query, search_migu(" ".join(filter(None, [query.title, query.artist])), timeout=timeout))
