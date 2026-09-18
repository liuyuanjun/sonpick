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
    playlists = db.query(Playlist).order_by(Playlist.updated_at.desc()).all()
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
    pl = Playlist(name=name, description=(body.description or "").strip() or None)
    db.add(pl)
    db.commit()
    db.refresh(pl)
    return _playlist_out(db, pl)


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
