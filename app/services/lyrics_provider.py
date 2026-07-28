"""统一歌词候选、匹配与 Provider 协议。"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

_VERSION_WORDS = ("live", "现场", "伴奏", "instrumental", "翻唱", "cover", "remix", "重制", "remaster")


def _norm(value: str | None) -> str:
    return re.sub(r"[\W_]+", "", str(value or "").lower())


def _version_flags(value: str | None) -> set[str]:
    text = str(value or "").lower()
    return {word for word in _VERSION_WORDS if word in text}


@dataclass
class LyricsQuery:
    track_name: str
    artist_name: str = ""
    album_name: str = ""
    duration: int | None = None
    keyword: str = ""


@dataclass
class LyricsCandidate:
    source: str
    source_id: str
    track_name: str
    artist_name: str = ""
    album_name: str = ""
    duration: int | None = None
    synced_lyrics: str | None = None
    plain_lyrics: str | None = None
    instrumental: bool = False
    score: float = 0.0
    match_detail: dict[str, Any] = field(default_factory=dict)
    diagnostic: dict[str, Any] = field(default_factory=dict)

    @property
    def lyrics_type(self) -> str:
        if self.instrumental:
            return "instrumental"
        if self.synced_lyrics:
            return "synced"
        if self.plain_lyrics:
            return "plain"
        return "empty"

    def to_dict(self, *, include_lyrics: bool = True) -> dict[str, Any]:
        data = asdict(self)
        data["lyrics_type"] = self.lyrics_type
        data["has_synced"] = bool(self.synced_lyrics)
        data["has_plain"] = bool(self.plain_lyrics)
        if not include_lyrics:
            data.pop("synced_lyrics", None)
            data.pop("plain_lyrics", None)
        return data


class LyricsProvider(Protocol):
    name: str

    def search(self, query: LyricsQuery, *, limit: int = 20) -> list[LyricsCandidate]: ...

    def get(self, source_id: str) -> LyricsCandidate | None: ...


def score_lyrics_candidate(query: LyricsQuery, candidate: LyricsCandidate) -> LyricsCandidate:
    title_match = 1.0 if _norm(query.track_name) == _norm(candidate.track_name) else 0.0
    artist_match = 1.0 if query.artist_name and _norm(query.artist_name) == _norm(candidate.artist_name) else 0.0
    album_match = 1.0 if query.album_name and _norm(query.album_name) == _norm(candidate.album_name) else 0.0
    duration_delta = None
    duration_score = 0.0
    if query.duration and candidate.duration:
        duration_delta = abs(int(query.duration) - int(candidate.duration))
        duration_score = max(0.0, 1.0 - duration_delta / 12.0)
    version_mismatch = _version_flags(query.track_name) != _version_flags(candidate.track_name)
    score = title_match * 55 + artist_match * 25 + album_match * 8 + duration_score * 12
    if version_mismatch:
        score -= 20
    if candidate.instrumental and "伴奏" not in str(query.track_name) and "instrumental" not in str(query.track_name).lower():
        score -= 12
    candidate.score = round(max(0.0, score), 2)
    candidate.match_detail = {
        "title_match": bool(title_match),
        "artist_match": bool(artist_match),
        "album_match": bool(album_match),
        "duration_delta": duration_delta,
        "version_mismatch": version_mismatch,
    }
    return candidate
