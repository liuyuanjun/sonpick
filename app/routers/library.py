import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.models import AppSettings, Favorite, MediaSource, Song, SongFile
from app.routers.auth import get_current_user
from app.schemas import SongOut
from app.services.convert_service import LOSSLESS_FORMATS, ConvertService
from app.services.operation_log_service import write_log
from app.services.song_file_resolver import NoPlayableSongFileError, SongFileResolver
from app.services.webdav_service import WebDAVService

router = APIRouter(prefix="/songs", tags=["library"])


# 正在后台转码的 song_id，避免同一首歌并发重复转码
_converting_song_ids: set[int] = set()
_converting_lock = threading.Lock()


def _maybe_auto_convert_mp3(db: Session, song: Song, lossless_preferred: bool) -> None:
    """播放时若优先 MP3 但缺失，则在后台自动转码（本次播放仍回退无损）。"""
    if lossless_preferred:
        return
    settings = db.get(AppSettings, 1)
    if not settings or not getattr(settings, "auto_convert_when_lossless_not_preferred", False):
        return
    files = db.query(SongFile).filter(SongFile.song_id == song.id).all()
    if any((f.format or "").lower() == "mp3" and f.local_path and Path(f.local_path).exists() for f in files):
        return
    if not any((f.format or "").lower() in LOSSLESS_FORMATS and f.local_path and Path(f.local_path).exists() for f in files):
        return
    with _converting_lock:
        if song.id in _converting_song_ids:
            return
        _converting_song_ids.add(song.id)
    threading.Thread(target=_convert_mp3_in_background, args=(song.id,), daemon=True).start()


def _convert_mp3_in_background(song_id: int) -> None:
    try:
        with SessionLocal() as db:
            song = db.get(Song, song_id)
            if not song:
                return
            title = f"{song.artist or ''} - {song.title}".strip(" -")
            try:
                mp3_file = ConvertService(db).convert_song_to_mp3(song)
                write_log(
                    db,
                    action="convert",
                    target="local",
                    status="success",
                    title=title,
                    message="播放时自动转码 MP3",
                    local_path=str(mp3_file.local_path),
                    song_id=song.id,
                )
            except Exception as exc:
                write_log(
                    db,
                    action="convert",
                    target="local",
                    status="failed",
                    title=title,
                    message=str(exc),
                    song_id=song.id,
                )
    finally:
        with _converting_lock:
            _converting_song_ids.discard(song_id)


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
    return db.query(Song).filter(
        Song.id.in_(db.query(SongFile.song_id).filter(
            (SongFile.library_source_id.is_(None)) | (SongFile.library_source_id.in_(active_ids))
        ))
    )


def _playable_song_ids(db: Session):
    """至少有一个有效版本的 Song 子查询。

    有效版本 = local_path 或 webdav_path 非空，且未被标记 unavailable
    （与 song_file_resolver.candidates 的口径一致）。
    """
    return db.query(SongFile.song_id).filter(
        (SongFile.local_path.isnot(None)) | (SongFile.webdav_path.isnot(None)),
        (SongFile.availability_status.is_(None)) | (SongFile.availability_status != "unavailable"),
    )


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
    include_unavailable: bool = Query(False),
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    source = None
    source_type = None
    if source_id is not None:
        source = db.get(MediaSource, source_id)
        source_type = source.type if source else None

    query = _active_song_query(db).order_by(Song.id.desc())
    if not include_unavailable:
        query = query.filter(Song.id.in_(_playable_song_ids(db)))
    if source_id is not None:
        # 单源视图：只展示在该源内实际可播放的歌曲
        if source_type == "local":
            # 本地源需校验文件真实存在
            playable_ids = []
            for sf in db.query(SongFile).filter(
                SongFile.library_source_id == source_id,
                SongFile.local_path.isnot(None),
                (SongFile.availability_status.is_(None)) | (SongFile.availability_status != "unavailable"),
            ).all():
                if Path(sf.local_path).exists():
                    playable_ids.append(sf.song_id)
                else:
                    sf.availability_status = "unavailable"
                    sf.last_error = "本地文件不存在"
                    sf.last_checked_at = datetime.now(timezone.utc)
                    sf.updated_at = datetime.now(timezone.utc)
            db.commit()
            query = query.filter(Song.id.in_(playable_ids))
        elif source_type == "webdav":
            query = query.filter(Song.id.in_(
                db.query(SongFile.song_id).filter(
                    SongFile.library_source_id == source_id,
                    SongFile.webdav_path.isnot(None),
                    (SongFile.availability_status.is_(None)) | (SongFile.availability_status != "unavailable"),
                )
            ))
        else:
            query = query.filter(Song.id.in_(db.query(SongFile.song_id).filter(SongFile.library_source_id == source_id)))
    if q:
        like = f"%{q}%"
        query = query.filter((Song.title.ilike(like)) | (Song.artist.ilike(like)))
    total = query.count()
    songs = query.offset((page - 1) * page_size).limit(page_size).all()
    fav = _favorite_ids(db, [s.id for s in songs])
    song_ids = [song.id for song in songs]
    song_files = db.query(SongFile).filter(SongFile.song_id.in_(song_ids)).all() if song_ids else []
    files_by_song: dict[int, list[SongFile]] = {}
    for item in song_files:
        files_by_song.setdefault(item.song_id, []).append(item)
    result = []
    for s in songs:
        data = s.to_dict()
        data["is_favorite"] = s.id in fav
        versions = files_by_song.get(s.id, [])
        # 单源视图：只保留当前源内的版本
        if source_id is not None:
            versions = [v for v in versions if v.library_source_id == source_id]
            if source_type == "local":
                versions = [v for v in versions if v.local_path and Path(v.local_path).exists()]
            elif source_type == "webdav":
                versions = [v for v in versions if v.webdav_path and v.availability_status != "unavailable"]
        primary = ConvertService(db).select_playable_file(s, lossless_preferred=False, source_id=source_id)
        data["versions"] = [item.to_dict() for item in versions]
        data["available_formats"] = sorted({item.format for item in versions if item.format})
        data["has_playable_file"] = primary is not None
        result.append(SongOut(**data))
    return result


@router.get("/{song_id}/stream")
async def stream_song(
    song_id: int,
    request: Request,
    token: str = Query(None),
    lossless_preferred: bool = Query(False),
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

    candidates = ConvertService(db).select_playable_files(song, lossless_preferred=lossless_preferred)
    if not candidates:
        raise HTTPException(status_code=404, detail="No playable source")

    _maybe_auto_convert_mp3(db, song, lossless_preferred)

    last_error: Exception | None = None
    for selected in candidates:
        try:
            if selected.local_path and Path(selected.local_path).exists():
                selected.availability_status = "available"
                selected.last_error = None
                selected.last_checked_at = datetime.now(timezone.utc)
                db.commit()
                path = Path(selected.local_path)
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
                    return StreamingResponse(iterfile(), status_code=206, media_type="audio/mpeg", headers={"Content-Range": f"bytes {start}-{end}/{file_size}", "Accept-Ranges": "bytes", "Content-Length": str(end - start + 1), "X-Playback-Format": selected.format})
                return FileResponse(path, filename=path.name, headers={"X-Playback-Format": selected.format})
            if selected.webdav_path:
                response = await WebDAVService(db, source_id=selected.library_source_id).stream(selected.webdav_path, request.headers.get("range"))
                selected.availability_status = "available"
                selected.last_error = None
                selected.last_checked_at = datetime.now(timezone.utc)
                db.commit()
                response.headers["X-Playback-Format"] = selected.format
                return response
        except Exception as exc:
            last_error = exc
            selected.availability_status = "unavailable"
            selected.last_error = str(exc)[:512]
            selected.last_checked_at = datetime.now(timezone.utc)
            db.commit()

    raise HTTPException(status_code=503, detail=f"All playback sources failed: {last_error}")


@router.post("/{song_id}/convert")
def convert_song(
    song_id: int,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建异步转码任务：立即返回 task_id，转码进度在任务中心查看。"""
    from app.models import Task
    from app.services.task_worker import worker

    song = db.get(Song, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    task = Task(
        type="convert",
        status="pending",
        payload_json=json.dumps({"song_id": song_id}, ensure_ascii=False),
        progress_json=json.dumps({"message": "等待执行", "percent": 0}, ensure_ascii=False),
        result_json="{}",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    worker.enqueue(task.id)
    return {"async": True, "task_id": task.id, "status": task.status}


@router.post("/{song_id}/upload-webdav")
def upload_to_webdav(
    song_id: int,
    source_id: int = Query(None),
    policy: str = Query(None),
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    song = db.get(Song, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    try:
        version = SongFileResolver(db).resolve_local(song, lossless_preferred=True)
    except NoPlayableSongFileError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    service = WebDAVService(db, source_id=source_id)
    try:
        result = service.upload_song(song, source_id=source_id, local_path=version.local_path, policy=policy)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{song_id}/upload-webdav/check")
def check_upload_conflicts(
    song_id: int,
    source_id: int = Query(None),
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    song = db.get(Song, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    try:
        version = SongFileResolver(db).resolve_local(song, lossless_preferred=True)
    except NoPlayableSongFileError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    service = WebDAVService(db, source_id=source_id)
    try:
        return service.check_conflicts(song, source_id=source_id, local_path=version.local_path)
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
    local_paths = []
    remote_paths = []
    versions = db.query(SongFile).filter(SongFile.song_id == song.id).all()
    if delete_files:
        for version in versions:
            if version.local_path:
                local_paths.append(version.local_path)
                for path in (version.local_path, version.cover_path, version.lrc_path):
                    if path and Path(path).is_file():
                        try:
                            Path(path).unlink()
                            deleted.append(path)
                        except OSError:
                            pass
            if version.webdav_path:
                remote_paths.append(version.webdav_path)

    title = f"{song.artist or ''} - {song.title}".strip(" -")
    write_log(
        db,
        action="delete",
        target="song",
        status="success",
        title=title,
        message="删除曲库条目" + ("并删除本地文件" if delete_files else ""),
        local_path=local_paths[0] if local_paths else None,
        remote_path=remote_paths[0] if remote_paths else None,
        song_id=song.id,
        detail={"deleted_files": deleted, "delete_files": delete_files, "version_count": len(versions)},
    )
    db.delete(song)
    db.commit()
    return {"ok": True, "deleted_files": deleted}
