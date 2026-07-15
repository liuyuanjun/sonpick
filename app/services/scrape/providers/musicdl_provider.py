"""musicdl multi-source scrape provider (Netease → QQ → Migu by default)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Optional

from app.services.scrape.base import ScrapeQuery, ScrapeResult
from app.services.scrape.query_normalize import clean_artist, clean_title, split_title_artist

DEFAULT_SOURCES = [
    "NeteaseMusicClient",
    "QQMusicClient",
    "MiguMusicClient",
]


class MusicDLProvider:
    """Scrape-only provider. Download availability is not required."""

    name = "musicdl"
    priority = 90

    def __init__(self, db=None, music_sources: list[str] | None = None):
        self.db = db
        self.music_sources = list(music_sources or DEFAULT_SOURCES)

    def lookup(self, query: ScrapeQuery, *, timeout: float = 80.0) -> Optional[ScrapeResult]:
        title, artist = split_title_artist(query.title, query.artist)
        if not title:
            title = clean_title(query.title) or (query.title or "").strip()
        if not title:
            return None

        def _work() -> dict[str, Any]:
            from app.services.musicdl_service import MusicDLService

            svc = MusicDLService(self.db)
            # each source gets a solid budget; serial sources need more than 3s on NAS
            n = max(1, len(self.music_sources))
            per = max(25.0, float(timeout) / n)
            return svc.lookup_album_meta(
                title=title,
                artist=artist or None,
                duration=query.duration,
                music_sources=self.music_sources,
                search_size_per_source=8,
                timeout_per_source=per,
            ) or {}

        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(_work)
                data = fut.result(timeout=max(2.0, float(timeout)))
        except FuturesTimeout:
            return None
        except Exception:
            return None

        if not isinstance(data, dict) or not data:
            return None
        album = (data.get("album") or "").strip()
        if not album and not data.get("artist"):
            return None
        return ScrapeResult(
            title=(data.get("title") or title) or None,
            artist=(data.get("artist") or query.artist) or None,
            album=album or None,
            duration=data.get("duration"),
            cover_url=data.get("cover_url"),
            provider=f"musicdl:{(data.get('source') or 'multi')}",
            score=float(data.get("score") or (12 if album else 5)),
            raw=data,
        )
