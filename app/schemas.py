import base64
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from cryptography.fernet import Fernet
from pydantic import BaseModel, Field

from app.config import get_settings


def _fernet() -> Fernet:
    digest = hashlib.sha256(get_settings().secret_key.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_text(plain: Optional[str]) -> Optional[str]:
    if not plain:
        return None
    return _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_text(cipher: Optional[str]) -> Optional[str]:
    if not cipher:
        return None
    return _fernet().decrypt(cipher.encode("utf-8")).decode("utf-8")


class LoginRequest(BaseModel):
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SettingsUpdate(BaseModel):
    storage_path: Optional[str] = None
    webdav_url: Optional[str] = None
    webdav_username: Optional[str] = None
    webdav_password: Optional[str] = None
    prefer_format: Optional[str] = Field(default=None, pattern="^(flac|mp3|m4a|any)$")
    mp3_output_path: Optional[str] = None
    lossless_output_path: Optional[str] = None
    lossless_preferred: Optional[bool] = None
    auto_convert_when_lossless_not_preferred: Optional[bool] = None
    auto_upload_webdav: Optional[bool] = None
    webdav_delete_local_after_upload: Optional[bool] = None
    webdav_upload_sidecar: Optional[bool] = None
    webdav_conflict_policy: Optional[str] = Field(default=None, pattern="^(overwrite|skip|rename)$")
    webdav_remote_dir: Optional[str] = None
    scan_local_enabled: Optional[bool] = None
    scan_local_dirs: Optional[list[str]] = None
    scan_webdav_enabled: Optional[bool] = None
    scan_webdav_dirs: Optional[list[str]] = None
    scan_exclude_globs: Optional[list[str]] = None
    scan_audio_exts: Optional[str] = None
    scrape_sources: Optional[list[dict[str, Any]]] = None
    acoustid_api_key: Optional[str] = Field(default=None, max_length=512)


class SettingsResponse(BaseModel):
    storage_path: str
    webdav_url: Optional[str]
    webdav_username: Optional[str]
    webdav_password: Optional[str]
    prefer_format: str
    mp3_output_path: str
    lossless_output_path: str = ""
    lossless_preferred: bool = False
    auto_convert_when_lossless_not_preferred: bool = False
    auto_upload_webdav: bool
    webdav_delete_local_after_upload: bool
    webdav_upload_sidecar: bool
    webdav_conflict_policy: str
    webdav_remote_dir: str
    scan_local_enabled: bool = True
    scan_local_dirs: list[str] = Field(default_factory=list)
    scan_webdav_enabled: bool = True
    scan_webdav_dirs: list[str] = Field(default_factory=lambda: [""])
    scan_exclude_globs: list[str] = Field(default_factory=list)
    scan_audio_exts: str = "mp3,flac,m4a,wav,ogg,aac,ape,wma"
    scrape_sources: list[dict[str, Any]] = Field(default_factory=list)
    acoustid_ready: bool = False
    acoustid_message: Optional[str] = None
    updated_at: Optional[str]


class LibraryScanRequest(BaseModel):
    source: str = Field(default="all", pattern="^(local|webdav|all)$")
    source_ids: Optional[list[int]] = None
    all: bool = False


class LibraryScanStats(BaseModel):
    source: str
    source_id: Optional[int] = None
    scanned: int = 0
    added: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
    message: Optional[str] = None


class LibraryScanResponse(BaseModel):
    ok: bool = True
    source: str
    local: Optional[LibraryScanStats] = None
    webdav: Optional[LibraryScanStats] = None
    sources: Optional[list[LibraryScanStats]] = None
    total_added: int = 0
    total_updated: int = 0
    total_skipped: int = 0
    total_errors: int = 0
    duration_ms: int = 0
    message: Optional[str] = None


class DownloadRequest(BaseModel):
    keyword: str
    prefer: str = "any"
    source: str = "all"
    # 曲库重复决策：None 保持旧行为（直接作为新歌曲下载）
    duplicate_action: Optional[str] = Field(default=None, pattern="^(keep_both|replace)$")
    replace_song_file_id: Optional[int] = None
    matched_song_id: Optional[int] = None


class BatchDownloadRequest(BaseModel):
    content: str
    prefer: str = "any"
    source: str = "all"


class LibraryMatchVersionOut(BaseModel):
    song_file_id: int
    location: str = "local"  # local | webdav
    format: Optional[str] = None
    size_bytes: Optional[int] = None
    duration_seconds: Optional[int] = None
    replaceable: bool = False


class LibraryMatchOut(BaseModel):
    status: str  # exists | possible_duplicate
    confidence: str = "medium"  # high | medium | low
    song_id: int
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    versions: list[LibraryMatchVersionOut] = Field(default_factory=list)


class SearchResultItem(BaseModel):
    song_name: str
    singers: Optional[str] = None
    album: Optional[str] = None
    duration: Optional[str] = None
    filesize: Optional[str] = None
    file_size: Optional[str] = None
    ext: Optional[str] = None
    source: Optional[str] = None
    song_id: Optional[str] = None
    download_url: Optional[str] = None
    raw: Optional[dict] = None
    library_match: Optional[LibraryMatchOut] = None


class SearchPageOut(BaseModel):
    items: list[SearchResultItem]
    total: int
    page: int
    page_size: int


class SongOut(BaseModel):
    id: int
    title: str
    artist: Optional[str]
    album: Optional[str]
    source: Optional[str]
    format: Optional[str]
    duration: Optional[int]
    file_size: Optional[int]
    cover_path: Optional[str]
    lrc_path: Optional[str]
    library_source_id: Optional[int] = None
    status: str
    play_count: int = 0
    is_favorite: bool = False
    versions: list[dict[str, Any]] = Field(default_factory=list)
    available_formats: list[str] = Field(default_factory=list)
    has_playable_file: bool = False
    created_at: Optional[str]
    updated_at: Optional[str]


class ArtistOut(BaseModel):
    name: str
    song_count: int
    album_count: int
    cover_song_id: Optional[int] = None


class AlbumOut(BaseModel):
    name: str
    artist: Optional[str]
    song_count: int
    cover_song_id: Optional[int] = None


class LyricsLineOut(BaseModel):
    time: float
    text: str


class LyricsOut(BaseModel):
    song_id: int
    lines: list[LyricsLineOut] = Field(default_factory=list)
    raw: Optional[str] = None


class PlaylistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None


class PlaylistUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None


class PlaylistOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    cover_song_id: Optional[int]
    song_count: int = 0
    created_at: Optional[str]
    updated_at: Optional[str]


class PlaylistAddSongs(BaseModel):
    song_ids: list[int] = Field(default_factory=list)


class PlayHistoryOut(BaseModel):
    id: int
    song_id: int
    played_at: Optional[str]
    song: Optional[SongOut] = None


class LibraryStatsOut(BaseModel):
    song_count: int = 0
    artist_count: int = 0
    album_count: int = 0
    favorite_count: int = 0
    playlist_count: int = 0
    total_duration: int = 0
    total_size: int = 0
    meta_completeness: dict = Field(default_factory=dict)
    sources: list[dict] = Field(default_factory=list)
    tasks: dict = Field(default_factory=dict)


class SourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    type: str = Field(pattern="^(local|webdav)$")
    enabled: bool = True
    root_path: Optional[str] = None
    scan_dirs: Optional[list[str]] = None
    webdav_url: Optional[str] = None
    webdav_username: Optional[str] = None
    webdav_password: Optional[str] = None
    remote_dir: Optional[str] = None
    scan_remote_dirs: Optional[list[str]] = None
    exclude_globs: Optional[list[str]] = None
    audio_exts: Optional[str] = None
    is_default_upload: bool = False
    upload_sidecar: Optional[bool] = None
    conflict_policy: Optional[str] = Field(default=None, pattern="^(overwrite|skip|rename)$")
    delete_local_after_upload: Optional[bool] = None


class SourceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    enabled: Optional[bool] = None
    root_path: Optional[str] = None
    scan_dirs: Optional[list[str]] = None
    webdav_url: Optional[str] = None
    webdav_username: Optional[str] = None
    webdav_password: Optional[str] = None
    remote_dir: Optional[str] = None
    scan_remote_dirs: Optional[list[str]] = None
    exclude_globs: Optional[list[str]] = None
    audio_exts: Optional[str] = None
    is_default_upload: Optional[bool] = None
    upload_sidecar: Optional[bool] = None
    conflict_policy: Optional[str] = Field(default=None, pattern="^(overwrite|skip|rename)$")
    delete_local_after_upload: Optional[bool] = None


class SourceOut(BaseModel):
    id: int
    name: str
    type: str
    enabled: bool
    is_builtin: bool = False
    locked_fields: list[str] = Field(default_factory=list)
    deletable: bool = True
    root_path: Optional[str] = None
    scan_dirs: list[str] = Field(default_factory=list)
    webdav_url: Optional[str] = None
    webdav_username: Optional[str] = None
    remote_dir: Optional[str] = None
    scan_remote_dirs: list[str] = Field(default_factory=lambda: [""])
    exclude_globs: list[str] = Field(default_factory=list)
    audio_exts: Optional[str] = None
    is_default_upload: bool = False
    upload_sidecar: bool = True
    conflict_policy: str = "rename"
    delete_local_after_upload: bool = False
    connection_status: str = "unknown"
    connection_message: Optional[str] = None
    last_checked_at: Optional[str] = None
    last_scan_at: Optional[str] = None
    last_scan_added: int = 0
    last_scan_updated: int = 0
    song_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class OperationLogOut(BaseModel):
    id: int
    action: str
    target: str
    status: str
    title: Optional[str]
    message: Optional[str]
    local_path: Optional[str]
    remote_path: Optional[str]
    song_id: Optional[int]
    task_id: Optional[int]
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str]


class TaskOut(BaseModel):
    id: int
    type: str
    status: str
    payload: dict[str, Any] = Field(default_factory=dict)
    progress: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
