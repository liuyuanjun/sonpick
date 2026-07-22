"""下载重复决策的执行逻辑：保留两者 / 下载完成后替换已有本地版本。

安全约束：
- 替换永远先把新文件复制到目标目录临时文件，``os.replace`` 近似原子替换；
- 任一步失败都不会删除或损坏旧文件；
- 不信任前端路径，SongFile 一律重新从数据库查询并校验；
- WebDAV remote-only 版本不提供替换（路由层已拦截，这里再兜底）。
"""
from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Song, SongFile
from app.services.library_layout import AUDIO_EXTS, unique_path
from app.services.song_file_resolver import SongFileResolver


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_new_local_file(db: Session, new_song: Song) -> SongFile:
    return SongFileResolver(db).resolve_local(new_song)


def _adopt_sidecars(db: Session, target_song: Song, donor: Song, donor_file: Optional[SongFile]) -> None:
    """把下载附带的封面/歌词补到目标歌曲（不覆盖已有资源）。"""
    if not target_song.cover_path and donor.cover_path:
        target_song.cover_path = donor.cover_path
    if not target_song.lrc_path and donor.lrc_path:
        target_song.lrc_path = donor.lrc_path
    if not target_song.duration and donor.duration:
        target_song.duration = donor.duration
    if not (target_song.album or "").strip() and (donor.album or "").strip():
        target_song.album = donor.album
    target_song.updated_at = _now()
    db.add(target_song)


def _discard_new_song(db: Session, new_song: Song, *, keep_file: bool = False) -> None:
    """删除下载流程临时创建的 Song/SongFile 记录（文件保留与否由调用方决定）。"""
    db.flush()
    db.query(SongFile).filter(SongFile.song_id == new_song.id).delete(synchronize_session=False)
    db.query(Song).filter(Song.id == new_song.id).delete(synchronize_session=False)
    db.flush()


def apply_keep_both(db: Session, new_song: Song, matched_song_id: Optional[int]) -> Song:
    """保留两者：新下载版本并入匹配的同一逻辑 Song 作为新 SongFile。

    匹配歌曲已不存在时退化为独立新歌（兼容旧行为）。
    """
    matched = db.get(Song, matched_song_id) if matched_song_id else None
    if not matched:
        return new_song
    new_file = _resolve_new_local_file(db, new_song)
    new_file.song_id = matched.id
    if matched.library_source_id is None and new_song.library_source_id is not None:
        matched.library_source_id = new_song.library_source_id
    new_file.updated_at = _now()
    db.add(new_file)
    _adopt_sidecars(db, matched, new_song, new_file)
    _discard_new_song(db, new_song)
    db.flush()
    return matched


def apply_replace(
    db: Session,
    new_song: Song,
    replace_song_file_id: int,
    expected_song_id: Optional[int],
    task_id: Optional[int] = None,
) -> Song:
    """下载完成后替换指定已有本地版本。任何失败抛出异常且不动旧文件。"""
    old_file = db.get(SongFile, replace_song_file_id)
    if not old_file:
        raise RuntimeError("要替换的曲库版本已不存在")
    if expected_song_id and old_file.song_id != expected_song_id:
        raise RuntimeError("要替换的版本已不属于匹配的曲库歌曲")
    if not old_file.local_path:
        raise RuntimeError("远端版本暂不支持替换")
    old_path = Path(old_file.local_path)
    if not old_path.is_file():
        raise RuntimeError("要替换的本地文件已不可访问")

    new_file = _resolve_new_local_file(db, new_song)
    new_path = Path(new_file.local_path)
    if not new_path.is_file() or new_path.stat().st_size <= 0:
        raise RuntimeError("下载结果无效，未执行替换")
    new_ext = new_path.suffix.lower()
    if new_ext not in AUDIO_EXTS:
        raise RuntimeError(f"下载结果不是支持的音频格式: {new_ext}")

    # 目标路径：同格式直接原位替换；格式变化则换扩展名（避让同名第三方文件）
    if new_ext == old_path.suffix.lower():
        target = old_path
    else:
        candidate = old_path.with_suffix(new_ext)
        if candidate.exists():
            candidate = unique_path(old_path.parent, old_path.stem, new_ext)
        target = candidate

    tmp = target.parent / f".{target.name}.sonpick-replace-{task_id or 'tmp'}"
    try:
        shutil.copy2(new_path, tmp)
        if not tmp.is_file() or tmp.stat().st_size <= 0:
            raise RuntimeError("临时文件写入失败，未执行替换")
        os.replace(tmp, target)
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise

    # 替换成功后再清理旧文件（格式变化导致路径不同的情况）
    if target != old_path:
        try:
            old_path.unlink()
        except OSError:
            pass

    # 同名歌词侧车：优先沿用旧的，缺失时采用新下载的
    old_lrc = old_path.with_suffix(".lrc")
    lrc_path = old_file.lrc_path
    if not (lrc_path and Path(lrc_path).is_file()):
        new_lrc = None
        if new_file.lrc_path and Path(new_file.lrc_path).is_file():
            new_lrc = Path(new_file.lrc_path)
        elif new_song.lrc_path and Path(new_song.lrc_path).is_file():
            new_lrc = Path(new_song.lrc_path)
        if new_lrc:
            lrc_target = target.with_suffix(".lrc")
            try:
                if new_lrc.resolve() != lrc_target.resolve():
                    shutil.copy2(new_lrc, lrc_target)
                lrc_path = str(lrc_target)
            except OSError:
                lrc_path = None
        elif old_lrc.is_file() and old_path.suffix.lower() == target.suffix.lower():
            lrc_path = str(old_lrc)

    old_file.local_path = str(target)
    old_file.format = new_ext.lstrip(".")
    old_file.file_size = target.stat().st_size
    if new_song.duration:
        old_file.duration = new_song.duration
    old_file.lrc_path = lrc_path
    if not old_file.cover_path and new_file.cover_path:
        old_file.cover_path = new_file.cover_path
    old_file.availability_status = "available"
    old_file.last_error = None
    old_file.last_checked_at = _now()
    old_file.updated_at = _now()
    db.add(old_file)

    song = db.get(Song, old_file.song_id)
    if song:
        song.format = old_file.format
        song.file_size = old_file.file_size
        if old_file.duration:
            song.duration = old_file.duration
        if lrc_path and not song.lrc_path:
            song.lrc_path = lrc_path
        if old_file.cover_path and not song.cover_path:
            song.cover_path = old_file.cover_path
        song.updated_at = _now()
        db.add(song)

    _discard_new_song(db, new_song)

    # 清理下载目录中残留的原始新文件（音频与未采用的侧车）
    adopted = {str(target)}
    if lrc_path:
        adopted.add(str(Path(lrc_path).resolve()))
    if old_file.cover_path:
        adopted.add(str(Path(old_file.cover_path).resolve()))
    leftovers = [new_path, new_file.lrc_path, new_file.cover_path, new_song.lrc_path, new_song.cover_path]
    for item in leftovers:
        if not item:
            continue
        p = Path(item)
        try:
            if p.is_file() and str(p.resolve()) not in adopted:
                p.unlink()
        except OSError:
            pass
    try:
        d = new_path.parent
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    except OSError:
        pass

    db.flush()
    return song
