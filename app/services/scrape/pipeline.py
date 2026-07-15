"""Scrape pipeline: try providers by priority until fields are filled."""
from __future__ import annotations

import logging
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Optional, TYPE_CHECKING

from app.services.scrape.base import ScrapeQuery, ScrapeResult
from app.services.scrape.cover_utils import download_cover_with_diagnostics

log = logging.getLogger("sonpick.scrape")
from app.services.scrape.query_normalize import clean_artist, clean_title, looks_like_opaque_id, repair_shifted_meta, split_title_artist
from app.services.scrape.providers.musicbrainz import MusicBrainzProvider
from app.services.scrape.providers.musicdl_provider import MusicDLProvider
from app.services.scrape.providers.smart_cn_provider import SmartCNProvider

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.models import Song


def default_providers(db: "Session | None" = None) -> list:
    """MusicBrainz → SmartCN(并行华语打分) → musicdl 兜底。"""
    return [
        MusicBrainzProvider(),
        SmartCNProvider(db=db),
        MusicDLProvider(db=db),
    ]



class ScrapePipeline:
    def __init__(
        self,
        providers: Iterable | None = None,
        *,
        db: Session | None = None,
        timeout_per_provider: float = 80.0,
        total_timeout: float = 150.0,
    ):
        self.db = db
        self.providers = list(providers) if providers is not None else default_providers(db)
        self.providers.sort(key=lambda p: getattr(p, "priority", 100))
        self.timeout_per_provider = float(timeout_per_provider)
        self.total_timeout = float(total_timeout)

    def lookup(
        self,
        query: ScrapeQuery,
        *,
        need_fields: set[str] | None = None,
    ) -> Optional[ScrapeResult]:
        """Try providers in priority order; merge first useful hits."""
        need = need_fields or {"album", "artist", "title", "duration", "cover_url"}
        merged = ScrapeResult()
        remaining = set(need)
        import time

        started = time.monotonic()
        tried: list[str] = []
        for prov in self.providers:
            if time.monotonic() - started >= self.total_timeout:
                break
            if not remaining:
                break
            name = getattr(prov, "name", prov.__class__.__name__)
            tried.append(name)
            budget = min(
                self.timeout_per_provider,
                max(1.0, self.total_timeout - (time.monotonic() - started)),
            )
            try:
                log.info(
                    "provider 查询 name=%s title=%r artist=%r budget=%.1fs remaining=%s",
                    name,
                    query.title,
                    query.artist,
                    budget,
                    sorted(remaining),
                )
                hit = prov.lookup(query, timeout=budget)
            except Exception as e:
                log.warning("provider 异常 name=%s err=%s: %s", name, type(e).__name__, e)
                hit = None
            if not hit:
                log.info("provider 未命中 name=%s", name)
                continue
            log.info(
                "provider 命中 name=%s title=%r artist=%r album=%r duration=%s score=%s",
                name,
                getattr(hit, "title", None),
                getattr(hit, "artist", None),
                getattr(hit, "album", None),
                getattr(hit, "duration", None),
                getattr(hit, "score", None),
            )
            for key in ("title", "artist", "album", "duration", "cover_url", "lyrics"):
                val = getattr(hit, key, None)
                if val in (None, "", 0):
                    continue
                cur = getattr(merged, key, None)
                if cur in (None, "", 0):
                    setattr(merged, key, val)
                    remaining.discard(key)
            if not merged.provider:
                merged.provider = hit.provider or name
            else:
                merged.provider = f"{merged.provider}+{hit.provider or name}"
            if hit.score:
                merged.score = max(merged.score, float(hit.score))
            if hit.raw:
                merged.raw.setdefault("by_provider", {})[name] = hit.raw
        merged.raw["tried"] = tried
        if not merged.has_any(need):
            return None
        return merged


def default_pipeline(db: Session | None = None, **kwargs) -> ScrapePipeline:
    return ScrapePipeline(db=db, **kwargs)


def lookup_album_via_pipeline(
    title: str,
    artist: str | None = None,
    duration: int | None = None,
    *,
    db: "Session | None" = None,
    timeout_per_provider: float = 80.0,
    total_timeout: float = 150.0,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Convenience for reorganize / album fill. Uses scrape_cache when available."""
    from app.services.scrape.cache import cache_get, cache_put

    if use_cache:
        cached = cache_get(db, title, artist, duration)
        if cached.get("album"):
            return cached

    pipe = default_pipeline(
        db,
        timeout_per_provider=timeout_per_provider,
        total_timeout=total_timeout,
    )
    hit = pipe.lookup(
        ScrapeQuery(title=title, artist=artist, duration=duration),
        need_fields={"album", "artist", "title", "duration", "cover_url"},
    )
    if not hit:
        return {}
    out: dict[str, Any] = {}
    if hit.title:
        out["title"] = hit.title
    if hit.artist:
        out["artist"] = hit.artist
    if hit.album:
        out["album"] = hit.album
    if hit.duration:
        out["duration"] = hit.duration
    if hit.cover_url:
        out["cover_url"] = hit.cover_url
    out["provider"] = hit.provider
    out["score"] = hit.score
    if use_cache and out.get("album"):
        cache_put(
            db,
            title=title,
            artist=artist,
            duration=duration or out.get("duration"),
            album=out.get("album"),
            cover_url=out.get("cover_url"),
            provider=out.get("provider"),
            score=int(out.get("score") or 0),
            payload=out,
        )
    return out


def _download_cover(url: str, dest: Path, *, timeout: float = 8.0) -> Optional[Path]:
    if not url or not dest:
        return None
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Sonpick/0.5.2 (personal music library)"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        if not data or len(data) < 100:
            return None
        # basic image sniff
        ext = ".jpg"
        if data.startswith(b"\x89PNG"):
            ext = ".png"
        if dest.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            dest = dest.with_suffix(ext)
        dest.write_bytes(data)
        return dest
    except Exception:
        return None


def enrich_song_via_pipeline(
    song: "Song",
    *,
    db: "Session | None" = None,
    timeout_per_provider: float = 80.0,
    total_timeout: float = 150.0,
    download_cover: bool = True,
    write_lyrics: bool = True,
) -> dict[str, Any]:
    """Fill missing song fields via multi-provider pipeline. Returns changed keys."""
    from app.services.media_meta_service import is_local_file, read_audio_duration
    from app.services.library_layout import is_generic_dir_name

    raw_title = (song.title or "").strip()
    raw_artist = (song.artist or "").strip() if song.artist else ""
    raw_album = (song.album or "").strip() if song.album else ""
    repaired_title, repaired_artist, repaired_album = repair_shifted_meta(raw_title, raw_artist, raw_album)
    split_t, split_a = split_title_artist(repaired_title or raw_title, repaired_artist or raw_artist)
    cleaned_title = split_t or clean_title(repaired_title or raw_title) or raw_title
    cleaned_artist = split_a or repaired_artist or (clean_artist(raw_artist) if raw_artist else "")
    title = cleaned_title

    # 优先本地读时长（mutagen/tinytag/ffprobe），匹配用；不靠网络
    local_duration_filled = False
    if (not song.duration or int(song.duration or 0) <= 0) and is_local_file(getattr(song, "local_path", None)):
        local_dur = read_audio_duration(song.local_path)
        if local_dur and int(local_dur) > 0:
            song.duration = int(local_dur)
            local_duration_filled = True

    needs_album = not (song.album and str(song.album).strip()) or is_generic_dir_name(song.album)
    needs_duration = not song.duration or int(song.duration or 0) <= 0
    has_local_cover = bool(song.cover_path and is_local_file(song.cover_path))
    needs_cover = not has_local_cover
    has_local_lrc = bool(song.lrc_path and Path(str(song.lrc_path)).is_file())
    needs_lyrics = not has_local_lrc
    needs_artist = (not raw_artist) or is_generic_dir_name(raw_artist) or looks_like_opaque_id(raw_artist)
    needs_title_cleanup = bool(cleaned_title and cleaned_title != raw_title)
    needs_artist_split = bool(cleaned_artist and cleaned_artist != raw_artist)
    needs_album_cleanup = bool(repaired_album != raw_album and looks_like_opaque_id(raw_title))

    if not (needs_album or needs_duration or needs_cover or needs_lyrics or needs_artist or needs_title_cleanup or needs_artist_split or needs_album_cleanup or local_duration_filled):
        return {}

    if not title:
        return {}

    need_fields = set()
    if needs_album:
        need_fields.add("album")
    if needs_artist:
        need_fields.add("artist")
    if needs_duration:
        need_fields.add("duration")
    if needs_cover:
        need_fields.add("cover_url")
    if needs_lyrics:
        need_fields.add("lyrics")
    # 标题被 mid 污染时，即使其它字段看似齐全也要重查
    if needs_title_cleanup:
        need_fields.update({"album", "artist", "title"})
    if not need_fields:
        filled: dict[str, Any] = {}
        if local_duration_filled and song.duration:
            filled["duration"] = song.duration
        if needs_title_cleanup:
            song.title = cleaned_title
            filled["title"] = cleaned_title
        if cleaned_artist and (needs_artist or needs_artist_split or looks_like_opaque_id(raw_artist)):
            song.artist = cleaned_artist
            filled["artist"] = cleaned_artist
        if needs_album_cleanup:
            song.album = repaired_album or None
            filled["album"] = song.album
        return filled

    pipe = default_pipeline(
        db,
        timeout_per_provider=timeout_per_provider,
        total_timeout=total_timeout,
    )

    hit = pipe.lookup(
        ScrapeQuery(
            title=title,
            artist=cleaned_artist or (None if needs_artist else song.artist),
            album=None if needs_album else song.album,
            duration=song.duration,
        ),
        need_fields=need_fields or {"album", "artist", "title"},
    )
    if not hit:
        # still fix local title/artist fusion even if network miss
        filled: dict[str, Any] = {}
        if local_duration_filled and song.duration:
            filled["duration"] = song.duration
        if needs_title_cleanup:
            song.title = cleaned_title
            filled["title"] = cleaned_title
        if cleaned_artist and (needs_artist or needs_artist_split or looks_like_opaque_id(raw_artist)):
            song.artist = cleaned_artist
            filled["artist"] = cleaned_artist
        if needs_album_cleanup:
            song.album = repaired_album or None
            filled["album"] = song.album
        return filled

    filled: dict[str, Any] = {}
    if local_duration_filled and song.duration:
        filled["duration"] = song.duration
    if needs_title_cleanup:
        song.title = cleaned_title
        filled["title"] = cleaned_title
    elif hit.title and (not song.title or looks_like_opaque_id(song.title)):
        song.title = hit.title
        filled["title"] = hit.title
    if needs_artist_split and cleaned_artist:
        song.artist = cleaned_artist
        filled["artist"] = cleaned_artist
    if needs_album_cleanup:
        song.album = repaired_album or None
        filled["album"] = song.album
    if hit.album and (needs_album or needs_album_cleanup or not song.album or is_generic_dir_name(song.album)):
        song.album = hit.album
        filled["album"] = hit.album
    if hit.artist and (needs_artist or needs_artist_split or not song.artist or is_generic_dir_name(song.artist) or looks_like_opaque_id(raw_title)):
        song.artist = hit.artist
        filled["artist"] = hit.artist
    elif hit.artist and (not song.artist or is_generic_dir_name(song.artist)):
        song.artist = hit.artist
        filled["artist"] = hit.artist
    if hit.title and (needs_title_cleanup or not song.title or looks_like_opaque_id(raw_title)):
        song.title = clean_title(hit.title) or hit.title
        filled["title"] = song.title
    if needs_duration and hit.duration:
        try:
            song.duration = int(hit.duration)
            filled["duration"] = song.duration
        except Exception:
            pass
    if needs_lyrics and hit.lyrics:
        lyrics_text = str(hit.lyrics).strip()
        if lyrics_text and write_lyrics:
            lrc_dest = None
            local = song.local_path if is_local_file(getattr(song, "local_path", None)) else None
            if local:
                lrc_dest = Path(local).with_suffix(".lrc")
            elif getattr(song, "lrc_path", None):
                lrc_dest = Path(str(song.lrc_path))
            else:
                tmp = Path("/tmp/sonpick_lyrics")
                tmp.mkdir(parents=True, exist_ok=True)
                lrc_dest = tmp / f"song_{song.id or 'x'}.lrc"
            try:
                lrc_dest.parent.mkdir(parents=True, exist_ok=True)
                lrc_dest.write_text(lyrics_text, encoding="utf-8")
                song.lrc_path = str(lrc_dest)
                filled["lrc_path"] = song.lrc_path
                filled["lyrics"] = True
            except Exception:
                filled["lyrics"] = True
        else:
            filled["lyrics"] = True

    if needs_cover and hit.cover_url and download_cover:
        cover_dest = None
        local = song.local_path if is_local_file(getattr(song, "local_path", None)) else None
        if local:
            cover_dest = Path(local).parent / "cover.jpg"
        else:
            cover_dest = Path("/tmp/sonpick_covers") / f"song_{song.id or 'x'}.jpg"
        cover_result = download_cover_with_diagnostics(hit.cover_url, cover_dest, timeout=min(20.0, timeout_per_provider))
        filled["cover_result"] = cover_result
        if cover_result.get("ok") and cover_result.get("path"):
            song.cover_path = str(cover_result["path"])
            filled["cover_path"] = song.cover_path
            filled["cover_url"] = hit.cover_url
        else:
            log.warning("cover download failed url=%s result=%s", hit.cover_url, cover_result)
    elif needs_cover and hit.cover_url:
        filled["cover_url"] = hit.cover_url

    filled["provider"] = hit.provider
    return filled
