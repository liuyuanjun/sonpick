"""网易云与咪咕独立歌词 Provider。"""
from __future__ import annotations

from app.services.lyrics_provider import LyricsCandidate, LyricsQuery, score_lyrics_candidate
from app.services.scrape.providers.migu_http import fetch_migu_lyric, search_migu
from app.services.scrape.providers.netease_http import fetch_netease_lyric, search_netease


class DomesticLyricsProvider:
    def __init__(self, source: str, *, timeout: int = 15):
        if source not in {"netease", "migu"}:
            raise ValueError(f"不支持的歌词源: {source}")
        self.name = source
        self.timeout = max(5, min(60, int(timeout)))

    def _candidate(self, row: dict) -> LyricsCandidate:
        return LyricsCandidate(
            source=self.name,
            source_id=str(row.get("id") or ""),
            track_name=str(row.get("title") or ""),
            artist_name=str(row.get("artist") or ""),
            album_name=str(row.get("album") or ""),
            duration=int(row.get("duration") or 0) or None,
            diagnostic={"cover_url": row.get("cover_url")},
        )

    def search(self, query: LyricsQuery, *, limit: int = 20) -> list[LyricsCandidate]:
        keyword = query.keyword or " ".join(filter(None, [query.track_name, query.artist_name]))
        if self.name == "netease":
            rows = search_netease(keyword, limit=limit, timeout=self.timeout)
        else:
            rows = search_migu(keyword, limit=limit, timeout=self.timeout)
        candidates = [score_lyrics_candidate(query, self._candidate(row)) for row in rows]
        return sorted(candidates, key=lambda item: item.score, reverse=True)

    def get(self, source_id: str) -> LyricsCandidate | None:
        lyrics = fetch_netease_lyric(source_id, timeout=self.timeout) if self.name == "netease" else fetch_migu_lyric(source_id, timeout=self.timeout)
        if not lyrics:
            return None
        return LyricsCandidate(
            source=self.name,
            source_id=str(source_id),
            track_name="",
            synced_lyrics=lyrics if "[" in lyrics and "]" in lyrics else None,
            plain_lyrics=None if "[" in lyrics and "]" in lyrics else lyrics,
        )
