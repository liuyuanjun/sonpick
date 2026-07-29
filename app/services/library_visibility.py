"""曲库可见性与来源归属的统一口径。

Song 不记录来源；一首歌是否可见、是否属于某来源，完全由它的 SongFile 版本决定：

- 可见（启用来源口径）= 拥有任一版本，其来源处于启用状态（版本无来源的历史数据也可见）
- 属于来源 X = 拥有任一版本 library_source_id == X

所有列表过滤、批量任务选歌、来源统计都必须使用本模块，禁止再按 Song 记来源。
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import MediaSource, Song, SongFile


def active_source_ids(db: Session) -> list[int]:
    return [r[0] for r in db.query(MediaSource.id).filter(MediaSource.enabled == True).all()]


def active_song_filter(db: Session):
    """过滤条件：歌曲拥有任一属于启用来源（或无来源）的版本。"""
    active_ids = active_source_ids(db)
    return Song.id.in_(
        db.query(SongFile.song_id).filter(
            (SongFile.library_source_id.is_(None)) | (SongFile.library_source_id.in_(active_ids))
        )
    )


def active_song_query(db: Session):
    return db.query(Song).filter(active_song_filter(db))


def has_version_in_source(db: Session, source_id: int):
    """过滤条件：歌曲拥有任一属于指定来源的版本。"""
    return Song.id.in_(
        db.query(SongFile.song_id).filter(SongFile.library_source_id == source_id)
    )


def count_songs_in_source(db: Session, source_id: int) -> int:
    """来源的歌曲数 = 该来源下不同 song_id 的版本归属数。"""
    return (
        db.query(SongFile.song_id)
        .filter(SongFile.library_source_id == source_id)
        .distinct()
        .count()
    )
