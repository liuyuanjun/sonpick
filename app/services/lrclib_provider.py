"""LRCLIB 只读客户端，包含节流、缓存和 429 退避。"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app.services.lyrics_provider import LyricsCandidate, LyricsQuery, score_lyrics_candidate

_BASE_URL = "https://lrclib.net"
_USER_AGENT = "Sonpick/0.13.0-rc2 (https://github.com/liuyuanjun/sonpick)"


class LrclibRateLimitError(RuntimeError):
    def __init__(self, retry_after: int):
        super().__init__(f"LRCLIB 请求过于频繁，请在 {retry_after} 秒后重试")
        self.retry_after = retry_after


class LrclibProvider:
    name = "lrclib"
    _lock = threading.Lock()
    _last_request_at = 0.0
    _blocked_until = 0.0
    _cache: dict[str, tuple[float, Any]] = {}

    def __init__(self, *, timeout: int = 18, minimum_interval: float = 0.3):
        self.timeout = max(5, min(60, int(timeout)))
        self.minimum_interval = max(0.2, min(0.5, float(minimum_interval)))

    @classmethod
    def _cached(cls, key: str) -> Any | None:
        row = cls._cache.get(key)
        if not row:
            return None
        expires, value = row
        if expires <= time.monotonic():
            cls._cache.pop(key, None)
            return None
        return value

    def _request(self, path: str, params: dict[str, Any] | None = None) -> Any:
        query = urllib.parse.urlencode({key: value for key, value in (params or {}).items() if value not in (None, "")})
        url = f"{_BASE_URL}{path}" + (f"?{query}" if query else "")
        cached = self._cached(url)
        if cached is not None:
            return cached
        with self._lock:
            cached = self._cached(url)
            if cached is not None:
                return cached
            cls = type(self)
            now = time.monotonic()
            if now < cls._blocked_until:
                raise LrclibRateLimitError(max(1, int(cls._blocked_until - now)))
            delay = self.minimum_interval - (now - cls._last_request_at)
            if delay > 0:
                time.sleep(delay)
            request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": _USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8", errors="replace"))
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    return None
                if exc.code == 429:
                    try:
                        retry_after = max(1, min(60, int(exc.headers.get("Retry-After") or 5)))
                    except (TypeError, ValueError):
                        retry_after = 5
                    cls._blocked_until = time.monotonic() + retry_after
                    raise LrclibRateLimitError(retry_after) from exc
                raise RuntimeError(f"LRCLIB 请求失败: HTTP {exc.code}") from exc
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                raise RuntimeError(f"LRCLIB 请求失败: {type(exc).__name__}: {exc}") from exc
            finally:
                cls._last_request_at = time.monotonic()
            self._cache[url] = (time.monotonic() + 300, payload)
            return payload

    @staticmethod
    def _candidate(row: dict[str, Any]) -> LyricsCandidate:
        return LyricsCandidate(
            source="lrclib",
            source_id=str(row.get("id") or ""),
            track_name=str(row.get("trackName") or ""),
            artist_name=str(row.get("artistName") or ""),
            album_name=str(row.get("albumName") or ""),
            duration=int(row.get("duration") or 0) or None,
            synced_lyrics=row.get("syncedLyrics") or None,
            plain_lyrics=row.get("plainLyrics") or None,
            instrumental=bool(row.get("instrumental")),
        )

    def get(self, source_id: str) -> LyricsCandidate | None:
        row = self._request(f"/api/get/{urllib.parse.quote(str(source_id))}")
        return self._candidate(row) if isinstance(row, dict) else None

    def search(self, query: LyricsQuery, *, limit: int = 20) -> list[LyricsCandidate]:
        rows: list[dict[str, Any]] = []
        if query.track_name and query.artist_name and query.album_name and query.duration:
            exact = self._request(
                "/api/get",
                {
                    "track_name": query.track_name,
                    "artist_name": query.artist_name,
                    "album_name": query.album_name,
                    "duration": int(query.duration),
                },
            )
            if isinstance(exact, dict):
                candidate = score_lyrics_candidate(query, self._candidate(exact))
                candidate.diagnostic["match_mode"] = "exact"
                return [candidate]
        params = {"q": query.keyword or " ".join(filter(None, [query.track_name, query.artist_name]))}
        if not query.keyword:
            params = {
                "track_name": query.track_name,
                "artist_name": query.artist_name or None,
                "album_name": query.album_name or None,
            }
        payload = self._request("/api/search", params)
        if isinstance(payload, list):
            rows = payload[: max(1, min(20, int(limit)))]
        candidates = [score_lyrics_candidate(query, self._candidate(row)) for row in rows]
        for candidate in candidates:
            candidate.diagnostic["match_mode"] = "search"
        return sorted(candidates, key=lambda item: item.score, reverse=True)
