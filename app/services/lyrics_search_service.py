"""独立歌词搜索、应用与批量补全服务。"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models import AppSettings, Song, SongFile
from app.services.domestic_lyrics_provider import DomesticLyricsProvider
from app.services.lrclib_provider import LrclibProvider
from app.services.lyrics_provider import LyricsCandidate, LyricsQuery
from app.services.lyrics_source_registry import select_lyrics_source_configs
from app.services.media_meta_service import read_audio_duration, write_audio_tags
from app.services.lyrics_service import load_lyrics_for_song
from app.services.song_file_resolver import NoPlayableSongFileError, SongFileResolver


class LyricsApplicationError(RuntimeError):
    def __init__(self, message: str, *, code: str = "lyrics_error", retry_after: int | None = None):
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after

    def detail(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": str(self)}
        if self.retry_after is not None:
            payload["retry_after"] = self.retry_after
        return payload


class LyricsSearchService:
    def __init__(self, db: Session):
        self.db = db

    def _song_file(self, song: Song) -> SongFile | None:
        try:
            return SongFileResolver(self.db).resolve_local(song)
        except NoPlayableSongFileError:
            return None

    def query_for_song(self, song: Song, *, keyword: str = "") -> LyricsQuery:
        song_file = self._song_file(song)
        duration = song.duration or (read_audio_duration(song_file.local_path) if song_file else None)
        return LyricsQuery(
            track_name=song.title or "",
            artist_name=song.artist or "",
            album_name=song.album or "",
            duration=int(duration) if duration else None,
            keyword=keyword.strip(),
        )

    def source_configs(self, *, automatic: bool) -> list[dict[str, Any]]:
        settings = self.db.get(AppSettings, 1)
        return select_lyrics_source_configs(
            getattr(settings, "lyrics_sources_json", None),
            automatic=automatic,
            scrape_raw=getattr(settings, "scrape_sources_json", None),
        )

    @staticmethod
    def provider(config: dict[str, Any]):
        if config["id"] == "lrclib":
            return LrclibProvider(timeout=config.get("timeout", 18))
        return DomesticLyricsProvider(config["id"], timeout=config.get("timeout", 15))

    def search(self, song: Song, *, source: str = "auto", keyword: str = "", limit: int = 20) -> dict[str, Any]:
        query = self.query_for_song(song, keyword=keyword)
        configs = self.source_configs(automatic=source == "auto")
        if source != "auto":
            configs = [item for item in configs if item["id"] == source]
            if not configs:
                raise LyricsApplicationError("该歌词源未启用", code="source_disabled")
        candidates: list[LyricsCandidate] = []
        errors = []
        for config in configs:
            try:
                candidates.extend(self.provider(config).search(query, limit=limit))
            except Exception as exc:
                from app.services.lrclib_provider import LrclibRateLimitError

                if isinstance(exc, LrclibRateLimitError):
                    errors.append({
                        "source": config["id"],
                        "code": "rate_limited",
                        "message": str(exc),
                        "retry_after": exc.retry_after,
                    })
                else:
                    errors.append({"source": config["id"], "code": "provider_error", "message": str(exc)})
        candidates.sort(key=lambda item: item.score, reverse=True)
        return {
            "query": {
                "track_name": query.track_name,
                "artist_name": query.artist_name,
                "album_name": query.album_name,
                "duration": query.duration,
                "keyword": query.keyword,
                "complete_signature": bool(query.track_name and query.artist_name and query.album_name and query.duration),
            },
            "current": self.current_lyrics(song),
            "candidates": [item.to_dict(include_lyrics=True) for item in candidates[: max(1, min(20, limit))]],
            "errors": errors,
        }

    def details(self, source: str, source_id: str, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
        config = next((item for item in self.source_configs(automatic=False) if item["id"] == source), None)
        if not config:
            raise LyricsApplicationError("该歌词源未启用", code="source_disabled")
        fallback = fallback or {}
        if source == "lrclib" and (
            fallback.get("synced_lyrics")
            or fallback.get("plain_lyrics")
            or fallback.get("instrumental")
        ):
            return dict(fallback)
        try:
            candidate = self.provider(config).get(source_id)
        except Exception as exc:
            from app.services.lrclib_provider import LrclibRateLimitError

            if isinstance(exc, LrclibRateLimitError):
                raise LyricsApplicationError(
                    str(exc),
                    code="rate_limited",
                    retry_after=exc.retry_after,
                ) from exc
            if isinstance(exc, TimeoutError):
                raise LyricsApplicationError("歌词来源请求超时", code="provider_timeout") from exc
            raise LyricsApplicationError(f"歌词来源请求失败: {exc}", code="provider_error") from exc
        if not candidate:
            raise LyricsApplicationError("该歌词候选没有可用内容", code="lyrics_not_found")
        candidate.track_name = candidate.track_name or str(fallback.get("track_name") or "")
        candidate.artist_name = candidate.artist_name or str(fallback.get("artist_name") or "")
        candidate.album_name = candidate.album_name or str(fallback.get("album_name") or "")
        candidate.duration = candidate.duration or fallback.get("duration")
        candidate.score = float(fallback.get("score") or 0)
        candidate.match_detail = dict(fallback.get("match_detail") or {})
        return candidate.to_dict(include_lyrics=True)

    def current_lyrics(self, song: Song) -> dict[str, Any]:
        _lines, raw, resolved = load_lyrics_for_song(song, db=self.db, persist=True)
        text = str(raw or "").strip()
        return {
            "text": text,
            "has_lyrics": bool(text),
            "path": resolved,
            "source": getattr(song, "lyrics_provider", None),
            "source_id": getattr(song, "lyrics_source_id", None),
            "lyrics_type": getattr(song, "lyrics_type", None),
            "score": getattr(song, "lyrics_score", None),
            "fetched_at": getattr(song, "lyrics_fetched_at", None).isoformat() if getattr(song, "lyrics_fetched_at", None) else None,
            "instrumental": bool(getattr(song, "lyrics_instrumental", False)),
        }

    def clear(self, song: Song, *, write_file_tags: bool = True) -> dict[str, Any]:
        resolver = SongFileResolver(self.db)
        all_files = resolver.all_files(song)
        writable_files = resolver.writable_local_files(song)
        writable_ids = {item.id for item in writable_files}
        removed_paths: list[str] = []
        results: list[dict[str, Any]] = []
        aggregate_paths = {Path(str(song.lrc_path))} if song.lrc_path else set()

        for song_file in all_files:
            base = {
                "song_file_id": song_file.id,
                "path": song_file.local_path or song_file.webdav_path,
                "format": song_file.format,
            }
            if song_file.id not in writable_ids:
                results.append({**base, "status": "skipped", "reason": "远端只读，未写入" if song_file.webdav_path else "本地文件不可用"})
                continue
            paths = set(aggregate_paths)
            if song_file.lrc_path:
                paths.add(Path(str(song_file.lrc_path)))
            audio_path = Path(song_file.local_path)
            paths.update({audio_path.with_suffix(".lrc"), audio_path.with_suffix(".LRC"), audio_path.with_suffix(".txt"), audio_path.with_suffix(".TXT")})
            try:
                for path in paths:
                    if path.is_file():
                        path.unlink()
                        removed_paths.append(str(path))
                tags = write_audio_tags(song_file.local_path, clear_fields={"lyrics"}) if write_file_tags else {}
                if write_file_tags and not tags:
                    raise RuntimeError("内嵌歌词清空未生效")
                song_file.lrc_path = None
                song_file.updated_at = datetime.now(timezone.utc)
                self.db.add(song_file)
                results.append({**base, "status": "written", "tags": tags})
            except Exception as exc:
                results.append({**base, "status": "failed", "error": str(exc)})

        song.lrc_path = None
        song.lyrics_provider = None
        song.lyrics_source_id = None
        song.lyrics_type = None
        song.lyrics_score = None
        song.lyrics_fetched_at = None
        song.lyrics_instrumental = False
        song.updated_at = datetime.now(timezone.utc)
        self.db.add(song)
        self.db.commit()
        failed = sum(item["status"] == "failed" for item in results)
        written = sum(item["status"] == "written" for item in results)
        return {
            "ok": failed == 0,
            "partial": failed > 0 and written > 0,
            "song_id": song.id,
            "removed_paths": sorted(set(removed_paths)),
            "written_file_tags": written,
            "versions": results,
            "lyrics_type": None,
            "source": None,
            "source_id": None,
            "lrc_path": None,
        }

    def apply(
        self,
        song: Song,
        candidate: dict[str, Any],
        *,
        write_file_tags: bool = True,
    ) -> dict[str, Any]:
        instrumental = bool(candidate.get("instrumental"))
        synced = str(candidate.get("synced_lyrics") or "").strip()
        plain = str(candidate.get("plain_lyrics") or "").strip()
        lyrics = synced or plain
        if not lyrics and not instrumental:
            raise LyricsApplicationError("空歌词不能覆盖已有歌词", code="empty_lyrics")
        resolver = SongFileResolver(self.db)
        all_files = resolver.all_files(song)
        writable_files = resolver.writable_local_files(song)
        if not writable_files:
            raise LyricsApplicationError("当前歌曲没有可写入的本地文件", code="no_local_file")
        writable_ids = {item.id for item in writable_files}
        results: list[dict[str, Any]] = []
        aggregate_lrc_path = None
        for song_file in all_files:
            base = {
                "song_file_id": song_file.id,
                "path": song_file.local_path or song_file.webdav_path,
                "format": song_file.format,
            }
            if song_file.id not in writable_ids:
                results.append({**base, "status": "skipped", "reason": "远端只读，未写入" if song_file.webdav_path else "本地文件不可用"})
                continue
            destination = Path(song_file.local_path).with_suffix(".lrc")
            try:
                if lyrics:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_text(lyrics, encoding="utf-8")
                    song_file.lrc_path = str(destination)
                    aggregate_lrc_path = aggregate_lrc_path or str(destination)
                else:
                    if destination.is_file():
                        destination.unlink()
                    song_file.lrc_path = None
                tags = write_audio_tags(
                    song_file.local_path,
                    lyrics=lyrics or None,
                    clear_fields={"lyrics"} if not lyrics else None,
                ) if write_file_tags else {}
                if write_file_tags and not tags:
                    raise RuntimeError("内嵌歌词写入未生效")
                self.db.add(song_file)
                results.append({**base, "status": "written", "lrc_path": song_file.lrc_path, "tags": tags})
            except Exception as exc:
                results.append({**base, "status": "failed", "error": str(exc)})
        song.lrc_path = aggregate_lrc_path
        song.lyrics_provider = str(candidate.get("source") or "manual")
        song.lyrics_source_id = str(candidate.get("source_id") or "") or None
        song.lyrics_type = "instrumental" if instrumental else ("synced" if synced else ("plain" if plain else "empty"))
        song.lyrics_score = max(0, min(100, int(round(float(candidate.get("score") or 0)))))
        song.lyrics_fetched_at = datetime.now(timezone.utc)
        song.lyrics_instrumental = instrumental
        song.updated_at = datetime.now(timezone.utc)
        self.db.add(song)
        self.db.commit()
        failed = sum(item["status"] == "failed" for item in results)
        written = sum(item["status"] == "written" for item in results)
        return {
            "ok": failed == 0,
            "partial": failed > 0 and written > 0,
            "song_id": song.id,
            "lrc_path": song.lrc_path,
            "lyrics_type": song.lyrics_type,
            "source": song.lyrics_provider,
            "source_id": song.lyrics_source_id,
            "written_file_tags": written if write_file_tags else 0,
            "versions": results,
        }
