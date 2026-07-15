"""Parallel Chinese-source scrape with match scoring (music-tag-web smart_tag style)."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout, as_completed
from typing import Any, Optional

from app.services.scrape.base import ScrapeQuery, ScrapeResult
from app.services.scrape.cover_utils import enrich_cover_fields
from app.services.scrape.match import pick_best_candidate
from app.services.scrape.providers.migu_http import fetch_migu_lyric, search_migu
from app.services.scrape.providers.netease_http import fetch_netease_lyric, search_netease
from app.services.scrape.query_normalize import build_search_keyword, split_title_artist

log = logging.getLogger("sonpick.scrape")


def _search_qq_via_musicdl(keyword: str, *, limit: int = 8, timeout: float = 20.0, db=None) -> list[dict[str, Any]]:
    """QQ via existing musicdl single-source path (no full scrape stack)."""
    try:
        from app.services.musicdl_service import MusicDLService

        svc = MusicDLService(db)

        def _work():
            return svc.search(
                keyword,
                music_sources=["QQMusicClient"],
                search_size_per_source=limit,
                require_download_url=False,
            ) or []

        with ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(_work)
            try:
                items = fut.result(timeout=max(5.0, float(timeout)))
            except FuturesTimeout:
                log.warning("smart_cn QQ search timeout keyword=%r", keyword)
                return []
        out: list[dict[str, Any]] = []
        for it in items or []:
            title = getattr(it, "song_name", None) or getattr(it, "title", None)
            artist = getattr(it, "singers", None) or getattr(it, "artist", None)
            album = getattr(it, "album", None) or getattr(it, "album_name", None)
            cover = getattr(it, "cover_url", None) or getattr(it, "album_pic", None) or getattr(it, "pic", None)
            duration = None
            for key in ("duration", "interval", "song_play_time"):
                val = getattr(it, key, None)
                if val is None:
                    continue
                try:
                    if isinstance(val, str) and ":" in val:
                        a, b = val.split(":", 1)
                        duration = int(a) * 60 + int(float(b))
                    else:
                        n = int(float(val))
                        duration = int(round(n / 1000)) if n > 10000 else n
                    break
                except Exception:
                    continue
            row = {
                "id": getattr(it, "song_id", None) or getattr(it, "id", None) or getattr(it, "mid", None),
                "title": title,
                "artist": artist,
                "album": album,
                "cover_url": cover,
                "duration": duration if duration and duration > 0 else None,
                "source": "qq",
            }
            out.append(enrich_cover_fields(row, it))
        return out
    except Exception as e:
        log.warning("smart_cn QQ search failed keyword=%r err=%s", keyword, e)
        return []


class SmartCNProvider:
    """Parallel Netease + MiGu + QQ, score and pick Top1."""

    name = "smart_cn"
    priority = 20  # after MusicBrainz(10), before musicdl(90)

    def __init__(self, db=None, *, enable_qq: bool = True):
        self.db = db
        self.enable_qq = enable_qq

    def lookup(self, query: ScrapeQuery, *, timeout: float = 45.0) -> Optional[ScrapeResult]:
        title, artist = split_title_artist(query.title, query.artist)
        if not title:
            return None
        keyword = build_search_keyword(title, artist) or title
        per_timeout = max(8.0, min(25.0, float(timeout) * 0.6))

        tasks = {
            "netease": lambda: search_netease(keyword, limit=8, timeout=per_timeout),
            "migu": lambda: search_migu(keyword, limit=8, timeout=per_timeout),
        }
        if self.enable_qq:
            tasks["qq"] = lambda: _search_qq_via_musicdl(
                keyword, limit=8, timeout=per_timeout, db=self.db
            )

        candidates: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=max(1, len(tasks))) as pool:
            futs = {pool.submit(fn): name for name, fn in tasks.items()}
            try:
                for fut in as_completed(futs, timeout=max(12.0, float(timeout))):
                    name = futs[fut]
                    try:
                        rows = fut.result() or []
                    except Exception as e:
                        log.warning("smart_cn source failed source=%s err=%s", name, e)
                        rows = []
                    log.info("smart_cn 搜索结果 source=%s keyword=%r count=%s", name, keyword, len(rows))
                    for i, r in enumerate(rows[:8], 1):
                        log.info(
                            "  [%s/%s] title=%r artist=%r album=%r duration=%s",
                            name,
                            i,
                            r.get("title"),
                            r.get("artist"),
                            r.get("album"),
                            r.get("duration"),
                        )
                    candidates.extend([enrich_cover_fields(r) for r in rows])
            except FuturesTimeout:
                log.warning("smart_cn 并行搜索超时 keyword=%r partial=%s", keyword, len(candidates))

        best, detail = pick_best_candidate(
            candidates,
            query_title=title,
            query_artist=artist or None,
            query_album=query.album,
            query_duration=query.duration,
            simple_mode=not bool(artist),
            min_total=2.0,
        )
        ranked = detail.get("ranked") or []
        if ranked:
            top = ", ".join(
                f"{x.get('source')}:{x.get('title')!r}@{x.get('score')}" for x in ranked[:5]
            )
            log.info("smart_cn 打分 top=%s", top)
        if not best:
            log.info(
                "smart_cn 未命中 keyword=%r best_total=%s",
                keyword,
                detail.get("total"),
            )
            return None

        lyrics = ""
        src = (best.get("source") or "").lower()
        sid = best.get("id")
        try:
            if src == "netease":
                lyrics = fetch_netease_lyric(sid, timeout=min(10.0, per_timeout))
            elif src == "migu":
                lyrics = fetch_migu_lyric(sid, timeout=min(10.0, per_timeout))
        except Exception as e:
            log.debug("smart_cn lyric skip err=%s", e)

        score = float(detail.get("total") or 0)
        log.info(
            "smart_cn 命中 score=%s source=%s title=%r artist=%r album=%r",
            score,
            src,
            best.get("title"),
            best.get("artist"),
            best.get("album"),
        )
        return ScrapeResult(
            title=best.get("title") or title,
            artist=best.get("artist") or artist or None,
            album=best.get("album") or None,
            duration=best.get("duration"),
            cover_url=best.get("cover_url"),
            lyrics=lyrics or None,
            provider=f"smart_cn:{src}",
            score=score,
            raw={
                "source": src,
                "id": sid,
                "match": {
                    k: detail.get(k)
                    for k in ("title", "artist", "album", "duration_bonus", "total")
                },
                "keyword": keyword,
            },
        )
