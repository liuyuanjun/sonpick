import logging
import os
import re
import sys
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from pathlib import Path
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

# 移除当前目录下的 musicdl/ 源码路径，避免与已安装的 musicdl 包冲突
_script_dir = Path(__file__).resolve().parent.parent.parent
for _p in list(sys.path):
    rp = os.path.realpath(_p)
    if rp in (os.path.realpath(os.getcwd()), os.path.realpath(str(_script_dir))):
        sys.path.remove(_p)

from musicdl import musicdl

from app.models import AppSettings, Song, SongFile
from app.services.convert_service import (
    LOSSLESS_FORMATS,
    resolve_lossless_output_dir,
    resolve_mp3_output_dir,
)
from app.services.library_layout import (
    library_relative_dir,
    preferred_album_cover_path,
    track_stem,
    unique_path,
)
from app.services.media_meta_service import enrich_local_audio, is_local_file, write_album_cover_file
from app.services.scrape.query_normalize import (
    build_search_keyword,
    clean_artist,
    clean_title,
    split_title_artist,
)

log = logging.getLogger("sonpick.scrape")
from app.services.scrape.match import score_candidate
from app.services.scrape.cover_utils import extract_cover_url

PREFER_FORMATS = {
    "flac": ["flac"],
    "mp3": ["mp3", "m4a"],
    "m4a": ["m4a", "mp3"],
    "any": [],
}

DEFAULT_DOWNLOAD_SOURCES = [
    "QQMusicClient",
    "NeteaseMusicClient",
    "MiguMusicClient",
]
SOURCE_LABELS = {
    "QQMusicClient": "QQ 音乐",
    "NeteaseMusicClient": "网易云音乐",
    "MiguMusicClient": "咪咕音乐",
}
SEARCH_RETRY_COUNT = 2
SEARCH_RETRY_DELAY_SECONDS = 2
# 单源单次搜索硬超时：musicdl 搜索时会为每条结果逐个探测第三方下载链接 API
#（每个 10s 超时），结果越多越慢。保留硬超时避免线程永久阻塞，但 QQ 音乐
# 的多轮链接探测在网络较慢时可超过 45 秒，因此放宽到 5 分钟。
SEARCH_TIMEOUT_SECONDS = 300
# 搜索页每源结果数：20 条时链接探测要几分钟，必然超时；10 条兼顾体验与耗时。
DEFAULT_SEARCH_SIZE_PER_SOURCE = 10
DEFAULT_SCRAPE_SOURCES = [
    "NeteaseMusicClient",
    "QQMusicClient",
    "MiguMusicClient",
]


class MusicDLService:
    def __init__(self, db: Session, emit: Optional[Callable[[int, str, int], None]] = None):
        self.db = db
        self.emit = emit or (lambda tid, msg, pct: None)
        self.client: Optional[musicdl.MusicClient] = None

    def _new_client(
        self,
        work_dir: Path,
        music_sources: list[str],
        search_size_per_source: int = 20,
    ) -> musicdl.MusicClient:
        """构造独立 client（不触碰 self 状态，可并发使用）。"""
        work_dir.mkdir(parents=True, exist_ok=True)
        cfg = {
            src: {
                "work_dir": str(work_dir),
                "search_size_per_source": int(search_size_per_source),
                "auto_set_proxies": False,
            }
            for src in music_sources
        }
        return musicdl.MusicClient(
            music_sources=music_sources,
            init_music_clients_cfg=cfg,
            clients_threadings={src: 1 for src in music_sources},
        )

    def _init_client(
        self,
        work_dir: Path,
        *,
        music_sources: list[str] | None = None,
        search_size_per_source: int = 20,
    ):
        sources = list(music_sources or DEFAULT_DOWNLOAD_SOURCES)
        if not sources:
            sources = list(DEFAULT_DOWNLOAD_SOURCES)
        self.client = self._new_client(work_dir, sources, search_size_per_source)
        self._client_sources = sources

    def _flatten_search_results(self, results) -> list:
        items: list = []
        if isinstance(results, dict):
            # keep source order when possible
            order = list(getattr(self, "_client_sources", []) or [])
            keys = order + [k for k in results.keys() if k not in order]
            for k in keys:
                v = results.get(k)
                if isinstance(v, list):
                    for it in v:
                        try:
                            setattr(it, "_sonpick_source", k)
                        except Exception:
                            pass
                        items.append(it)
                elif v is not None:
                    items.append(v)
        elif isinstance(results, list):
            items = results
        return items

    @staticmethod
    def _flatten_single_source(results, src: str) -> list:
        items: list = []
        if isinstance(results, dict):
            for k, v in results.items():
                if isinstance(v, list):
                    for it in v:
                        try:
                            setattr(it, "_sonpick_source", k)
                        except Exception:
                            pass
                        items.append(it)
                elif v is not None:
                    items.append(v)
        elif isinstance(results, list):
            items = list(results)
        for it in items:
            try:
                if not getattr(it, "_sonpick_source", None):
                    setattr(it, "_sonpick_source", src)
            except Exception:
                pass
        return items

    def _search_one_source(
        self,
        keyword: str,
        src: str,
        work_dir: Path,
        search_size_per_source: int,
    ) -> tuple[list, str | None]:
        """搜索单个源（含重试与硬超时），返回 (items, error)。"""
        last_error: Exception | None = None
        for attempt in range(SEARCH_RETRY_COUNT):
            pool = ThreadPoolExecutor(max_workers=1)
            try:
                client = self._new_client(work_dir, [src], search_size_per_source)
                results = pool.submit(client.search, keyword=keyword).result(timeout=SEARCH_TIMEOUT_SECONDS)
                return self._flatten_single_source(results, src), None
            except FuturesTimeout:
                last_error = RuntimeError(f"搜索超时（>{SEARCH_TIMEOUT_SECONDS}s）")
            except Exception as exc:
                last_error = exc
            finally:
                pool.shutdown(wait=False, cancel_futures=True)
            if attempt + 1 < SEARCH_RETRY_COUNT:
                time.sleep(SEARCH_RETRY_DELAY_SECONDS)
        return [], f"{SOURCE_LABELS.get(src, src)}: {last_error}"

    def _search_sources(
        self,
        keyword: str,
        *,
        music_sources: list[str] | None,
        work_dir: Path,
        search_size_per_source: int = DEFAULT_SEARCH_SIZE_PER_SOURCE,
    ) -> tuple[list, list[str]]:
        """并发搜索各源并合并结果：单个源挂起/失败不影响其他源，

        总耗时 ≈ 最慢的源而非各源之和。返回 (items, errors)。
        """
        sources = list(music_sources or DEFAULT_DOWNLOAD_SOURCES)
        if not sources:
            sources = list(DEFAULT_DOWNLOAD_SOURCES)
        items: list = []
        errors: list[str] = []
        pool = ThreadPoolExecutor(max_workers=min(len(sources), 4))
        try:
            futures = {
                pool.submit(self._search_one_source, keyword, src, work_dir, search_size_per_source): src
                for src in sources
            }
            for fut in futures:
                try:
                    found, error = fut.result()
                except Exception as exc:
                    found, error = [], f"{SOURCE_LABELS.get(futures[fut], futures[fut])}: {exc}"
                items.extend(found)
                if error:
                    errors.append(error)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        return items, errors

    def search(
        self,
        keyword: str,
        prefer: str = "any",
        *,
        music_sources: list[str] | None = None,
        search_size_per_source: int = DEFAULT_SEARCH_SIZE_PER_SOURCE,
        require_download_url: bool = True,
    ):
        items, errors = self._search_sources(
            keyword,
            music_sources=music_sources,
            work_dir=Path("/tmp/musicdl_search"),
            search_size_per_source=search_size_per_source,
        )
        if not items and errors:
            raise RuntimeError("音乐源搜索失败：" + "；".join(errors))
        if require_download_url:
            items = [it for it in items if getattr(it, "with_valid_download_url", False)]
        # optional prefer format filter kept light; caller may re-filter
        if prefer and prefer != "any":
            prefer_exts = PREFER_FORMATS.get(prefer, [])
            if prefer_exts:
                ranked = []
                for it in items:
                    ft = str(getattr(it, "file_type", "") or getattr(it, "ext", "") or "").lower()
                    score = 0
                    for i, ext in enumerate(prefer_exts):
                        if ext in ft:
                            score = 100 - i
                            break
                    ranked.append((score, it))
                ranked.sort(key=lambda x: x[0], reverse=True)
                items = [it for _, it in ranked]
        return items


    def download_one(
        self,
        task_id: int,
        keyword: str,
        song_name: str,
        singers: str,
        prefer: str,
        output_dir: Path,
        *,
        music_sources: list[str] | None = None,
        picked=None,
    ):
        if picked is None:
            items, errors = self._search_sources(
                keyword,
                music_sources=music_sources,
                work_dir=output_dir / ".musicdl_work",
                search_size_per_source=DEFAULT_SEARCH_SIZE_PER_SOURCE,
            )
            if not items and errors:
                raise RuntimeError("下载前搜索失败：" + "；".join(errors))
            picked = self._pick_item(items, prefer)

        if not picked:
            self.emit(task_id, f"未找到: {keyword}", 0)
            return None

        # 下载用 client 与该条目的来源保持一致
        src = getattr(picked, "_sonpick_source", None) or getattr(picked, "source", None)
        self._init_client(
            output_dir / ".musicdl_work",
            music_sources=[src] if src in DEFAULT_DOWNLOAD_SOURCES else music_sources,
        )

        ext = (getattr(picked, "ext", "") or "").upper()
        self.emit(task_id, f"命中 [{ext}] {picked.song_name} - {picked.singers}", 0)

        self.client.download([picked])
        moved = self._move_files(picked, song_name, singers, output_dir, task_id)
        return moved

    def _pick_item(self, items, prefer: str):
        prefer = prefer.lower().strip()
        wanted = PREFER_FORMATS.get(prefer, [])
        valid = [it for it in items if getattr(it, "with_valid_download_url", False)]
        if not valid:
            return None
        for ext in wanted:
            for item in valid:
                item_ext = (getattr(item, "ext", "") or "").lower().lstrip(".")
                if item_ext == ext:
                    return item
        return valid[0]

    def _normalize(self, text: str) -> str:
        return re.sub(r"[\\/:*?\"<>|]", "_", text).strip()

    def _format_base_dir(self, ext: str, output_dir: Path) -> Path:
        """按音频格式决定落盘根目录：无损→无损存放目录，其余→MP3 存放目录。"""
        settings = self.db.get(AppSettings, 1)
        storage = str(output_dir)
        if (ext or "").lower().lstrip(".") in LOSSLESS_FORMATS:
            return Path(resolve_lossless_output_dir(
                getattr(settings, "lossless_output_path", None) if settings else None,
                settings.storage_path if settings else storage,
            ))
        return Path(resolve_mp3_output_dir(
            getattr(settings, "mp3_output_path", None) if settings else None,
            settings.storage_path if settings else storage,
        ))

    def _move_files(self, picked, song_name: str, singers: str, output_dir: Path, task_id: int):
        keyword = f"{song_name} {singers}".strip()
        source_name = getattr(picked, "_sonpick_source", None) or getattr(picked, "source", None) or "QQMusicClient"
        base = output_dir / ".musicdl_work" / source_name
        if not base.exists():
            self.emit(task_id, f"下载工作目录不存在: {base}", 0)
            return None

        candidates = [d for d in base.iterdir() if d.is_dir()]
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        work_dir = candidates[0] if candidates else None
        if not work_dir:
            self.emit(task_id, f"下载工作目录为空: {base}", 0)
            return None

        album = getattr(picked, "album", None)
        # Store downloads under Artist/Album/ when metadata is available.
        rel_dir = library_relative_dir(singers, album)
        stem = track_stem(song_name or keyword, self._normalize(song_name or keyword) or "track")

        saved_audio: Optional[Path] = None
        saved_lrc: Optional[Path] = None

        # 先移动音频（按格式路由到 MP3/LOSSLESS 目录），歌词/封面跟随音频所在目录
        for f in work_dir.iterdir():
            if not f.is_file():
                continue
            ext = f.suffix.lower()
            if ext not in {".mp3", ".flac", ".m4a", ".wav", ".ogg", ".ape", ".wma"}:
                continue
            target_dir = self._format_base_dir(ext, output_dir) / rel_dir
            target_dir.mkdir(parents=True, exist_ok=True)
            target = self._unique_path(target_dir, stem, ext)
            shutil.move(str(f), str(target))
            saved_audio = target
            self.emit(task_id, f"音乐 -> {target.parent.as_posix()}/{target.name}", 0)

        if not saved_audio:
            self.emit(task_id, f"下载目录中未找到音频文件: {work_dir}", 0)
            return None

        target_dir = saved_audio.parent
        for f in work_dir.iterdir():
            if not f.is_file() or f.suffix.lower() != ".lrc":
                continue
            target = self._unique_path(target_dir, stem, ".lrc")
            shutil.move(str(f), str(target))
            saved_lrc = target
            self.emit(task_id, f"歌词 -> {target.parent.as_posix()}/{target.name}", 0)

        # 下载封面（与音频同目录，便于扫描侧车）
        cover_path = self._download_cover(picked, target_dir, stem)
        # 规范专辑封面文件名 cover.jpg（保留同 stem 图作为兼容）
        if cover_path:
            try:
                src = Path(cover_path)
                if src.is_file():
                    preferred = preferred_album_cover_path(target_dir, src.suffix)
                    if src.resolve() != preferred.resolve():
                        if not preferred.exists():
                            shutil.copy2(str(src), str(preferred))
                        cover_path = preferred
            except Exception:
                pass


        # musicdl 时长优先，其次读本地文件元数据
        duration = None
        for key in ("duration_s", "duration"):
            val = getattr(picked, key, None)
            if val is None:
                continue
            try:
                # duration may be "03:21" or seconds
                if isinstance(val, (int, float)):
                    duration = int(round(float(val)))
                else:
                    s = str(val).strip()
                    if s.isdigit():
                        duration = int(s)
                    elif ":" in s:
                        parts = [int(x) for x in s.split(":")]
                        sec = 0
                        for x in parts:
                            sec = sec * 60 + x
                        duration = sec
            except Exception:
                duration = None
            if duration and duration > 0:
                break

        song = Song(
            title=song_name,
            artist=singers,
            album=getattr(picked, "album", None),
            source=source_name,
            format=saved_audio.suffix.lstrip(".").lower(),
            duration=duration if duration and duration > 0 else None,
            file_size=saved_audio.stat().st_size,
            local_path=str(saved_audio),
            cover_path=str(cover_path) if cover_path else None,
            lrc_path=str(saved_lrc) if saved_lrc else None,
            status="local",
        )
        self.db.add(song)
        self.db.flush()
        self.db.add(SongFile(
            song_id=song.id,
            format=song.format or saved_audio.suffix.lstrip(".").lower(),
            local_path=str(saved_audio),
            duration=song.duration,
            file_size=song.file_size,
        ))

        # 本地文件补时长/内嵌封面/标签
        try:
            meta = enrich_local_audio(
                saved_audio,
                song_id=song.id,
                existing_cover=str(cover_path) if cover_path else None,
            )
            if meta.get("duration") and (not song.duration or song.duration <= 0):
                song.duration = int(meta["duration"])
            if meta.get("cover_path"):
                song.cover_path = meta["cover_path"]
            if meta.get("artist") and not (song.artist and song.artist.strip()):
                song.artist = meta["artist"]
            if meta.get("album") and not (song.album and song.album.strip()):
                song.album = meta["album"]
            if meta.get("title") and meta["title"] != song.title:
                # keep download query title unless empty
                if not song.title:
                    song.title = meta["title"]
            if (not song.lrc_path) and meta.get("lyrics"):
                lrc_saved = self._save_lyrics(song, str(meta["lyrics"]))
                if lrc_saved:
                    song.lrc_path = lrc_saved
        except Exception:
            pass

        self.db.commit()
        self.db.refresh(song)
        return song

    def _unique_path(self, directory: Path, stem: str, ext: str) -> Path:
        target = directory / f"{stem}{ext}"
        idx = 1
        while target.exists():
            target = directory / f"{stem} ({idx}){ext}"
            idx += 1
        return target

    def _download_cover(self, picked, output_dir: Path, stem: str) -> Optional[Path]:
        cover_url, _cover_source = extract_cover_url(picked)
        if not cover_url or not str(cover_url).startswith("http"):
            return None
        try:
            import requests
            r = requests.get(cover_url, timeout=15, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            r.raise_for_status()
            target = self._unique_path(output_dir, stem, ".jpg")
            target.write_bytes(r.content)
            return target
        except Exception:
            return None

    @staticmethod
    def parse_line(line: str) -> tuple[str, str]:
        line = line.strip()
        if not line:
            return "", ""
        line = re.sub(r"^\d+\s*[.、\.\-]?\s*", "", line)
        if " - " in line:
            song, singer = line.split(" - ", 1)
        elif "-" in line:
            song, singer = line.split("-", 1)
        else:
            song, singer = line, ""
        return song.strip(), singer.strip()

    def enrich_song_metadata(self, song: Song) -> dict:
        """Search QQ Music for the song and return missing metadata.

        Returns a dict with keys that were filled:
            {album, duration, cover_path, lrc_path}
        Only keys where the song was missing data and musicdl found a match are included.
        Empty dict means nothing was enriched.
        """
        # Determine what's missing
        needs_album = not (song.album and song.album.strip())
        needs_duration = not song.duration or song.duration <= 0
        has_local_cover = bool(song.cover_path and is_local_file(song.cover_path))
        needs_cover = not has_local_cover
        has_local_lrc = bool(song.lrc_path and Path(song.lrc_path).is_file())
        needs_lyrics = not has_local_lrc

        # If nothing is missing, skip
        if not (needs_album or needs_duration or needs_cover or needs_lyrics):
            return {}

        # Build search keyword
        keyword = f"{song.title} {song.artist}".strip() if song.artist else song.title
        if not keyword:
            return {}

        # Init client on demand
        if not self.client:
            self._init_client(Path("/tmp/musicdl_enrich"))

        # Search
        try:
            results = self.client.search(keyword=keyword)
        except Exception:
            return {}

        items = self._flatten_search_results(results)
        if not items:
            return {}

        # Match best result
        best = self._match_best(items, song.title, song.artist, duration=song.duration)
        if not best:
            return {}

        enriched = {}

        # Fill album
        if needs_album:
            album = getattr(best, "album", None)
            if album and str(album).strip():
                song.album = str(album).strip()
                enriched["album"] = song.album

        # Fill duration
        if needs_duration:
            dur = getattr(best, "duration_s", None)
            if dur is None:
                dur_str = getattr(best, "duration", None)
                if dur_str and str(dur_str).count(":") >= 1:
                    parts = [int(x) for x in str(dur_str).split(":")]
                    dur = 0
                    for x in parts:
                        dur = dur * 60 + x
            if dur and int(dur) > 0:
                song.duration = int(dur)
                enriched["duration"] = song.duration

        # Fill cover: download from cover_url
        if needs_cover:
            cover_url = getattr(best, "cover_url", None)
            if cover_url and str(cover_url).startswith("http"):
                cover_path = self._download_cover(best, self._cover_output_dir(song), self._cover_stem(song))
                if cover_path:
                    song.cover_path = str(cover_path)
                    enriched["cover_path"] = song.cover_path

        # Fill lyrics
        if needs_lyrics:
            lyric = getattr(best, "lyric", None)
            if lyric and str(lyric).strip() and str(lyric) not in {"NULL", "null", "None", "none"}:
                lrc_path = self._save_lyrics(song, str(lyric))
                if lrc_path:
                    song.lrc_path = lrc_path
                    enriched["lrc_path"] = song.lrc_path

        # Persist if anything changed
        if enriched:
            try:
                self.db.add(song)
                self.db.commit()
                self.db.refresh(song)
            except Exception:
                try:
                    self.db.rollback()
                except Exception:
                    pass

        return enriched


    def _summarize_search_item(self, item, *, max_title: int = 40) -> dict:
        """Compact dict for scrape debug logs."""
        def _clip(v):
            if v is None:
                return None
            s = str(v).strip()
            if len(s) > max_title:
                return s[: max_title - 1] + "…"
            return s or None

        title = getattr(item, "song_name", None) or getattr(item, "title", None)
        artist = getattr(item, "singers", None) or getattr(item, "artist", None)
        album = getattr(item, "album", None) or getattr(item, "album_name", None)
        dur = None
        for key in ("duration", "interval", "song_play_time"):
            val = getattr(item, key, None)
            if val is None:
                continue
            try:
                if isinstance(val, (int, float)):
                    n = int(val)
                    if n > 10000:
                        n = int(round(n / 1000))
                    dur = n if n > 0 else None
                    break
                s = str(val).strip()
                if ":" in s:
                    parts = s.split(":")
                    if len(parts) == 2:
                        dur = int(parts[0]) * 60 + int(float(parts[1]))
                        break
                n = int(float(s))
                if n > 10000:
                    n = int(round(n / 1000))
                dur = n if n > 0 else None
                break
            except Exception:
                continue
        return {
            "title": _clip(title),
            "artist": _clip(artist),
            "album": _clip(album),
            "duration": dur,
            "source": getattr(item, "_sonpick_source", None),
        }

    def _log_search_results(self, *, source: str, keyword: str, items, limit: int = 8) -> None:
        rows = [self._summarize_search_item(it) for it in list(items or [])[:limit]]
        if not rows:
            log.info("搜索结果 source=%s keyword=%r count=0", source, keyword)
            return
        lines = []
        for i, r in enumerate(rows, 1):
            lines.append(
                f"  [{i}] title={r.get('title')!r} artist={r.get('artist')!r} "
                f"album={r.get('album')!r} duration={r.get('duration')}"
            )
        log.info(
            "搜索结果 source=%s keyword=%r count=%s\n%s",
            source,
            keyword,
            len(items or []),
            "\n".join(lines),
        )

    def _match_best(
        self,
        items,
        title: str,
        artist: str | None,
        duration: int | None = None,
        duration_tol: int = 3,
    ):
        """Fuzzy-match by title + artist + optional duration (±tol seconds)."""

        def _norm(s):
            if not s:
                return ""
            return re.sub(r"[\s\-_/、,，]+", "", str(s).lower().strip())

        def _item_duration(item) -> int | None:
            for key in ("duration", "interval", "song_play_time"):
                val = getattr(item, key, None)
                if val is None:
                    continue
                try:
                    if isinstance(val, (int, float)):
                        n = int(val)
                        if n > 10000:
                            n = int(round(n / 1000))
                        return n if n > 0 else None
                    s = str(val).strip()
                    if not s:
                        continue
                    if ":" in s:
                        parts = s.split(":")
                        if len(parts) == 2:
                            return int(parts[0]) * 60 + int(float(parts[1]))
                        if len(parts) == 3:
                            return (
                                int(parts[0]) * 3600
                                + int(parts[1]) * 60
                                + int(float(parts[2]))
                            )
                    return int(float(s))
                except Exception:
                    continue
            return None

        clean_t, clean_a = split_title_artist(title, artist)
        if not clean_t:
            clean_t = clean_title(title) or (title or "")
        target_title = _norm(clean_t)
        target_artist = _norm(clean_a) if clean_a else ""
        target_dur = int(duration) if duration and int(duration) > 0 else None

        best_score = -1
        best_item: Any = None
        for item in items:
            raw_title = getattr(item, "song_name", "") or getattr(item, "title", "")
            raw_artist = getattr(item, "singers", "") or getattr(item, "artist", "")
            item_title = _norm(clean_title(raw_title) or raw_title)
            item_artist = _norm(clean_artist(raw_artist) or raw_artist)
            if not target_title:
                continue
            fused_target = _norm(f"{clean_t}{clean_a}") if clean_a else target_title
            fused_item = _norm(f"{raw_title}{raw_artist}")
            title_hit = (
                target_title == item_title
                or target_title in item_title
                or item_title in target_title
                or (fused_target and (fused_target == item_title or fused_target == fused_item or item_title in fused_target))
            )
            if not title_hit:
                continue

            score = 0
            if item_title == target_title:
                score += 12
            elif target_title in item_title or item_title in target_title:
                score += 7
            elif fused_target and (fused_target == fused_item or fused_target == item_title):
                score += 10
            else:
                score += 5

            if target_artist and item_artist:
                cand_detail = score_candidate(
                    query_title=clean_t,
                    query_artist=clean_a,
                    query_duration=target_dur,
                    cand_title=raw_title,
                    cand_artist=raw_artist,
                    cand_album=getattr(item, "album", None) or getattr(item, "album_name", None),
                    cand_duration=_item_duration(item),
                )
                artist_hit = cand_detail.get("artist", 0)
                if artist_hit >= 2:
                    score += 12
                elif artist_hit == 1:
                    score += 6
                else:
                    score -= 5
                score += int(cand_detail.get("duration_bonus", 0) * 2)
            elif not target_artist:
                # no artist known: still accept strong title (+duration) matches
                score += 1

            item_dur = _item_duration(item)
            if target_dur and item_dur:
                diff = abs(item_dur - target_dur)
                if diff <= 2:
                    score += 10
                elif diff <= 5:
                    score += 6
                elif diff <= 10:
                    score += 2
                elif diff > 30:
                    score -= 8
                elif diff > 15:
                    score -= 4


            album = getattr(item, "album", None) or getattr(item, "album_name", None)
            if album and str(album).strip():
                score += 2

            if score > best_score:
                best_score = score
                best_item = item

        # lower threshold: title-only Chinese songs often lack reliable artist tags
        min_score = 8 if target_artist else 7
        if best_item is not None and best_score >= min_score:
            summary = self._summarize_search_item(best_item)
            log.info(
                "匹配命中 score=%s min=%s target_title=%r target_artist=%r -> %s",
                best_score,
                min_score,
                clean_t,
                clean_a or None,
                summary,
            )
            return best_item
        # dump top candidates that almost matched for debugging
        almost = []
        for item in items[:8]:
            raw_title = getattr(item, "song_name", "") or getattr(item, "title", "")
            raw_artist = getattr(item, "singers", "") or getattr(item, "artist", "")
            almost.append(
                {
                    "title": str(raw_title)[:40] if raw_title else None,
                    "artist": str(raw_artist)[:40] if raw_artist else None,
                    "album": str(getattr(item, "album", None) or "")[:40] or None,
                }
            )
        log.info(
            "匹配未命中 best_score=%s min=%s target_title=%r target_artist=%r candidates=%s",
            best_score,
            min_score,
            clean_t,
            clean_a or None,
            almost,
        )
        return None

    def lookup_album_meta(
        self,
        title: str,
        artist: str | None = None,
        duration: int | None = None,
        *,
        music_sources: list[str] | None = None,
        search_size_per_source: int = 8,
        timeout_per_source: float = 25.0,
    ) -> dict:
        """Network lookup across sources (default scrape chain). Best effort.

        Does not require a valid download URL — scrape-only.
        """
        title, artist = split_title_artist(title, artist)
        keyword = build_search_keyword(title, artist)
        if not keyword:
            keyword = (title or "").strip()
        if not keyword:
            return {}
        log.info("lookup 查询清洗 title=%r artist=%r keyword=%r", title, artist, keyword)
        sources = list(music_sources or DEFAULT_SCRAPE_SOURCES)
        best_out: dict = {}
        best_score = -1
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

        for src in sources:
            def _search_one(source=src):
                self._init_client(
                    Path("/tmp/musicdl_scrape"),
                    music_sources=[source],
                    search_size_per_source=search_size_per_source,
                )
                results = self.client.search(keyword=keyword)
                return self._flatten_search_results(results)

            try:
                log.info("开始搜索 source=%s keyword=%r timeout=%ss", src, keyword, timeout_per_source)
                with ThreadPoolExecutor(max_workers=1) as pool:
                    fut = pool.submit(_search_one)
                    items = fut.result(timeout=max(1.0, float(timeout_per_source)))
            except FuturesTimeout:
                log.warning("搜索超时 source=%s keyword=%r timeout=%ss", src, keyword, timeout_per_source)
                continue
            except Exception as e:
                log.warning("搜索失败 source=%s keyword=%r err=%s: %s", src, keyword, type(e).__name__, e)
                continue
            self._log_search_results(source=src, keyword=keyword, items=items, limit=8)
            if not items:
                continue
            best = self._match_best(items, title=title, artist=artist, duration=duration)
            if not best:
                # still take first with album if score gate fails but album exists
                for it in items:
                    album = getattr(it, "album", None)
                    if album and str(album).strip():
                        best = it
                        break
            if not best:
                continue
            out = {
                "title": getattr(best, "song_name", None) or title,
                "artist": getattr(best, "singers", None) or artist,
                "album": getattr(best, "album", None),
                "source": getattr(best, "_sonpick_source", None) or src,
            }
            dur = getattr(best, "duration", None)
            try:
                if dur is not None:
                    n = int(dur)
                    if n > 10000:
                        n = int(round(n / 1000))
                    if n > 0:
                        out["duration"] = n
            except Exception:
                pass
            cover, cover_source = extract_cover_url(best)
            if cover:
                out["cover_url"] = str(cover)
                out["cover_source"] = cover_source
            # score roughly
            score = 0
            if out.get("album"):
                score += 5
            if out.get("artist") and artist and str(artist).lower() in str(out.get("artist")).lower():
                score += 3
            if out.get("duration") and duration:
                if abs(int(out["duration"]) - int(duration)) <= 3:
                    score += 4
            score += max(0, 3 - sources.index(src))  # prefer earlier sources slightly
            if score > best_score and out.get("album"):
                best_score = score
                best_out = out
                log.info("候选采用 source=%s score=%s out=%s", src, score, out)
                # good enough early stop
                if score >= 10 or (out.get("album") and out.get("duration") and duration and abs(int(out["duration"]) - int(duration)) <= 3):
                    break
            elif not best_out and out:
                best_out = out
                log.info("候选暂存(无专辑也可) source=%s score=%s out=%s", src, score, out)
        if best_out:
            log.info("lookup_album_meta 最终结果 keyword=%r best=%s", keyword, best_out)
        else:
            log.info("lookup_album_meta 无结果 keyword=%r sources=%s", keyword, sources)
        return best_out
