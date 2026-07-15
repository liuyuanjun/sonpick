"""Persistent scrape cache helpers."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session


def _norm(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"[\s\-_/、,，]+", "", str(s).lower().strip())


def make_cache_key(title: str, artist: str | None = None, duration: int | None = None) -> str:
    t = _norm(title)
    a = _norm(artist)
    # bucket duration to 3s to improve hit rate
    d = ""
    try:
        if duration and int(duration) > 0:
            d = str(int(round(int(duration) / 3.0) * 3))
    except Exception:
        d = ""
    raw = f"{t}|{a}|{d}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def cache_get(db: Session | None, title: str, artist: str | None = None, duration: int | None = None) -> dict[str, Any]:
    if db is None:
        return {}
    from app.models import ScrapeCache

    key = make_cache_key(title, artist, duration)
    row = db.query(ScrapeCache).filter(ScrapeCache.cache_key == key).first()
    if not row:
        # try without duration bucket
        key2 = make_cache_key(title, artist, None)
        if key2 != key:
            row = db.query(ScrapeCache).filter(ScrapeCache.cache_key == key2).first()
    if not row:
        return {}
    try:
        row.hit_count = int(row.hit_count or 0) + 1
        row.updated_at = datetime.now(timezone.utc)
        db.add(row)
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    out = {
        "title": row.title,
        "artist": row.artist,
        "album": row.album,
        "duration": row.duration,
        "cover_url": row.cover_url,
        "provider": row.provider,
        "score": row.score,
        "cached": True,
    }
    try:
        payload = json.loads(row.payload_json or "{}")
        if isinstance(payload, dict):
            out["payload"] = payload
    except Exception:
        pass
    return out


def cache_put(
    db: Session | None,
    *,
    title: str,
    artist: str | None = None,
    duration: int | None = None,
    album: str | None = None,
    cover_url: str | None = None,
    provider: str | None = None,
    score: int = 0,
    payload: dict | None = None,
) -> None:
    if db is None or not (album or cover_url):
        return
    from app.models import ScrapeCache

    key = make_cache_key(title, artist, duration)
    try:
        row = db.query(ScrapeCache).filter(ScrapeCache.cache_key == key).first()
        if not row:
            row = ScrapeCache(cache_key=key)
        row.title = title
        row.artist = artist
        row.album = album
        row.duration = int(duration) if duration else None
        row.cover_url = cover_url
        row.provider = provider
        row.score = int(score or 0)
        row.payload_json = json.dumps(payload or {}, ensure_ascii=False)
        row.updated_at = datetime.now(timezone.utc)
        db.add(row)
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
