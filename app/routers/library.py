import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AppSettings, Favorite, MediaSource, Song, SongFile, Task
from app.routers.auth import get_current_user
from app.schemas import RandomPoolOut, RandomSongOut, SongOut, SongPageOut
from app.services.convert_service import LOSSLESS_FORMATS, ConvertService
from app.services.library_visibility import active_song_query
from app.services.operation_log_service import write_log
from app.services.song_file_resolver import NoPlayableSongFileError, SongFileResolver
from app.services.webdav_service import WebDAVService

router = APIRouter(prefix="/songs", tags=["library"])


def _maybe_auto_convert_mp3(db: Session, song: Song, lossless_preferred: bool) -> None:
    """播放时若优先 MP3 但缺失，则创建异步转码任务（本次播放仍回退无损）。

    转码统一走任务系统（type=convert）：进度/日志/取消语义与手动转码一致，
    不再使用游离的裸线程。同一首歌已有排队/执行中的转码任务时跳过。
    """
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
    for existing in db.query(Task).filter(Task.type == "convert", Task.status.in_(["pending", "running"])).all():
        try:
            if int(json.loads(existing.payload_json or "{}").get("song_id") or 0) == song.id:
                return
        except Exception:
            continue
    task = Task(
        type="convert",
        status="pending",
        payload_json=json.dumps({"song_id": song.id}, ensure_ascii=False),
        progress_json=json.dumps({"message": "等待执行（播放时自动转码）", "percent": 0}, ensure_ascii=False),
        result_json="{}",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    from app.services.task_worker import worker

    worker.enqueue(task.id)


def _parse_range(range_header: str, file_size: int):
    unit, rng = range_header.split("=")
    start, end = rng.split("-")
    start = int(start) if start else 0
    end = int(end) if end else file_size - 1
    return start, end


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


@router.get("/random-pool", response_model=RandomPoolOut)
def random_pool(
    q: str = Query(None),
    source_id: int | None = Query(None),
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = active_song_query(db).filter(Song.id.in_(_playable_song_ids(db)))
    if q:
        like = f"%{q}%"
        query = query.filter((Song.title.ilike(like)) | (Song.artist.ilike(like)))
    if source_id is not None:
        query = query.filter(Song.id.in_(
            db.query(SongFile.song_id).filter(SongFile.library_source_id == source_id)
        ))
    songs = query.order_by(Song.id).all()
    return RandomPoolOut(
        items=[RandomSongOut(
            id=s.id, title=s.title, artist=s.artist, album=s.album,
            duration=s.duration, cover_path=s.cover_path,
        ) for s in songs],
        total=len(songs),
    )


@router.get("", response_model=SongPageOut)
def list_songs(
    q: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=2000),
    source_id: int | None = Query(None),
    include_unavailable: bool = Query(False),
    availability: str = Query(None),
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # availability: available（默认，至少一个有效版本）| all | unavailable（全部版本失效）
    availability = (availability or ("all" if include_unavailable else "available")).lower()
    if availability not in ("available", "all", "unavailable"):
        raise HTTPException(status_code=422, detail="availability 必须是 available / all / unavailable")
    source = None
    source_type = None
    if source_id is not None:
        source = db.get(MediaSource, source_id)
        source_type = source.type if source else None

    query = active_song_query(db).order_by(Song.id.desc())
    if availability == "available":
        query = query.filter(Song.id.in_(_playable_song_ids(db)))
    elif availability == "unavailable":
        query = query.filter(Song.id.notin_(_playable_song_ids(db)))
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
        playable_versions = [
            item for item in versions
            if (item.local_path or item.webdav_path) and item.availability_status != "unavailable"
        ]
        data["versions"] = [item.to_dict() for item in versions]
        data["available_formats"] = sorted({item.format for item in versions if item.format})
        data["has_playable_file"] = bool(playable_versions)
        result.append(SongOut(**data))
    return SongPageOut(items=result, total=total, page=page, page_size=page_size)


@router.post("/{song_id}/recheck", response_model=SongOut)
def recheck_song(
    song_id: int,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """逐个版本重新探测可用性：本地 stat、WebDAV 远程探测。

    探测不可达（如 WebDAV 连接失败）时保留原状态并记录错误，不会误标失效。
    """
    song = db.get(Song, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")

    now = datetime.now(timezone.utc)
    versions = db.query(SongFile).filter(SongFile.song_id == song.id).all()
    for sf in versions:
        if sf.local_path:
            exists = Path(sf.local_path).is_file()
            sf.availability_status = "available" if exists else "unavailable"
            sf.last_error = None if exists else "本地文件不存在"
            sf.last_checked_at = now
            sf.updated_at = now
            db.add(sf)
        elif sf.webdav_path and sf.library_source_id is not None:
            try:
                from app.services.webdav_service import WebDAVService

                exists = WebDAVService(db=db, source_id=sf.library_source_id).exists_path(sf.webdav_path)
                sf.availability_status = "available" if exists else "unavailable"
                sf.last_error = None if exists else "远端文件不存在"
            except Exception as e:
                # 连接失败：保留原状态，仅记录本次检查错误
                sf.last_error = f"检查失败: {type(e).__name__}: {e}"[:500]
            sf.last_checked_at = now
            sf.updated_at = now
            db.add(sf)

    from app.services.song_file_resolver import refresh_song_aggregate_assets

    refresh_song_aggregate_assets(db, song)
    db.commit()
    db.refresh(song)

    data = song.to_dict()
    data["is_favorite"] = song.id in _favorite_ids(db, [song.id])
    data["versions"] = [item.to_dict() for item in versions]
    data["available_formats"] = sorted({item.format for item in versions if item.format})
    data["has_playable_file"] = ConvertService(db).select_playable_file(song, lossless_preferred=False) is not None
    return SongOut(**data)


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
