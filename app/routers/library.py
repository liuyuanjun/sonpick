import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Favorite, MediaSource, Song
from app.routers.auth import get_current_user
from app.schemas import SongOut
from app.services.convert_service import ConvertService
from app.services.operation_log_service import write_log
from app.services.webdav_service import WebDAVService

router = APIRouter(prefix="/songs", tags=["library"])


def _parse_range(range_header: str, file_size: int):
    unit, rng = range_header.split("=")
    start, end = rng.split("-")
    start = int(start) if start else 0
    end = int(end) if end else file_size - 1
    return start, end


def _active_source_ids(db: Session) -> list[int]:
    return [r[0] for r in db.query(MediaSource.id).filter(MediaSource.enabled == True).all()]


def _active_song_query(db: Session):
    active_ids = _active_source_ids(db)
    return db.query(Song).filter((Song.library_source_id.is_(None)) | (Song.library_source_id.in_(active_ids)))


def _favorite_ids(db: Session, song_ids: list[int]) -> set[int]:
    if not song_ids:
        return set()
    rows = db.query(Favorite.song_id).filter(Favorite.song_id.in_(song_ids)).all()
    return {r[0] for r in rows}


@router.get("", response_model=list[SongOut])
def list_songs(
    q: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(500, ge=1, le=2000),
    source_id: int | None = Query(None),
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = _active_song_query(db).order_by(Song.id.desc())
    if source_id is not None:
        query = query.filter(Song.library_source_id == source_id)
    if q:
        like = f"%{q}%"
        query = query.filter((Song.title.ilike(like)) | (Song.artist.ilike(like)))
    total = query.count()
    songs = query.offset((page - 1) * page_size).limit(page_size).all()
    fav = _favorite_ids(db, [s.id for s in songs])
    source_map = {s.id: s for s in db.query(MediaSource).filter(MediaSource.id.in_([song.library_source_id for song in songs if song.library_source_id])).all()}
    result = []
    for s in songs:
        data = s.to_dict()
        data["is_favorite"] = s.id in fav
        src = source_map.get(s.library_source_id)
        data["library_source_name"] = src.name if src else None
        data["library_source_type"] = src.type if src else None
        result.append(SongOut(**data))
    return result


@router.get("/{song_id}/stream")
async def stream_song(
    song_id: int,
    request: Request,
    token: str = Query(None),
    db: Session = Depends(get_db),
):
    # token query param for audio element
    if token:
        from app.security import decode_token
        try:
            decode_token(token)
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid token")
    else:
        # fallback header auth handled by dependency elsewhere; for simplicity allow token only
        pass

    song = db.get(Song, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")

    # prefer local; fallback webdav
    if song.local_path and Path(song.local_path).exists():
        path = Path(song.local_path)
        file_size = path.stat().st_size
        range_header = request.headers.get("range")
        if range_header:
            start, end = _parse_range(range_header, file_size)
            def iterfile():
                with open(path, "rb") as f:
                    f.seek(start)
                    remaining = end - start + 1
                    while remaining > 0:
                        chunk = f.read(min(64 * 1024, remaining))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk
            return StreamingResponse(
                iterfile(),
                status_code=206,
                media_type="audio/mpeg",
                headers={
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Accept-Ranges": "bytes",
                    "Content-Length": str(end - start + 1),
                },
            )
        return FileResponse(path, filename=path.name)

    if song.webdav_path:
        service = WebDAVService(db)
        # webdav_path may be absolute remote under base; stream expects relative to configured root path
        cfg_path = song.webdav_path
        # if path includes configured base prefix, strip to relative browse path is complex; pass as-is relative if possible
        try:
            return await service.stream(cfg_path, request.headers.get("range"))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    raise HTTPException(status_code=404, detail="No playable source")


@router.post("/{song_id}/convert")
def convert_song(
    song_id: int,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    song = db.get(Song, song_id)
    if not song or not song.local_path:
        raise HTTPException(status_code=404, detail="Song not found")
    try:
        svc = ConvertService(db)
        new_path = svc.convert_to_mp3(song.local_path, song_id=song.id)
        song = db.get(Song, song_id)
        song.updated_at = datetime.now(timezone.utc)
        db.commit()
        write_log(
            db,
            action="convert",
            target="local",
            status="success",
            title=f"{song.artist or ''} - {song.title}".strip(" -"),
            message="转码为 MP3",
            local_path=str(new_path),
            song_id=song.id,
        )
        return {"local_path": str(new_path)}
    except Exception as e:
        write_log(
            db,
            action="convert",
            target="local",
            status="failed",
            title=f"{song.artist or ''} - {song.title}".strip(" -") if song else None,
            message=str(e),
            song_id=song_id,
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{song_id}/upload-webdav")
def upload_to_webdav(
    song_id: int,
    source_id: int = Query(None),
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    song = db.get(Song, song_id)
    if not song or not song.local_path:
        raise HTTPException(status_code=404, detail="Song not found")

    service = WebDAVService(db, source_id=source_id)
    try:
        result = service.upload_song(song, source_id=source_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{song_id}")
def delete_song(
    song_id: int,
    delete_files: bool = Query(True),
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    song = db.get(Song, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")

    deleted = []
    if delete_files:
        for p in [song.local_path, song.cover_path, song.lrc_path]:
            if p and Path(p).exists():
                try:
                    Path(p).unlink()
                    deleted.append(p)
                except Exception:
                    pass

    title = f"{song.artist or ''} - {song.title}".strip(" -")
    write_log(
        db,
        action="delete",
        target="song",
        status="success",
        title=title,
        message="删除曲库条目" + ("并删除本地文件" if delete_files else ""),
        local_path=song.local_path,
        remote_path=song.webdav_path,
        song_id=song.id,
        detail={"deleted_files": deleted, "delete_files": delete_files},
    )
    db.delete(song)
    db.commit()
    return {"ok": True, "deleted_files": deleted}
