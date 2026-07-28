from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import MediaSource, Song, SongFile

LOSSLESS_FORMATS = {"flac", "wav", "aiff", "alac", "ape", "dsf", "dff"}


class NoPlayableSongFileError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SongFileResolver:
    """SongFile 唯一物理路径解析入口。

    Song 只保存逻辑歌曲及聚合元数据；所有播放、上传、转码和文件标签操作
    都必须先通过本服务选出一个真实、可用的 SongFile。
    """

    def __init__(self, db: Session):
        self.db = db

    def all_files(self, song: Song) -> list[SongFile]:
        return (
            self.db.query(SongFile)
            .filter(SongFile.song_id == song.id)
            .order_by(SongFile.id.asc())
            .all()
        )

    def writable_local_files(self, song: Song) -> list[SongFile]:
        return [
            item for item in self.all_files(song)
            if item.local_path and Path(item.local_path).is_file()
        ]

    def describe_files(self, song: Song) -> list[dict]:
        files = self.all_files(song)
        source_ids = {item.library_source_id for item in files if item.library_source_id is not None}
        source_names = {
            source.id: source.name
            for source in self.db.query(MediaSource).filter(MediaSource.id.in_(source_ids)).all()
        } if source_ids else {}
        result = []
        for item in files:
            local_exists = bool(item.local_path and Path(item.local_path).is_file())
            location = "local" if item.local_path else "webdav"
            path = item.local_path or item.webdav_path or ""
            result.append({
                "id": item.id,
                "format": item.format,
                "location": location,
                "path": path,
                "source_id": item.library_source_id,
                "source_name": source_names.get(item.library_source_id),
                "file_size": item.file_size,
                "availability_status": item.availability_status,
                "writable": local_exists,
                "write_status": "可写入本地文件" if local_exists else ("远端只读，未写入" if item.webdav_path else "本地文件不可用"),
            })
        return result

    def candidates(self, song: Song, lossless_preferred: bool = False) -> list[SongFile]:
        files = self.db.query(SongFile).filter(SongFile.song_id == song.id).all()
        priorities = {
            source.id: source.playback_priority
            for source in self.db.query(MediaSource).all()
        }
        usable = [
            item for item in files
            if (item.local_path or item.webdav_path) and item.availability_status != "unavailable"
        ]
        if not usable:
            return []

        preferred = LOSSLESS_FORMATS if lossless_preferred else {"mp3"}
        fallback = {"mp3"} if lossless_preferred else LOSSLESS_FORMATS

        def sort_key(item: SongFile) -> tuple[int, int, int]:
            priority = item.source_priority + priorities.get(item.library_source_id, 0)
            return (-priority, -(item.id or 0), 0 if item.local_path else 1)

        ordered: list[SongFile] = []
        for formats in (preferred, fallback):
            ordered.extend(sorted(
                (item for item in usable if (item.format or "").lower() in formats and item not in ordered),
                key=sort_key,
            ))
        ordered.extend(sorted((item for item in usable if item not in ordered), key=sort_key))
        return ordered

    def resolve(self, song: Song, lossless_preferred: bool = False) -> SongFile:
        candidates = self.candidates(song, lossless_preferred)
        if not candidates:
            raise NoPlayableSongFileError("该歌曲没有可用的文件版本")
        selected = candidates[0]
        self.refresh_song_assets(song, selected)
        return selected

    def resolve_local(self, song: Song, lossless_preferred: bool = False) -> SongFile:
        for item in self.candidates(song, lossless_preferred):
            if item.local_path and Path(item.local_path).is_file():
                self.refresh_song_assets(song, item)
                return item
        raise NoPlayableSongFileError("该歌曲没有可用的本地文件版本")

    def refresh_song_assets(self, song: Song, selected: SongFile) -> bool:
        """将选中文件版本的侧车资源回填为 Song 的聚合缓存。"""
        changed = False
        for field in ("cover_path", "lrc_path"):
            candidate = getattr(selected, field, None)
            if candidate and candidate != getattr(song, field, None):
                setattr(song, field, candidate)
                changed = True
        if changed:
            song.updated_at = _now()
            self.db.add(song)
        return changed

    def mark_unavailable(self, song_file: SongFile, reason: str) -> None:
        song_file.availability_status = "unavailable"
        song_file.last_error = reason[:512]
        song_file.last_checked_at = _now()
        song_file.updated_at = _now()
        self.db.add(song_file)


def refresh_song_aggregate_assets(db: Session, song: Song) -> bool:
    """从当前偏好最优的可用 SongFile 回填 Song 封面/歌词缓存。"""
    resolver = SongFileResolver(db)
    try:
        selected = resolver.resolve(song)
    except NoPlayableSongFileError:
        return False
    return resolver.refresh_song_assets(song, selected)
