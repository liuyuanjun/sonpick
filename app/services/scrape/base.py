"""Multi-source metadata scrape contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


@dataclass
class ScrapeQuery:
    title: str
    artist: Optional[str] = None
    album: Optional[str] = None
    duration: Optional[int] = None  # seconds


@dataclass
class ScrapeResult:
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    duration: Optional[int] = None
    cover_url: Optional[str] = None
    lyrics: Optional[str] = None
    provider: str = ""
    score: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)

    def has_any(self, fields: set[str] | None = None) -> bool:
        keys = fields or {"title", "artist", "album", "duration", "cover_url", "lyrics"}
        for k in keys:
            v = getattr(self, k, None)
            if isinstance(v, str) and v.strip():
                return True
            if isinstance(v, (int, float)) and v:
                return True
        return False


class ScrapeProvider(Protocol):
    """A single metadata scrape source."""

    name: str
    priority: int  # smaller = higher priority

    def lookup(self, query: ScrapeQuery, *, timeout: float = 8.0) -> Optional[ScrapeResult]:
        ...
