"""失效曲库记录的体检与清理。

死 Song：没有任何"有效版本"（有效 = local_path/webdav_path 非空且未标
unavailable），与曲库列表默认过滤口径一致。清理前先确认每个版本归属的
存储位置可达（本地根目录存在可读 / WebDAV 连接成功），挂载点整体掉线时
拒绝删除，避免把"暂时离线"误判为"垃圾数据"。本地文件实际还在的记录会被
恢复为 available（顺带自愈），而不是删除。
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import AppSettings, MediaSource, Song, SongFile
from app.services.operation_log_service import write_log


def _now() -> datetime:
    return datetime.now(timezone.utc)


class LibraryCleanupService:
    def __init__(self, db: Session):
        self.db = db
        self._reachability: dict[Any, tuple[bool, str]] = {}

    # ---------- 可达性 ----------

    def _check_local_root(self, root: Optional[str]) -> tuple[bool, str]:
        root = (root or "").strip()
        if not root:
            return False, "未配置本地根目录"
        p = Path(root).expanduser()
        if not p.exists():
            return False, f"目录不存在: {root}"
        if not p.is_dir():
            return False, f"路径不是目录: {root}"
        if not os.access(p, os.R_OK | os.X_OK):
            return False, f"目录不可读: {root}"
        return True, "ok"

    def _check_webdav(self, source: MediaSource) -> tuple[bool, str]:
        if not (source.webdav_url or "").strip():
            return False, "未配置 WebDAV 地址"
        try:
            from app.services.webdav_service import WebDAVService

            WebDAVService(db=self.db, source_id=source.id).list()
            return True, "ok"
        except Exception as e:
            return False, f"WebDAV 连接失败: {type(e).__name__}: {e}"

    def _reachability_for(self, source_id: Optional[int]) -> tuple[bool, str]:
        """source_id=None 表示未归属任何源的本地文件，用全局 storage_path 判断。"""
        key = source_id if source_id is not None else "__default__"
        if key in self._reachability:
            return self._reachability[key]
        if source_id is None:
            settings = self.db.get(AppSettings, 1)
            result = self._check_local_root(settings.storage_path if settings else None)
        else:
            source = self.db.get(MediaSource, source_id)
            if source is None:
                result = (False, f"来源已不存在 (id={source_id})")
            elif source.type == "local":
                result = self._check_local_root(source.root_path)
            elif source.type == "webdav":
                result = self._check_webdav(source)
            else:
                result = (False, f"未知来源类型: {source.type}")
        self._reachability[key] = result
        return result

    # ---------- 分类 ----------

    def _dead_songs(self) -> list[Song]:
        playable_ids = self.db.query(SongFile.song_id).filter(
            (SongFile.local_path.isnot(None)) | (SongFile.webdav_path.isnot(None)),
            (SongFile.availability_status.is_(None)) | (SongFile.availability_status != "unavailable"),
        )
        return (
            self.db.query(Song)
            .filter(Song.id.notin_(playable_ids))
            .order_by(Song.id.asc())
            .all()
        )

    def _classify(self, song: Song, versions: list[SongFile]) -> tuple[str, Optional[str]]:
        """返回 (类别, 原因)。类别: healable / cleanable / blocked。"""
        for sf in versions:
            if sf.local_path:
                ok, msg = self._reachability_for(sf.library_source_id)
                if not ok:
                    return "blocked", f"本地存储不可达（{msg}）"
                if Path(sf.local_path).is_file():
                    return "healable", None
            elif sf.webdav_path:
                ok, msg = self._reachability_for(sf.library_source_id)
                if not ok:
                    return "blocked", msg
        return "cleanable", None

    def analyze(self) -> dict[str, Any]:
        songs = self._dead_songs()
        files_by_song: dict[int, list[SongFile]] = {}
        if songs:
            for sf in self.db.query(SongFile).filter(SongFile.song_id.in_([s.id for s in songs])).all():
                files_by_song.setdefault(sf.song_id, []).append(sf)

        healable: list[dict[str, Any]] = []
        cleanable: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        for song in songs:
            versions = files_by_song.get(song.id, [])
            category, reason = self._classify(song, versions)
            entry = {
                "song_id": song.id,
                "title": song.title,
                "artist": song.artist,
                "album": song.album,
                "version_count": len(versions),
                "reason": reason,
            }
            (healable if category == "healable" else cleanable if category == "cleanable" else blocked).append(entry)

        return {
            "dead_songs": len(songs),
            "healable": len(healable),
            "cleanable": len(cleanable),
            "blocked": len(blocked),
            "healable_samples": healable[:10],
            "cleanable_samples": cleanable[:20],
            "blocked_samples": blocked[:10],
        }

    # ---------- 执行 ----------

    def run(self, emit=None) -> dict[str, Any]:
        _emit = emit if callable(emit) else (lambda msg, pct=None: None)
        _emit("分析失效记录...", 5)
        songs = self._dead_songs()
        files_by_song: dict[int, list[SongFile]] = {}
        if songs:
            for sf in self.db.query(SongFile).filter(SongFile.song_id.in_([s.id for s in songs])).all():
                files_by_song.setdefault(sf.song_id, []).append(sf)

        healed = 0
        deleted = 0
        blocked = 0
        deleted_titles: list[str] = []
        total = max(len(songs), 1)
        for idx, song in enumerate(songs, 1):
            versions = files_by_song.get(song.id, [])
            category, reason = self._classify(song, versions)
            if category == "healable":
                for sf in versions:
                    if sf.local_path and Path(sf.local_path).is_file():
                        sf.availability_status = "available"
                        sf.last_error = None
                        sf.last_checked_at = _now()
                        sf.updated_at = _now()
                        self.db.add(sf)
                healed += 1
            elif category == "cleanable":
                deleted_titles.append(f"{song.artist or ''} - {song.title}".strip(" -"))
                self.db.delete(song)  # 级联删除 SongFile / 收藏 / 播放历史
                deleted += 1
            else:
                blocked += 1
            if idx % 20 == 0:
                try:
                    self.db.commit()
                except Exception:
                    self.db.rollback()
                    raise
                _emit(f"已处理 {idx}/{len(songs)} 首（恢复 {healed} / 清理 {deleted} / 跳过 {blocked}）", 5 + int(90 * idx / total))

        self.db.commit()
        stats = {
            "dead_songs": len(songs),
            "healed": healed,
            "deleted": deleted,
            "blocked": blocked,
        }
        if deleted or healed:
            write_log(
                self.db,
                action="delete",
                target="library",
                status="success",
                title="清理失效曲库记录",
                message=f"恢复 {healed} 首，清理 {deleted} 首，跳过 {blocked} 首（存储不可达）",
                detail={**stats, "deleted_titles": deleted_titles[:50]},
            )
            self.db.commit()
        return stats
