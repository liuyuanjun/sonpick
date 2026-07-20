from __future__ import annotations

import re
import shutil
import subprocess
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from mutagen.id3 import APIC, ID3
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AppSettings, MediaSource, Song, SongFile

BITRATE = "320k"
LOSSLESS_FORMATS = {"flac", "wav", "aiff", "alac", "ape"}


def resolve_output_dir(raw: str | None, storage_path: str | None, default_name: str) -> str:
    """Resolve a format output directory.

    - 留空：``<存储目录>/<default_name>``
    - 相对路径（``MP3``、``/MP3`` 等单段写法）：基于本地存储路径解析
    - 多段绝对路径（``/mnt/nas/mp3``）：按原样使用
    """
    storage = (storage_path or "").strip() or get_settings().storage_path
    value = (raw or "").strip()
    if not value:
        return str(Path(storage) / default_name)
    if value.startswith("/") and "/" in value[1:]:
        return value
    return str(Path(storage) / value.lstrip("/"))


def resolve_mp3_output_dir(raw: str | None, storage_path: str | None) -> str:
    """Resolve the MP3 output directory（默认 <存储目录>/MP3）。"""
    return resolve_output_dir(raw, storage_path, "MP3")


def resolve_lossless_output_dir(raw: str | None, storage_path: str | None) -> str:
    """Resolve the lossless output directory（默认 <存储目录>/LOSSLESS）。"""
    return resolve_output_dir(raw, storage_path, "LOSSLESS")


class ConvertService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def is_lossless(song_file: SongFile) -> bool:
        return (song_file.format or "").lower() in LOSSLESS_FORMATS

    def select_playable_files(self, song: Song, lossless_preferred: bool = False) -> list[SongFile]:
        files = self.db.query(SongFile).filter(SongFile.song_id == song.id).all()
        priorities = {source.id: source.playback_priority for source in self.db.query(MediaSource).all()}
        playable = [item for item in files if item.local_path or item.webdav_path]
        if not playable:
            return []
        ordered_formats = (LOSSLESS_FORMATS, {"mp3"}) if lossless_preferred else ({"mp3"}, LOSSLESS_FORMATS)
        ordered: list[SongFile] = []
        for formats in ordered_formats:
            ordered.extend(sorted(
                (item for item in playable if (item.format or "").lower() in formats and item not in ordered),
                key=lambda item: (item.availability_status == "unavailable", -(item.source_priority + priorities.get(item.library_source_id, 0)), item.id),
            ))
        ordered.extend(sorted(
            (item for item in playable if item not in ordered),
            key=lambda item: (item.availability_status == "unavailable", -item.source_priority, item.id),
        ))
        return ordered

    def select_playable_file(self, song: Song, lossless_preferred: bool = False) -> SongFile | None:
        candidates = self.select_playable_files(song, lossless_preferred)
        return candidates[0] if candidates else None

    def convert_song_to_mp3(self, song: Song) -> SongFile:
        source = self._pick_lossless_source(song)
        existing = next(
            (item for item in self.db.query(SongFile).filter(SongFile.song_id == song.id).all()
             if (item.format or "").lower() == "mp3"),
            None,
        )
        if existing and existing.local_path and Path(existing.local_path).exists():
            return existing

        output_path = self._output_path(song)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._run_ffmpeg(Path(source.local_path), output_path, song)
        self._copy_lyrics(song, output_path)
        self._verify_mp3(output_path, song, require_cover=bool(song.cover_path and Path(song.cover_path).exists()))

        if not existing:
            existing = SongFile(song_id=song.id, format="mp3")
            self.db.add(existing)
        existing.local_path = str(output_path)
        existing.file_size = output_path.stat().st_size
        existing.duration = song.duration or source.duration
        existing.library_source_id = source.library_source_id
        self.db.commit()
        return existing

    def _pick_lossless_source(self, song: Song) -> SongFile:
        """选出本地文件确实存在的无损源；路径失效时先自愈再标记不可用。"""
        candidates = [
            item for item in self.select_playable_files(song, lossless_preferred=True)
            if item.local_path
        ]
        if not candidates:
            raise RuntimeError("没有可转码的本地无损文件")
        lossless = [item for item in candidates if self.is_lossless(item)]
        if not lossless:
            raise RuntimeError("仅无损音频需要转码为 MP3")
        for item in lossless:
            if Path(item.local_path).exists():
                return item
            relocated = self._relocate_missing_file(song, item)
            if relocated is not None:
                return relocated
            item.availability_status = "unavailable"
            item.last_error = "本地文件不存在（可能已被移动或整理）"
            item.last_checked_at = datetime.now(timezone.utc)
            self.db.commit()
        raise RuntimeError(
            f"无损源文件不存在: {lossless[0].local_path}（文件可能已被移动或整理，请重新扫描曲库）"
        )

    def _relocate_missing_file(self, song: Song, item: SongFile) -> SongFile | None:
        """SongFile.local_path 失效时尝试重新定位文件，返回可用的版本行。

        覆盖两类常见失真：曲库整理只更新了 Song.local_path；macOS 创建的
        NFD 文件名与 DB 中 NFC 形式不一致。
        """
        old = item.local_path or ""
        name = Path(old).name
        suffix = Path(old).suffix.lower()
        candidates: list[str] = [old]
        if song.local_path and song.local_path != old:
            candidates.append(song.local_path)
        for cand in candidates:
            for variant in {cand, unicodedata.normalize("NFC", cand), unicodedata.normalize("NFD", cand)}:
                p = Path(variant)
                if p.is_file() and p.suffix.lower() == suffix:
                    adopted = self._adopt_path(item, p)
                    if adopted is not None:
                        return adopted
        # 兜底：按文件名在存储目录下搜索
        settings = self.db.get(AppSettings, 1)
        storage = (settings.storage_path if settings else None) or get_settings().storage_path
        try:
            for p in Path(storage).rglob(name):
                if p.is_file() and p.suffix.lower() == suffix:
                    adopted = self._adopt_path(item, p)
                    if adopted is not None:
                        return adopted
        except Exception:
            pass
        return None

    def _adopt_path(self, item: SongFile, path: Path) -> SongFile | None:
        """把版本行指向重新找到的文件；处理 local_path 唯一约束冲突。"""
        owner = (
            self.db.query(SongFile)
            .filter(SongFile.local_path == str(path), SongFile.id != item.id)
            .first()
        )
        if owner is not None:
            if owner.song_id == item.song_id:
                # 同一首歌已有指向该文件的版本行，当前行是冗余记录
                self.db.delete(item)
                self.db.commit()
                return owner
            return None
        item.local_path = str(path)
        item.availability_status = "available"
        item.last_error = None
        self.db.commit()
        return item

    def auto_convert_missing_mp3(self) -> list[int]:
        settings = self.db.get(AppSettings, 1)
        if not settings or settings.lossless_preferred or not settings.auto_convert_when_lossless_not_preferred:
            return []
        converted: list[int] = []
        for song in self.db.query(Song).all():
            files = self.db.query(SongFile).filter(SongFile.song_id == song.id).all()
            if any((item.format or "").lower() == "mp3" for item in files):
                continue
            if any(self.is_lossless(item) and item.local_path for item in files):
                self.convert_song_to_mp3(song)
                converted.append(song.id)
        return converted

    def _output_path(self, song: Song) -> Path:
        settings = self.db.get(AppSettings, 1)
        root = Path(resolve_mp3_output_dir(
            getattr(settings, "mp3_output_path", None) if settings else None,
            settings.storage_path if settings else None,
        ))
        return root / self._normalize(song.artist or "未知艺术家") / self._normalize(song.album or "未知专辑") / f"{self._normalize(song.title or '未知歌曲')}.mp3"

    def _run_ffmpeg(self, input_path: Path, output_path: Path, song: Song) -> None:
        cover = Path(song.cover_path) if song.cover_path and Path(song.cover_path).is_file() else None
        cmd = ["ffmpeg", "-y", "-i", str(input_path)]
        if cover:
            cmd += ["-i", str(cover), "-map", "0:a:0", "-map", "1:v:0", "-c:v", "mjpeg", "-disposition:v:0", "attached_pic"]
        else:
            cmd += ["-map", "0:a:0"]
        cmd += ["-c:a", "libmp3lame", "-b:a", BITRATE, "-ar", "44100", "-ac", "2", "-metadata", f"title={song.title or ''}", "-metadata", f"artist={song.artist or ''}", "-metadata", f"album={song.album or ''}", "-id3v2_version", "3", str(output_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, errors="replace")
        if result.returncode:
            output_path.unlink(missing_ok=True)
            raise RuntimeError(f"FFmpeg 转码失败: {result.stderr[-500:]}")

    @staticmethod
    def _copy_lyrics(song: Song, output_path: Path) -> None:
        if song.lrc_path and Path(song.lrc_path).is_file():
            shutil.copy2(song.lrc_path, output_path.with_suffix(".lrc"))

    @staticmethod
    def _verify_mp3(path: Path, song: Song, require_cover: bool) -> None:
        try:
            tags = ID3(path)
            title = str(tags.get("TIT2", ""))
            artist = str(tags.get("TPE1", ""))
            album = str(tags.get("TALB", ""))
            has_cover = any(isinstance(frame, APIC) for frame in tags.values())
        except Exception as exc:
            path.unlink(missing_ok=True)
            raise RuntimeError(f"MP3 标签校验失败: {exc}") from exc
        if ((song.title and title != song.title) or (song.artist and artist != song.artist) or (song.album and album != song.album) or (require_cover and not has_cover)):
            path.unlink(missing_ok=True)
            raise RuntimeError("MP3 标签或内嵌封面校验失败")

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r'[\\/:*?"<>|]', "_", text).strip() or "未知"
