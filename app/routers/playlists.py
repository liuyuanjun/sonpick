from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Favorite, MediaSource, Playlist, PlaylistItem, Song
from app.routers.auth import get_current_user
from app.schemas import (
    PlaylistAddSongs,
    PlaylistCreate,
    PlaylistOut,
    PlaylistUpdate,
    SongOut,
)

router = APIRouter(prefix="/playlists", tags=["playlists"])


def _active_source_ids(db: Session) -> list[int]:
    return [r[0] for r in db.query(MediaSource.id).filter(MediaSource.enabled == True).all()]


def _active_song_query(db: Session):
    active_ids = _active_source_ids(db)
    return db.query(Song).filter((Song.library_source_id.is_(None)) | (Song.library_source_id.in_(active_ids)))


def _song_out(song: Song, favorite_ids: set[int] | None = None) -> SongOut:
    data = song.to_dict()
    data["is_favorite"] = bool(favorite_ids and song.id in favorite_ids)
    return SongOut(**data)


def _playlist_out(db: Session, pl: Playlist) -> PlaylistOut:
    count = (
        db.query(func.count(PlaylistItem.id))
        .filter(PlaylistItem.playlist_id == pl.id)
        .scalar()
        or 0
    )
    return PlaylistOut(**pl.to_dict(song_count=count))


@router.get("", response_model=list[PlaylistOut])
def list_playlists(
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    playlists = db.query(Playlist).order_by(Playlist.updated_at.desc()).all()
    return [_playlist_out(db, p) for p in playlists]


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
    songs = _active_song_query(db).filter(Song.id.in_(song_ids)).all()
    song_map = {s.id: s for s in songs}
    fav_ids = {
        f.song_id
        for f in db.query(Favorite).filter(Favorite.song_id.in_(song_ids)).all()
    }
    result = []
    for sid in song_ids:
        song = song_map.get(sid)
        if song:
            result.append(_song_out(song, fav_ids))
    return result


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
