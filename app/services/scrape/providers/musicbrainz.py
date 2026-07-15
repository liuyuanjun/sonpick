"""MusicBrainz + Cover Art Archive provider (stable open API)."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from app.services.scrape.base import ScrapeQuery, ScrapeResult
from app.services.scrape.query_normalize import clean_artist, clean_title

# MusicBrainz requires a descriptive User-Agent.
_UA = "Sonpick/0.5.2 (personal music library; https://github.com/local/sonpick)"
_MB_BASE = "https://musicbrainz.org/ws/2"
_CAA_FRONT = "https://coverartarchive.org/release/{mbid}/front-250"


def _norm(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"[\s\-_/、,，]+", "", str(s).lower().strip())


def _http_json(url: str, *, timeout: float) -> dict[str, Any] | list | None:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        return None
    try:
        return json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:
        return None


def _item_duration_ms(rec: dict[str, Any]) -> int | None:
    length = rec.get("length")
    if length is None:
        return None
    try:
        n = int(length)
        if n > 10000:
            return int(round(n / 1000))
        return n if n > 0 else None
    except Exception:
        return None


def _score(query: ScrapeQuery, title: str, artist: str, duration: int | None) -> float:
    qt = _norm(query.title)
    qa = _norm(query.artist)
    it = _norm(title)
    ia = _norm(artist)
    if not qt or (qt not in it and it not in qt):
        return -1
    score = 0.0
    if it == qt:
        score += 10
    elif qt in it or it in qt:
        score += 5
    if qa and ia:
        if qa == ia:
            score += 10
        elif qa in ia or ia in qa:
            score += 5
    if query.duration and duration:
        diff = abs(int(query.duration) - int(duration))
        if diff <= 3:
            score += 8
        elif diff <= 6:
            score += 3
        elif diff > 15:
            score -= 4
    return score


class MusicBrainzProvider:
    name = "musicbrainz"
    priority = 10  # preferred

    def lookup(self, query: ScrapeQuery, *, timeout: float = 8.0) -> Optional[ScrapeResult]:
        title = clean_title(query.title) or (query.title or "").strip()
        artist = clean_artist(query.artist) if query.artist else ""
        if not title:
            return None
        # use cleaned query for scoring too
        query = ScrapeQuery(title=title, artist=artist or None, album=query.album, duration=query.duration)
        parts = [f'recording:"{title.replace(chr(34), "")}"']
        if artist:
            parts.append(f'artist:"{str(artist).replace(chr(34), "")}"')
        q = " AND ".join(parts)
        url = (
            f"{_MB_BASE}/recording?query={urllib.parse.quote(q)}"
            f"&fmt=json&limit=8"
        )
        data = _http_json(url, timeout=timeout)
        if not isinstance(data, dict):
            return None
        recordings = data.get("recordings") or []
        best: dict[str, Any] | None = None
        best_score = -1.0
        best_artist = ""
        best_album = ""
        best_dur: int | None = None
        best_release_id: str | None = None

        for rec in recordings:
            if not isinstance(rec, dict):
                continue
            rtitle = str(rec.get("title") or "").strip()
            credit = rec.get("artist-credit") or []
            artist_name = ""
            if credit and isinstance(credit, list):
                names = []
                for c in credit:
                    if isinstance(c, dict):
                        n = c.get("name") or (c.get("artist") or {}).get("name")
                        if n:
                            names.append(str(n))
                artist_name = " / ".join(names)
            dur = _item_duration_ms(rec)
            sc = _score(query, rtitle, artist_name, dur)
            if sc < 0:
                continue
            album = ""
            release_id = None
            releases = rec.get("releases") or []
            if releases and isinstance(releases, list):
                rel0 = releases[0] if isinstance(releases[0], dict) else {}
                album = str(rel0.get("title") or "").strip()
                release_id = rel0.get("id")
                if album:
                    sc += 1
            if sc > best_score:
                best_score = sc
                best = rec
                best_artist = artist_name
                best_album = album
                best_dur = dur
                best_release_id = str(release_id) if release_id else None

        min_score = 10 if query.artist else 5
        if not best or best_score < min_score:
            return None

        cover_url = None
        if best_release_id:
            # Cover Art Archive: HEAD/GET front; use direct URL (may 404)
            cover_url = _CAA_FRONT.format(mbid=best_release_id)

        return ScrapeResult(
            title=str(best.get("title") or title).strip() or None,
            artist=best_artist or (query.artist or None),
            album=best_album or None,
            duration=best_dur,
            cover_url=cover_url,
            provider=self.name,
            score=float(best_score),
            raw={"recording_id": best.get("id"), "release_id": best_release_id},
        )
