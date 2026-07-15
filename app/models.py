import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, CheckConstraint

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AppSettings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True)
    storage_path = Column(String(512), nullable=False)
    webdav_url = Column(String(512), nullable=True)
    webdav_username = Column(String(255), nullable=True)
    webdav_password_enc = Column(String(512), nullable=True)
    prefer_format = Column(String(16), default="any")
    auto_convert_mp3 = Column(Boolean, default=False)
    auto_upload_webdav = Column(Boolean, default=False)
    webdav_delete_local_after_upload = Column(Boolean, default=False)
    webdav_upload_sidecar = Column(Boolean, default=True)
    webdav_conflict_policy = Column(String(16), default="rename")  # overwrite|skip|rename
    webdav_remote_dir = Column(String(512), default="")
    scan_local_enabled = Column(Boolean, default=True)
    scan_local_dirs = Column(Text, default="[]")
    scan_webdav_enabled = Column(Boolean, default=True)
    scan_webdav_dirs = Column(Text, default='[""]')
    scan_exclude_globs = Column(
        Text,
        default='["**/.*","**/.@*","**/@eaDir/**","**/#recycle/**","**/Thumbs.db","**/*.tmp"]',
    )
    scan_audio_exts = Column(String(255), default="mp3,flac,m4a,wav,ogg,aac,ape,wma")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        CheckConstraint("id = 1", name="only_one_settings_row"),
    )


class MediaSource(Base):
    __tablename__ = "media_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    type = Column(String(16), nullable=False)  # local | webdav
    enabled = Column(Boolean, default=True)

    # local
    root_path = Column(String(1024), nullable=True)
    scan_dirs = Column(Text, default="[]")

    # webdav
    webdav_url = Column(String(512), nullable=True)
    webdav_username = Column(String(255), nullable=True)
    webdav_password_enc = Column(String(512), nullable=True)
    remote_dir = Column(String(512), default="")
    scan_remote_dirs = Column(Text, default='[\"\"]')

    # scan
    exclude_globs = Column(
        Text,
        default='[\"**/.*\",\"**/.@*\",\"**/@eaDir/**\",\"**/#recycle/**\",\"**/Thumbs.db\",\"**/*.tmp\"]',
    )
    audio_exts = Column(String(255), default="mp3,flac,m4a,wav,ogg,aac,ape,wma")

    # upload (webdav only)
    is_default_upload = Column(Boolean, default=False)
    upload_sidecar = Column(Boolean, default=True)
    conflict_policy = Column(String(16), default="rename")  # rename | overwrite | skip
    delete_local_after_upload = Column(Boolean, default=False)

    # status
    connection_status = Column(String(16), default="unknown")  # unknown | ok | failed | not_configured
    connection_message = Column(Text, nullable=True)
    last_checked_at = Column(DateTime, nullable=True)
    last_scan_at = Column(DateTime, nullable=True)
    last_scan_added = Column(Integer, default=0)
    last_scan_updated = Column(Integer, default=0)
    song_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "enabled": bool(self.enabled),
            "root_path": self.root_path,
            "scan_dirs": _json_list(self.scan_dirs),
            "webdav_url": self.webdav_url,
            "webdav_username": self.webdav_username,
            "remote_dir": self.remote_dir or "",
            "scan_remote_dirs": _json_list(self.scan_remote_dirs),
            "exclude_globs": _json_list(self.exclude_globs),
            "audio_exts": self.audio_exts or "",
            "is_default_upload": bool(self.is_default_upload),
            "upload_sidecar": bool(self.upload_sidecar),
            "conflict_policy": self.conflict_policy or "rename",
            "delete_local_after_upload": bool(self.delete_local_after_upload),
            "connection_status": self.connection_status or "unknown",
            "connection_message": self.connection_message,
            "last_checked_at": self.last_checked_at.isoformat() if self.last_checked_at else None,
            "last_scan_at": self.last_scan_at.isoformat() if self.last_scan_at else None,
            "last_scan_added": self.last_scan_added or 0,
            "last_scan_updated": self.last_scan_updated or 0,
            "song_count": self.song_count or 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


def _json_list(raw):
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    try:
        import json

        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x) for x in data]
    except Exception:
        pass
    return []


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(32), nullable=False)
    status = Column(String(16), default="pending")  # pending running completed failed cancelled
    payload_json = Column(Text, nullable=False, default="{}")
    progress_json = Column(Text, nullable=False, default="{}")
    result_json = Column(Text, nullable=False, default="{}")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "type": self.type,
            "status": self.status,
            "payload": json.loads(self.payload_json or "{}"),
            "progress": json.loads(self.progress_json or "{}"),
            "result": json.loads(self.result_json or "{}"),
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Song(Base):
    __tablename__ = "songs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    artist = Column(String(255), nullable=True)
    album = Column(String(255), nullable=True)
    source = Column(String(64), nullable=True)
    source_id = Column(String(128), nullable=True)
    format = Column(String(16), nullable=True)
    duration = Column(Integer, nullable=True)
    file_size = Column(Integer, nullable=True)
    local_path = Column(String(1024), nullable=True)
    cover_path = Column(String(1024), nullable=True)
    lrc_path = Column(String(1024), nullable=True)
    webdav_path = Column(String(1024), nullable=True)
    library_source_id = Column(Integer, ForeignKey("media_sources.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(16), default="local")  # local / uploaded / both / remote
    play_count = Column(Integer, default=0)
    meta_confidence = Column(Integer, default=0)  # 0-100
    meta_provider = Column(String(64), nullable=True)
    scrape_status = Column(String(16), default="none")  # none/pending/done/failed
    meta_locked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "source": self.source,
            "source_id": self.source_id,
            "format": self.format,
            "duration": self.duration,
            "file_size": self.file_size,
            "local_path": self.local_path,
            "cover_path": self.cover_path,
            "lrc_path": self.lrc_path,
            "webdav_path": self.webdav_path,
            "library_source_id": self.library_source_id,
            "status": self.status,
            "play_count": self.play_count or 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("song_id", name="uq_favorite_song"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    song_id = Column(Integer, ForeignKey("songs.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "song_id": self.song_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Playlist(Base):
    __tablename__ = "playlists"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    cover_song_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self, song_count: int = 0):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "cover_song_id": self.cover_song_id,
            "song_count": song_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class PlaylistItem(Base):
    __tablename__ = "playlist_items"
    __table_args__ = (UniqueConstraint("playlist_id", "song_id", name="uq_playlist_song"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    playlist_id = Column(Integer, ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False)
    song_id = Column(Integer, ForeignKey("songs.id", ondelete="CASCADE"), nullable=False)
    position = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class PlayHistory(Base):
    __tablename__ = "play_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    song_id = Column(Integer, ForeignKey("songs.id", ondelete="CASCADE"), nullable=False)
    played_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "song_id": self.song_id,
            "played_at": self.played_at.isoformat() if self.played_at else None,
        }




class ScrapeCache(Base):
    """Cache network scrape hits to avoid repeated external calls."""

    __tablename__ = "scrape_cache"
    __table_args__ = (
        UniqueConstraint("cache_key", name="uq_scrape_cache_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    cache_key = Column(String(255), nullable=False)
    title = Column(String(255), nullable=True)
    artist = Column(String(255), nullable=True)
    album = Column(String(255), nullable=True)
    duration = Column(Integer, nullable=True)
    cover_url = Column(String(1024), nullable=True)
    provider = Column(String(64), nullable=True)
    score = Column(Integer, default=0)
    payload_json = Column(Text, default="{}")
    hit_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class OperationLog(Base):
    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(String(32), nullable=False)  # download/upload/delete/convert
    target = Column(String(32), nullable=False, default="file")  # local/webdav/song
    status = Column(String(16), nullable=False, default="success")  # success/failed/skipped/renamed/partial
    title = Column(String(255), nullable=True)
    message = Column(Text, nullable=True)
    local_path = Column(String(1024), nullable=True)
    remote_path = Column(String(1024), nullable=True)
    song_id = Column(Integer, nullable=True)
    task_id = Column(Integer, nullable=True)
    detail_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "action": self.action,
            "target": self.target,
            "status": self.status,
            "title": self.title,
            "message": self.message,
            "local_path": self.local_path,
            "remote_path": self.remote_path,
            "song_id": self.song_id,
            "task_id": self.task_id,
            "detail": json.loads(self.detail_json or "{}"),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
