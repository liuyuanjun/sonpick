from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Favorite, Playlist, PlaylistItem, Song
from app.routers.auth import get_current_user
from app.schemas import (
    PlaylistAddSongs,
    PlaylistCreate,
    PlaylistOrder,
    PlaylistOut,
    PlaylistUpdate,
    SongOut,
)
from app.services.library_visibility import active_song_query
from app.services.song_version_summary import songs_with_summary

router = APIRouter(prefix="/playlists", tags=["playlists"])


def _playlist_out(db: Session, pl: Playlist, contains_song: Optional[bool] = None) -> PlaylistOut:
    count = (
        db.query(func.count(PlaylistItem.id))
        .filter(PlaylistItem.playlist_id == pl.id)
        .scalar()
        or 0
    )
    return PlaylistOut(**pl.to_dict(song_count=count), contains_song=contains_song)


@router.get("", response_model=list[PlaylistOut])
def list_playlists(
    song_id: Optional[int] = None,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 按手动排序位升序。刻意不用 updated_at：改个名/加首歌就把歌单顶到最前不是用户要的
    playlists = (
        db.query(Playlist)
        .order_by(Playlist.sort_order.asc(), Playlist.id.asc())
        .all()
    )
    # 带 song_id 时标注每个歌单是否已含该歌（供「加入歌单」弹层显示已加入状态）
    member_of: set[int] = set()
    if song_id is not None:
        member_of = {
            i.playlist_id
            for i in db.query(PlaylistItem.playlist_id)
            .filter(PlaylistItem.song_id == song_id)
            .all()
        }
    return [
        _playlist_out(db, p, contains_song=(p.id in member_of) if song_id is not None else None)
        for p in playlists
    ]


@router.post("", response_model=PlaylistOut)
def create_playlist(
    body: PlaylistCreate,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="歌单名称不能为空")
    # 新建的歌单排在末尾（手动排序的语义是「我摆好的顺序」，新来的不该插队）
    max_order = db.query(func.max(Playlist.sort_order)).scalar()
    pl = Playlist(
        name=name,
        description=(body.description or "").strip() or None,
        sort_order=(max_order if max_order is not None else -1) + 1,
    )
    db.add(pl)
    db.commit()
    db.refresh(pl)
    return _playlist_out(db, pl)


@router.put("/order", response_model=list[PlaylistOut])
def reorder_playlists(
    body: PlaylistOrder,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    按前端拖拽后的顺序重排歌单。

    ⚠️ 本路由必须声明在 `/{playlist_id}` **之前**：Starlette 按声明顺序匹配，
    否则 "order" 会被当成 playlist_id 去转 int，直接 422。

    未出现在 ids 里的歌单（其它客户端刚建的）保持原有相对顺序、整体排到末尾，
    而不是被清成 0 —— 否则它们会突然插到最前面。
    """
    all_pls = (
        db.query(Playlist)
        .order_by(Playlist.sort_order.asc(), Playlist.id.asc())
        .all()
    )
    by_id = {pl.id: pl for pl in all_pls}
    ordered_ids = list(dict.fromkeys(body.ids))  # 去重且保序
    unknown = [pid for pid in ordered_ids if pid not in by_id]
    if unknown:
        raise HTTPException(status_code=400, detail=f"歌单不存在: {unknown}")

    requested = set(ordered_ids)
    tail = [pl for pl in all_pls if pl.id not in requested]

    for idx, pid in enumerate(ordered_ids):
        by_id[pid].sort_order = idx
    for offset, pl in enumerate(tail):
        pl.sort_order = len(ordered_ids) + offset

    db.commit()
    return [
        _playlist_out(db, pl)
        for pl in db.query(Playlist)
        .order_by(Playlist.sort_order.asc(), Playlist.id.asc())
        .all()
    ]


@router.get("/{playlist_id}", response_model=PlaylistOut)
def get_playlist(
    playlist_id: int,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pl = db.get(Playlist, playlist_id)
    if not pl:
        raise HTTPException(status_code=404, detail="歌单不存在")
    return _playlist_out(db, pl)


@router.put("/{playlist_id}", response_model=PlaylistOut)
def update_playlist(
    playlist_id: int,
    body: PlaylistUpdate,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pl = db.get(Playlist, playlist_id)
    if not pl:
        raise HTTPException(status_code=404, detail="歌单不存在")
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="歌单名称不能为空")
        pl.name = name
    if body.description is not None:
        pl.description = body.description.strip() or None
    pl.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(pl)
    return _playlist_out(db, pl)


@router.delete("/{playlist_id}")
def delete_playlist(
    playlist_id: int,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pl = db.get(Playlist, playlist_id)
    if not pl:
        raise HTTPException(status_code=404, detail="歌单不存在")
    db.query(PlaylistItem).filter(PlaylistItem.playlist_id == playlist_id).delete()
    db.delete(pl)
    db.commit()
    return {"ok": True}


@router.get("/{playlist_id}/songs", response_model=list[SongOut])
def list_playlist_songs(
    playlist_id: int,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pl = db.get(Playlist, playlist_id)
    if not pl:
        raise HTTPException(status_code=404, detail="歌单不存在")
    items = (
        db.query(PlaylistItem)
        .filter(PlaylistItem.playlist_id == playlist_id)
        .order_by(PlaylistItem.position.asc(), PlaylistItem.id.asc())
        .all()
    )
    song_ids = [i.song_id for i in items]
    if not song_ids:
        return []
    songs = active_song_query(db).filter(Song.id.in_(song_ids)).all()
    song_map = {s.id: s for s in songs}
    fav_ids = {
        f.song_id
        for f in db.query(Favorite).filter(Favorite.song_id.in_(song_ids)).all()
    }
    # 保持歌单自身的排序，批量序列化（含版本摘要，供列表的格式/大小列与信息弹窗使用）
    ordered_songs = [song_map[sid] for sid in song_ids if song_map.get(sid)]
    return songs_with_summary(db, ordered_songs, fav_ids)


@router.post("/{playlist_id}/songs", response_model=PlaylistOut)
def add_songs(
    playlist_id: int,
    body: PlaylistAddSongs,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pl = db.get(Playlist, playlist_id)
    if not pl:
        raise HTTPException(status_code=404, detail="歌单不存在")
    if not body.song_ids:
        return _playlist_out(db, pl)

    existing = {
        i.song_id
        for i in db.query(PlaylistItem)
        .filter(PlaylistItem.playlist_id == playlist_id)
        .all()
    }
    max_pos = (
        db.query(func.max(PlaylistItem.position))
        .filter(PlaylistItem.playlist_id == playlist_id)
        .scalar()
    )
    pos = (max_pos or 0) + 1
    for sid in body.song_ids:
        if sid in existing:
            continue
        song = db.get(Song, sid)
        if not song:
            continue
        db.add(PlaylistItem(playlist_id=playlist_id, song_id=sid, position=pos))
        if pl.cover_song_id is None:
            pl.cover_song_id = sid
        pos += 1
        existing.add(sid)
    pl.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(pl)
    return _playlist_out(db, pl)


@router.delete("/{playlist_id}/songs/{song_id}", response_model=PlaylistOut)
def remove_song(
    playlist_id: int,
    song_id: int,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pl = db.get(Playlist, playlist_id)
    if not pl:
        raise HTTPException(status_code=404, detail="歌单不存在")
    item = (
        db.query(PlaylistItem)
        .filter(
            PlaylistItem.playlist_id == playlist_id,
            PlaylistItem.song_id == song_id,
        )
        .first()
    )
    if item:
        db.delete(item)
    if pl.cover_song_id == song_id:
        next_item = (
            db.query(PlaylistItem)
            .filter(PlaylistItem.playlist_id == playlist_id)
            .order_by(PlaylistItem.position.asc(), PlaylistItem.id.asc())
            .first()
        )
        pl.cover_song_id = next_item.song_id if next_item else None
    pl.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(pl)
    return _playlist_out(db, pl)
