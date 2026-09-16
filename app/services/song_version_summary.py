"""歌曲文件版本摘要：把 SongFile 的展示级摘要批量附加到歌曲响应上。

为什么需要这一层（不是"多写一个 helper"）：

1. ``Song.format`` / ``Song.file_size`` 是历史遗留列，只在**扫描入库**与**下载替换**时写入；
   转码（``convert_service``）、``keep_both`` 新增版本（``download_duplicate_service``）、
   整理改路径（``library_organize_service``）都只更新 ``SongFile``，不更新 ``Song``。
   因此一首 FLAC 转码出 MP3 之后，``Song.file_size`` 仍是 FLAC 的旧值 —— 多版本场景下
   这两个列**必然失真**，不能作为展示依据。
2. ``SongFile`` 才是物理文件的唯一真相源，且一个 ``Song`` 对应 1..N 个 ``SongFile``。
   「这首歌是什么格式、多大」必须先定义取哪个版本，本模块统一按**音质优先**挑选
   （复用 ``SongFileResolver`` 的排序规则，避免展示与播放选择两套逻辑漂移）。
3. 列表接口必须**批量**取版本（一次 ``IN`` 查询），禁止按歌曲逐条查导致 N+1。

字段集与 ``/api/songs``（曲库列表）保持一致：``versions`` / ``available_formats`` /
``has_playable_file``，另加 `preferred_version`。前端各处可共用同一套渲染逻辑。
"""
from __future__ import annotations

from typing import Any, Callable, Iterable

from sqlalchemy.orm import Session

from app.models import MediaSource, Song, SongFile
from app.schemas import SongOut
from app.services.convert_service import order_playable_files


def is_playable_file(item: SongFile) -> bool:
    """与播放选择一致的"可用"判定：有路径且未被标记失效。"""
    return bool(item.local_path or item.webdav_path) and item.availability_status != "unavailable"


def load_versions_by_song(db: Session, song_ids: Iterable[int]) -> dict[int, list[SongFile]]:
    """一次查询取出这些歌曲的全部版本，按 id 升序（稳定顺序，便于 UI 逐行对应）。"""
    ids = [int(i) for i in song_ids if i is not None]
    if not ids:
        return {}
    rows = (
        db.query(SongFile)
        .filter(SongFile.song_id.in_(ids))
        .order_by(SongFile.id.asc())
        .all()
    )
    grouped: dict[int, list[SongFile]] = {}
    for item in rows:
        grouped.setdefault(item.song_id, []).append(item)
    return grouped


def load_source_priorities(db: Session) -> dict[int | None, int]:
    """来源播放优先级，供版本排序使用（一次查询，全表很小）。"""
    return {source.id: source.playback_priority for source in db.query(MediaSource).all()}


def build_version_summary(files: list[SongFile], priorities: dict[int | None, int]) -> dict[str, Any]:
    """由某首歌的版本列表派生展示摘要。``files`` 应为已按来源视图过滤后的列表。

    「首选版本」按 ``lossless_preferred=True`` 取值，语义是
    **播放器在「无损优先」模式下会选中的那个文件** —— 排序规则直接复用播放选择，
    所以列表上显示的格式/大小不会与播放行为脱节。
    """
    usable = [item for item in files if is_playable_file(item)]
    best = order_playable_files(usable, priorities, lossless_preferred=True)[0] if usable else None
    return {
        "versions": [item.to_dict() for item in files],
        "available_formats": sorted({item.format for item in files if item.format}),
        "has_playable_file": bool(usable),
        "preferred_version": None if best is None else {
            "id": best.id,
            "format": best.format,
            "file_size": best.file_size,
            "duration": best.duration,
            "location": "local" if best.local_path else "webdav",
            "availability_status": best.availability_status,
            # 版本总数用于列表上的「+N」角标
            "version_count": len(files),
        },
    }


def songs_with_summary(
    db: Session,
    songs: list[Song],
    favorite_ids: set[int] | None = None,
    filter_versions: Callable[[list[SongFile]], list[SongFile]] | None = None,
) -> list[SongOut]:
    """批量序列化歌曲（含版本摘要）。列表接口一律走这里，保证批量且字段一致。"""
    if not songs:
        return []
    files_by_song = load_versions_by_song(db, [song.id for song in songs])
    priorities = load_source_priorities(db)
    result: list[SongOut] = []
    for song in songs:
        files = files_by_song.get(song.id, [])
        if filter_versions is not None:
            files = filter_versions(files)
        data = song.to_dict()
        data["is_favorite"] = bool(favorite_ids and song.id in favorite_ids)
        data.update(build_version_summary(files, priorities))
        result.append(SongOut(**data))
    return result


def song_with_summary(
    db: Session,
    song: Song,
    favorite_ids: set[int] | None = None,
) -> SongOut:
    """单曲序列化（含版本摘要）。"""
    return songs_with_summary(db, [song], favorite_ids)[0]
