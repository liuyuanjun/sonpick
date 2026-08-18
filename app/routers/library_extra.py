"""Library extras: favorites, artists, albums, history, stats, cover, lyrics, play."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.library_organize_service import LibraryOrganizeService
from app.models import AppSettings, Favorite, MediaSource, PlayHistory, Playlist, Song, SongFile, Task, iso_utc

log = logging.getLogger("sonpick.library")
from app.routers.auth import get_current_user
from app.services.song_file_resolver import NoPlayableSongFileError, SongFileResolver
from app.schemas import (
    AlbumOut,
    ArtistOut,
    LibraryStatsOut,
    LyricsLineOut,
    LyricsOut,
    PlayHistoryOut,
    SongOut,
)
from app.services.lyrics_service import load_lyrics_for_song
from app.services.library_visibility import (
    active_song_filter,
    active_song_query,
    count_songs_in_source,
)
from app.services.scrape.cover_utils import enrich_cover_fields, qq_song_detail_cover
from app.services.media_meta_service import (
    extract_embedded_cover_bytes,
    is_local_file,
    materialize_song_cover,
    read_audio_duration,
    read_audio_tags,
)

router = APIRouter(tags=["library-extra"])


def _favorite_ids(db: Session, song_ids: list[int] | None = None) -> set[int]:
    q = db.query(Favorite.song_id)
    if song_ids is not None:
        if not song_ids:
            return set()
        q = q.filter(Favorite.song_id.in_(song_ids))
    return {row[0] for row in q.all()}


def _song_out(song: Song, fav_ids: set[int] | None = None) -> SongOut:
    data = song.to_dict()
    data["is_favorite"] = bool(fav_ids and song.id in fav_ids)
    return SongOut(**data)


@router.get("/songs/{song_id}/cover")
def get_cover(
    song_id: int,
    token: str = Query(None),
    db: Session = Depends(get_db),
):
    # Support token query for <img src> (no Authorization header available).
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        from app.security import decode_token

        payload = decode_token(token)
        if payload.get("sub") != "admin":
            raise HTTPException(status_code=401, detail="Invalid token")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    song = db.get(Song, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="歌曲不存在")

    # Fast path: already local, do not open WebDAV.
    cover = None
    if is_local_file(getattr(song, "cover_path", None)):
        cover = song.cover_path
    else:
        cover = materialize_song_cover(song, db=db)
    if not cover or not is_local_file(cover):
        raise HTTPException(status_code=404, detail="封面不存在")
    path = Path(cover)
    media = "image/jpeg"
    suffix = path.suffix.lower()
    if suffix in {".png"}:
        media = "image/png"
    elif suffix in {".webp"}:
        media = "image/webp"
    elif suffix in {".gif"}:
        media = "image/gif"
    return FileResponse(
        path,
        media_type=media,
        headers={
            "Cache-Control": "public, max-age=86400",
        },
    )


@router.get("/songs/{song_id}/lyrics", response_model=LyricsOut)
def get_lyrics(
    song_id: int,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    song = db.get(Song, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    # Prefer DB path; if empty/stale, fall back to same-stem .lrc next to audio and backfill.
    lines, raw, _resolved = load_lyrics_for_song(song, db=db, persist=True)
    return LyricsOut(
        song_id=song_id,
        lines=[LyricsLineOut(**ln) for ln in lines],
        raw=raw,
        lyrics_type=song.lyrics_type,
        provider=song.lyrics_provider,
        source_id=song.lyrics_source_id,
        fetched_at=iso_utc(song.lyrics_fetched_at),
        instrumental=bool(song.lyrics_instrumental),
    )


@router.get("/songs/{song_id}/files")
def get_song_files(
    song_id: int,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """返回该逻辑歌曲的全部本地/WebDAV 版本（含封面/歌词侧车与可写状态）。

    与播放、刮削/歌词检索共用 SongFileResolver.describe_files，作为「歌曲文件」列表的
    权威来源；前端刮削/歌词弹窗在打开时应拉取此处而非依赖内存里的 versions 字段，
    避免歌曲来自未填充 versions 的列表（如歌单）时显示「暂无歌曲文件记录」。
    """
    song = db.get(Song, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    return {"song_files": SongFileResolver(db).describe_files(song)}


class OrganizeSongApplyRequest(BaseModel):
    choices: list[int] = Field(default_factory=list, description="每个冲突项要保留的 song_file_id，顺序与 preview.conflicts 一致")


@router.post("/songs/{song_id}/organize/preview")
def organize_song_preview(
    song_id: int,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """预览把该歌的本地版本整理到标准路径（艺术家/专辑/歌名）。

    返回每个本地版本的去向、同歌同格式冲突（需用户选择保留哪一个，含码率/大小）、
    以及跨歌占用导致的 blocked 项（不自动覆盖他人文件）。专辑或标题不完整时
    complete=false，调用方应禁用整理。
    """
    song = db.get(Song, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    return LibraryOrganizeService(db).preview_organize_song(song_id)


@router.post("/songs/{song_id}/organize/apply")
def organize_song_apply(
    song_id: int,
    body: OrganizeSongApplyRequest,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """执行单曲整理：按选择保留冲突文件、删除另一文件及其侧车、清理空父文件夹、同步 SongFile/Song。"""
    song = db.get(Song, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    try:
        return LibraryOrganizeService(db).apply_organize_song(song_id, body.choices)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/songs/{song_id}/play", response_model=SongOut)
def record_play(
    song_id: int,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    song = db.get(Song, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    song.play_count = (song.play_count or 0) + 1
    song.updated_at = datetime.now(timezone.utc)
    db.add(PlayHistory(song_id=song_id))
    # Keep history table from growing unbounded
    total = db.query(func.count(PlayHistory.id)).scalar() or 0
    if total > 500:
        old_ids = [
            r[0]
            for r in (
                db.query(PlayHistory.id)
                .order_by(PlayHistory.played_at.asc())
                .limit(total - 500)
                .all()
            )
        ]
        if old_ids:
            db.query(PlayHistory).filter(PlayHistory.id.in_(old_ids)).delete(
                synchronize_session=False
            )
    db.commit()
    db.refresh(song)
    fav = _favorite_ids(db, [song.id])
    return _song_out(song, fav)


@router.post("/songs/{song_id}/enrich")
def enrich_song(
    song_id: int,
    async_mode: bool = Query(True, description="默认异步任务，避免反代/播放超时"),
    allow_network: bool = Query(True),
    write_file_tags: bool = Query(True),
    overwrite: bool = Query(False),
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """单曲元数据刮削。默认异步返回 task_id，避免播放时同步超时。"""
    import json
    from datetime import datetime, timezone

    from app.models import Task
    from app.services.task_worker import worker

    song = db.get(Song, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="歌曲不存在")

    payload = {
        "song_ids": [song_id],
        "allow_network": bool(allow_network),
        "overwrite": bool(overwrite),
        "write_file_tags": bool(write_file_tags),
        "limit": 1,
    }
    if async_mode:
        task = Task(
            type="scrape",
            status="pending",
            payload_json=json.dumps(payload, ensure_ascii=False),
            progress_json=json.dumps(
                {"percent": 0, "message": "queued", "logs": []},
                ensure_ascii=False,
            ),
            result_json="{}",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        try:
            worker.enqueue(task.id)
        except Exception:
            pass
        return {
            "async": True,
            "task_id": task.id,
            "status": task.status,
            "song_id": song_id,
            "message": "刮削任务已创建",
        }

    try:
        from app.services.scrape.job import run_scrape_job

        result = run_scrape_job(db, **payload)
        db.refresh(song)
        fav = _favorite_ids(db, [song.id])
        out = _song_out(song, fav)
        song_payload = out.model_dump() if hasattr(out, "model_dump") else out.dict()
        return {"async": False, "song": song_payload, "result": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"刮削失败: {type(e).__name__}: {e}") from e


class LyricsCandidateSearchRequest(BaseModel):
    source: str = "auto"
    keyword: str | None = Field(default=None, max_length=500)
    limit: int = Field(20, ge=1, le=20)


class LyricsCandidateDetailRequest(BaseModel):
    source: str
    source_id: str
    candidate: dict = Field(default_factory=dict)


class LyricsCandidateApplyRequest(BaseModel):
    candidate: dict
    write_file_tags: bool = True


class SongsLyricsRequest(BaseModel):
    song_ids: list[int] | None = None
    source_id: str = "auto"
    library_source_id: int | None = None
    only_missing: bool = True
    overwrite: bool = False
    write_file_tags: bool = True
    async_mode: bool = True


@router.post("/songs/{song_id}/lyrics/candidates")
def search_lyrics_candidates(
    song_id: int,
    body: LyricsCandidateSearchRequest,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.services.lyrics_search_service import LyricsApplicationError, LyricsSearchService

    song = db.get(Song, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    try:
        log.info("lyrics candidates search song_id=%s source=%r keyword=%r", song_id, body.source, body.keyword)
        result = LyricsSearchService(db).search(song, source=body.source, keyword=body.keyword or "", limit=body.limit)
        result["song_files"] = SongFileResolver(db).describe_files(song)
        if body.source != "auto" and not result.get("candidates") and result.get("errors"):
            error = result["errors"][0]
            status_code = 429 if error.get("code") == "rate_limited" else 502
            headers = {"Retry-After": str(error.get("retry_after"))} if error.get("retry_after") else None
            raise HTTPException(status_code=status_code, detail=error, headers=headers)
        return result
    except LyricsApplicationError as exc:
        raise HTTPException(status_code=400, detail=exc.detail()) from exc


@router.post("/songs/{song_id}/lyrics/candidate-details")
def get_lyrics_candidate_details(
    song_id: int,
    body: LyricsCandidateDetailRequest,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.services.lyrics_search_service import LyricsApplicationError, LyricsSearchService

    song = db.get(Song, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    try:
        return {
            "candidate": LyricsSearchService(db).details(body.source, body.source_id, fallback=body.candidate),
            "song_files": SongFileResolver(db).describe_files(song),
        }
    except LyricsApplicationError as exc:
        raise HTTPException(status_code=400, detail=exc.detail()) from exc


@router.post("/songs/{song_id}/lyrics/apply")
def apply_lyrics_candidate(
    song_id: int,
    body: LyricsCandidateApplyRequest,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.services.lyrics_search_service import LyricsApplicationError, LyricsSearchService
    from app.services.operation_log_service import write_log

    song = db.get(Song, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    try:
        result = LyricsSearchService(db).apply(
            song,
            body.candidate,
            write_file_tags=body.write_file_tags,
        )
        write_log(
            db,
            action="lyrics",
            target="local",
            status="success",
            title=f"{song.artist or ''} - {song.title}".strip(" -"),
            message=f"歌词已更新，来源 {result.get('source')}",
            local_path=result.get("lrc_path"),
            song_id=song.id,
            detail={"source": result.get("source"), "source_id": result.get("source_id"), "lyrics_type": result.get("lyrics_type")},
        )
        return result
    except LyricsApplicationError as exc:
        raise HTTPException(status_code=400, detail=exc.detail()) from exc


@router.delete("/songs/{song_id}/lyrics")
def clear_song_lyrics(
    song_id: int,
    confirm: bool = Query(False),
    clear_file_tags: bool = Query(True),
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.services.lyrics_search_service import LyricsApplicationError, LyricsSearchService
    from app.services.operation_log_service import write_log

    if not confirm:
        raise HTTPException(
            status_code=400,
            detail={"code": "confirmation_required", "message": "清空歌词需要 confirm=true"},
        )
    song = db.get(Song, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    try:
        result = LyricsSearchService(db).clear(song, write_file_tags=clear_file_tags)
        write_log(
            db,
            action="lyrics",
            target="local",
            status="success",
            title=f"{song.artist or ''} - {song.title}".strip(" -"),
            message="歌词已清空",
            song_id=song.id,
            detail={"operation": "clear", "removed_paths": result.get("removed_paths", []), "embedded_cleared": result.get("written_file_tags", False)},
        )
        return result
    except LyricsApplicationError as exc:
        raise HTTPException(status_code=400, detail=exc.detail()) from exc


@router.post("/songs/lyrics")
def fetch_songs_lyrics(
    body: SongsLyricsRequest,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    import json

    from app.services.lyrics_job import run_lyrics_job
    from app.services.task_worker import worker

    if body.only_missing and body.overwrite:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_batch_options", "message": "仅补缺失与覆盖已有不能同时启用"},
        )
    payload = {
        "song_ids": sorted(set(body.song_ids or [])) or None,
        "source_id": body.source_id or "auto",
        "library_source_id": body.library_source_id,
        "only_missing": bool(body.only_missing),
        "overwrite": bool(body.overwrite),
        "write_file_tags": bool(body.write_file_tags),
    }
    if body.async_mode:
        task = Task(
            type="lyrics",
            status="pending",
            payload_json=json.dumps(payload, ensure_ascii=False),
            progress_json=json.dumps({"percent": 0, "message": "等待获取歌词", "logs": []}, ensure_ascii=False),
            result_json="{}",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        worker.enqueue(task.id)
        return {"async": True, "task_id": task.id, "status": task.status, "payload": payload}
    return run_lyrics_job(db, **payload)


@router.post("/songs/{song_id}/favorite", response_model=SongOut)
def add_favorite(
    song_id: int,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    song = db.get(Song, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    exists = db.query(Favorite).filter(Favorite.song_id == song_id).first()
    if not exists:
        db.add(Favorite(song_id=song_id))
        db.commit()
    db.refresh(song)
    return _song_out(song, {song_id})


@router.delete("/songs/{song_id}/favorite", response_model=SongOut)
def remove_favorite(
    song_id: int,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    song = db.get(Song, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    fav = db.query(Favorite).filter(Favorite.song_id == song_id).first()
    if fav:
        db.delete(fav)
        db.commit()
    db.refresh(song)
    return _song_out(song, set())


@router.get("/favorites", response_model=list[SongOut])
def list_favorites(
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Favorite, Song)
        .join(Song, Song.id == Favorite.song_id)
        .filter(active_song_filter(db))
        .order_by(Favorite.created_at.desc())
        .all()
    )
    return [_song_out(song, {song.id}) for _, song in rows]


@router.get("/artists", response_model=list[ArtistOut])
def list_artists(
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    songs = active_song_query(db).all()
    groups: dict[str, list[Song]] = defaultdict(list)
    for s in songs:
        name = (s.artist or "未知艺术家").strip() or "未知艺术家"
        groups[name].append(s)
    result = []
    for name, items in groups.items():
        albums = {(s.album or "").strip() for s in items if (s.album or "").strip()}
        cover = next((s for s in items if is_local_file(s.cover_path)), None)
        if cover is None:
            cover = next((s for s in items if s.cover_path), items[0] if items else None)
        result.append(
            ArtistOut(
                name=name,
                song_count=len(items),
                album_count=len(albums),
                cover_song_id=cover.id if cover else None,
            )
        )
    result.sort(key=lambda a: (-a.song_count, a.name.lower()))
    return result


@router.get("/artists/{artist_name}/songs", response_model=list[SongOut])
def list_artist_songs(
    artist_name: str,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    name = artist_name.strip()
    if name == "未知艺术家":
        songs = (
            active_song_query(db)
            .filter((Song.artist.is_(None)) | (Song.artist == "") | (Song.artist == "未知艺术家"))
            .order_by(Song.title.asc())
            .all()
        )
    else:
        songs = (
            active_song_query(db)
            .filter(Song.artist == name)
            .order_by(Song.album.asc(), Song.title.asc())
            .all()
        )
    fav = _favorite_ids(db, [s.id for s in songs])
    return [_song_out(s, fav) for s in songs]


@router.get("/albums", response_model=list[AlbumOut])
def list_albums(
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    songs = active_song_query(db).all()
    groups: dict[tuple[str, str], list[Song]] = defaultdict(list)
    for s in songs:
        album = (s.album or "未知专辑").strip() or "未知专辑"
        artist = (s.artist or "未知艺术家").strip() or "未知艺术家"
        groups[(album, artist)].append(s)
    result = []
    for (album, artist), items in groups.items():
        cover = next((s for s in items if is_local_file(s.cover_path)), None)
        if cover is None:
            cover = next((s for s in items if s.cover_path), items[0] if items else None)
        result.append(
            AlbumOut(
                name=album,
                artist=artist,
                song_count=len(items),
                cover_song_id=cover.id if cover else None,
            )
        )
    result.sort(key=lambda a: (-a.song_count, a.name.lower()))
    return result


@router.get("/albums/songs", response_model=list[SongOut])
def list_album_songs(
    name: str = Query(...),
    artist: str = Query(None),
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    album = name.strip() or "未知专辑"
    q = active_song_query(db)
    if album == "未知专辑":
        q = q.filter((Song.album.is_(None)) | (Song.album == "") | (Song.album == "未知专辑"))
    else:
        q = q.filter(Song.album == album)
    if artist:
        a = artist.strip()
        if a == "未知艺术家":
            q = q.filter(
                (Song.artist.is_(None)) | (Song.artist == "") | (Song.artist == "未知艺术家")
            )
        else:
            q = q.filter(Song.artist == a)
    songs = q.order_by(Song.title.asc()).all()
    fav = _favorite_ids(db, [s.id for s in songs])
    return [_song_out(s, fav) for s in songs]


@router.get("/history", response_model=list[PlayHistoryOut])
def list_history(
    limit: int = Query(50, ge=1, le=200),
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(PlayHistory)
        .join(Song, Song.id == PlayHistory.song_id)
        .filter(active_song_filter(db))
        .order_by(PlayHistory.played_at.desc())
        .limit(limit)
        .all()
    )
    song_ids = [r.song_id for r in rows]
    songs = active_song_query(db).filter(Song.id.in_(song_ids)).all() if song_ids else []
    song_map = {s.id: s for s in songs}
    fav = _favorite_ids(db, song_ids)
    result = []
    for r in rows:
        song = song_map.get(r.song_id)
        result.append(
            PlayHistoryOut(
                id=r.id,
                song_id=r.song_id,
                played_at=iso_utc(r.played_at),
                song=_song_out(song, fav) if song else None,
            )
        )
    return result


@router.get("/library/stats")
def library_stats(
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    songs = active_song_query(db).all()
    artists = {(s.artist or "未知艺术家").strip() or "未知艺术家" for s in songs}
    albums = {
        ((s.album or "未知专辑").strip() or "未知专辑", (s.artist or "").strip())
        for s in songs
    }
    fav_count = db.query(func.count(Favorite.id)).join(Song, Song.id == Favorite.song_id).filter(active_song_filter(db)).scalar() or 0
    pl_count = db.query(func.count(Playlist.id)).scalar() or 0
    total_duration = sum(int(s.duration or 0) for s in songs)
    total_size = sum(int(s.file_size or 0) for s in songs)

    with_dur = sum(1 for s in songs if s.duration and s.duration > 0)
    with_cover = sum(1 for s in songs if s.cover_path)
    with_lrc = sum(1 for s in songs if s.lrc_path)
    song_count = len(songs) or 1

    pending = db.query(func.count(Task.id)).filter(Task.status == "pending").scalar() or 0
    running = db.query(func.count(Task.id)).filter(Task.status == "running").scalar() or 0

    sources = (
        db.query(MediaSource)
        .order_by(MediaSource.id.asc())
        .all()
    )
    source_rows = []
    for src in sources:
        source_rows.append({
            "id": src.id,
            "name": src.name,
            "type": src.type,
            "song_count": count_songs_in_source(db, src.id),
            "connection_status": src.connection_status or "unknown",
            "last_scan_at": iso_utc(src.last_scan_at),
            "is_default_upload": bool(src.is_default_upload),
        })

    return LibraryStatsOut(
        song_count=len(songs),
        artist_count=len(artists),
        album_count=len(albums),
        favorite_count=fav_count,
        playlist_count=pl_count,
        total_duration=total_duration,
        total_size=total_size,
        meta_completeness={
            "duration_pct": round(with_dur / song_count * 100, 1),
            "cover_pct": round(with_cover / song_count * 100, 1),
            "lyrics_pct": round(with_lrc / song_count * 100, 1),
            "duration_count": with_dur,
            "cover_count": with_cover,
            "lyrics_count": with_lrc,
        },
        sources=source_rows,
        tasks={
            "pending": pending,
            "running": running,
        },
    )


class ScrapeCandidateRequest(BaseModel):
    source: str = "auto"  # auto / netease / migu / qq
    keyword: str | None = Field(default=None, max_length=500)
    limit: int = Field(8, ge=1, le=30)


class ApplyScrapeCandidateRequest(BaseModel):
    candidate: dict
    selected_fields: list[str] = Field(default_factory=lambda: ["title", "artist", "album", "year", "genre", "cover"])
    write_file_tags: bool = True
    # 浏览器已预览成功的封面（base64，可带 dataURL 前缀）；NAS 出网失败时用此绕过服务器下载
    cover_image_base64: str | None = None
    cover_image_mime: str | None = None


def _local_song_file(db: Session, song: Song) -> SongFile | None:
    try:
        return SongFileResolver(db).resolve_local(song)
    except NoPlayableSongFileError:
        return None


def _candidate_query(song: Song, db: Session) -> tuple[str, str, int | None]:
    from app.services.scrape.query_normalize import repair_shifted_meta, split_title_artist

    rt, ra, _ = repair_shifted_meta(song.title, song.artist, song.album)
    title, artist = split_title_artist(rt or song.title, ra or song.artist)
    duration = song.duration
    song_file = _local_song_file(db, song)
    if (not duration or int(duration or 0) <= 0) and song_file:
        duration = read_audio_duration(song_file.local_path)
    return title or (song.title or ""), artist or "", duration


def _score_candidates(rows: list[dict], *, title: str, artist: str, duration: int | None) -> list[dict]:
    from app.services.scrape.match import score_candidate
    from app.services.scrape.providers.netease_http import fetch_netease_song_cover

    out = []
    for row in rows:
        detail = score_candidate(
            query_title=title,
            query_artist=artist or None,
            query_duration=duration,
            cand_title=row.get("title"),
            cand_artist=row.get("artist"),
            cand_album=row.get("album"),
            cand_duration=row.get("duration"),
            simple_mode=not bool(artist),
        )
        item = enrich_cover_fields(dict(row))
        if not item.get("cover_url") and item.get("source") == "netease":
            netease_cover = fetch_netease_song_cover(item.get("id"))
            if netease_cover.get("cover_url"):
                item["cover_url"] = netease_cover["cover_url"]
                item["cover_source"] = netease_cover.get("source")
            else:
                item["cover_diagnostic"] = netease_cover
        if not item.get("cover_url") and (item.get("source") == "qq" or item.get("source") == "QQMusicClient"):
            qq_cover = qq_song_detail_cover(item.get("id") or item.get("songmid"))
            if qq_cover.get("cover_url"):
                item["cover_url"] = qq_cover["cover_url"]
                item["cover_source"] = qq_cover.get("source")
                item["has_cover"] = True
                item["cover_lookup"] = qq_cover
        item["score"] = detail.get("total")
        item["score_detail"] = detail
        out.append(item)
    out.sort(key=lambda x: float(x.get("score") or 0), reverse=True)
    return out


def _search_candidates(song: Song, *, source: str = "auto", keyword: str | None = None, limit: int = 8, db: Session | None = None) -> dict:
    from app.services.scrape.providers.deezer import search_deezer
    from app.services.scrape.providers.itunes import search_itunes
    from app.services.scrape.providers.migu_http import search_migu
    from app.services.scrape.providers.musicbrainz import MusicBrainzProvider
    from app.services.scrape.providers.netease_http import fetch_netease_song_cover, search_netease
    from app.services.scrape.providers.smart_cn_provider import _search_qq_via_musicdl
    from app.services.scrape.base import ScrapeQuery
    from app.services.scrape.source_registry import select_source_configs
    from app.services.scrape.query_normalize import build_search_keyword, split_title_artist

    title, artist, duration = _candidate_query(song, db)
    keyword = (keyword or "").strip() or build_search_keyword(title, artist) or title
    manual_title, manual_artist = split_title_artist(keyword, None)
    score_title = manual_title or keyword
    score_artist = manual_artist or ""
    source_settings = db.get(AppSettings, 1) if db else None
    enabled_sources = select_source_configs(getattr(source_settings, "scrape_sources_json", None), automatic=source == "auto")
    allowed_ids = {item["id"]: item for item in enabled_sources}
    sources = [source] if source != "auto" else list(allowed_ids)
    if source != "auto" and source not in allowed_ids:
        raise HTTPException(status_code=400, detail="该刮削源未启用")
    rows: list[dict] = []
    for src in sources:
        try:
            if src == "netease":
                rows.extend(search_netease(keyword, limit=limit, timeout=18))
            elif src == "migu":
                rows.extend(search_migu(keyword, limit=limit, timeout=18))
            elif src == "qq":
                rows.extend(_search_qq_via_musicdl(keyword, limit=limit, timeout=25, db=db))
            elif src == "itunes":
                rows.extend(search_itunes(keyword, country=allowed_ids[src]["region"], limit=limit, timeout=18))
            elif src == "deezer":
                rows.extend(search_deezer(keyword, limit=limit, timeout=18))
            elif src == "musicbrainz":
                hit = MusicBrainzProvider().lookup(ScrapeQuery(title=score_title, artist=score_artist or None, duration=duration), timeout=18)
                if hit:
                    rows.append({"id": hit.raw.get("recording_id"), "title": hit.title, "artist": hit.artist, "album": hit.album, "duration": hit.duration, "cover_url": hit.cover_url, "source": "musicbrainz"})
        except Exception:
            continue
    candidates = _score_candidates(rows, title=score_title, artist=score_artist, duration=duration)
    return {
        "query": {"title": score_title, "artist": score_artist, "duration": duration, "keyword": keyword},
        "current": _candidate_current_values(song, db),
        "song_files": SongFileResolver(db).describe_files(song),
        "candidates": candidates[:limit],
    }


def _hydrate_candidate_details(candidate: dict) -> dict:
    return dict(candidate or {})


def _candidate_current_values(song: Song, db: Session) -> dict:
    song_file = _local_song_file(db, song)
    tags = read_audio_tags(song_file.local_path) if song_file else {}
    cover_path = song.cover_path if is_local_file(song.cover_path) else materialize_song_cover(song, db=db)
    cover_exists = bool(cover_path and is_local_file(cover_path))
    cover_size = None
    if cover_exists:
        try:
            cover_size = Path(cover_path).stat().st_size
        except OSError:
            cover_exists = False
            cover_path = None
    return {
        "title": song.title or tags.get("title"),
        "artist": song.artist or tags.get("artist"),
        "album": song.album or tags.get("album"),
        "year": song.year or tags.get("year"),
        "genre": song.genre or tags.get("genre"),
        "cover": cover_path,
        "cover_exists": cover_exists,
        "cover_size": cover_size,
    }


@router.get("/songs/{song_id}/tags")
def get_song_tags(
    song_id: int,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    song = db.get(Song, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    song_file = _local_song_file(db, song)
    tags = read_audio_tags(song_file.local_path) if song_file else {}
    duration = read_audio_duration(song_file.local_path) if song_file else None
    cover_bytes = extract_embedded_cover_bytes(song_file.local_path) if song_file else None
    return {
        "song_id": song.id,
        "file_version_id": song_file.id if song_file else None,
        "db": {"title": song.title, "artist": song.artist, "album": song.album, "year": song.year, "genre": song.genre, "duration": song.duration, "cover_path": song.cover_path, "lrc_path": song.lrc_path},
        "embedded": {**(tags or {}), "duration": duration, "cover_embedded": bool(cover_bytes), "cover_size": len(cover_bytes or b"")},
    }


@router.post("/songs/{song_id}/scrape/candidates")
def scrape_candidates(
    song_id: int,
    body: ScrapeCandidateRequest,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    song = db.get(Song, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    return _search_candidates(song, source=body.source, keyword=body.keyword, limit=body.limit, db=db)


@router.post("/songs/{song_id}/scrape/candidate-details")
def scrape_candidate_details(
    song_id: int,
    body: ApplyScrapeCandidateRequest,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    song = db.get(Song, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    return {
        "current": _candidate_current_values(song, db),
        "candidate": _hydrate_candidate_details(body.candidate),
        "song_files": SongFileResolver(db).describe_files(song),
    }


@router.post("/songs/{song_id}/scrape/apply")
def apply_scrape_candidate(
    song_id: int,
    body: ApplyScrapeCandidateRequest,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    song = db.get(Song, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    cand = _hydrate_candidate_details(body.candidate)
    selected_fields = set(body.selected_fields or [])
    allowed_fields = {"title", "artist", "album", "year", "genre", "cover"}
    unknown_fields = selected_fields - allowed_fields
    if unknown_fields:
        raise HTTPException(status_code=422, detail=f"不支持的刮削字段: {', '.join(sorted(unknown_fields))}")
    changes = {}
    for key in ("title", "artist", "album", "year", "genre"):
        if key not in selected_fields:
            continue
        val = cand.get(key)
        if str(getattr(song, key, "") or "") != str(val or ""):
            setattr(song, key, (val or "") if key == "title" else (val or None))
            changes[key] = val or None
    cover_url = cand.get("cover_url") if "cover" in selected_fields else None
    if "cover" in selected_fields:
        changes["cover_path"] = cover_url or None
    song.meta_provider = cand.get("provider") or cand.get("source") or "manual"
    song.meta_confidence = int(min(100, max(0, float(cand.get("score") or 0) * 20))) if cand.get("score") is not None else song.meta_confidence
    song.scrape_status = "done"
    song.updated_at = datetime.now(timezone.utc)
    db.add(song)
    db.flush()

    from app.services.song_metadata_apply_service import apply_metadata_to_song_files
    import base64
    import binascii
    import logging
    import re

    log = logging.getLogger("sonpick.meta")
    cover_bytes = None
    cover_mime = body.cover_image_mime
    if "cover" in selected_fields and body.cover_image_base64:
        raw_b64 = body.cover_image_base64.strip()
        m = re.match(r"^data:([^;]+);base64,(.+)$", raw_b64, re.DOTALL)
        if m:
            cover_mime = cover_mime or m.group(1)
            raw_b64 = m.group(2)
        try:
            cover_bytes = base64.b64decode(raw_b64, validate=False)
            if not cover_bytes:
                cover_bytes = None
            elif len(cover_bytes) > 8 * 1024 * 1024:
                log.warning("scrape apply cover_image too large song_id=%s size=%s", song_id, len(cover_bytes))
                cover_bytes = None
                cover_mime = None
        except (binascii.Error, ValueError) as exc:
            log.warning("scrape apply cover_image base64 decode failed song_id=%s err=%s", song_id, exc)
            cover_bytes = None
            cover_mime = None

    log.info(
        "scrape apply song_id=%s fields=%s cover_url=%s client_cover=%s write_file_tags=%s",
        song_id,
        sorted(selected_fields),
        bool(cover_url),
        bool(cover_bytes),
        body.write_file_tags,
    )

    file_result = apply_metadata_to_song_files(
        db,
        song,
        selected_fields=selected_fields,
        cover_url=cover_url if not cover_bytes else None,
        cover_bytes=cover_bytes,
        cover_mime=cover_mime,
        write_file_tags=body.write_file_tags,
    )
    db.refresh(song)
    if "cover" in selected_fields:
        changes["cover_path"] = song.cover_path
    fav = _favorite_ids(db, [song.id])
    l0_cover_ok = bool(song.cover_path and is_local_file(song.cover_path)) if "cover" in selected_fields else True
    if "cover" in selected_fields and cover_url is None and not song.cover_path:
        # 明确清空封面也算 L0 成功
        l0_cover_ok = True
    if not file_result.get("ok") or file_result.get("failed") or file_result.get("errors"):
        log.warning(
            "scrape apply result song_id=%s ok=%s failed=%s unsupported=%s errors=%s",
            song_id,
            file_result.get("ok"),
            file_result.get("failed"),
            file_result.get("unsupported"),
            file_result.get("error_summary") or file_result.get("errors"),
        )
    return {
        "ok": file_result["ok"],
        "changes": changes,
        "cover_result": {
            "ok": l0_cover_ok,
            "path": song.cover_path,
            "paths": file_result.get("cover_paths") or [],
            "l0": file_result.get("l0_cover"),
        },
        "file_result": file_result,
        "error_summary": file_result.get("error_summary") or None,
        "song": _song_out(song, fav).model_dump(),
    }


class SongsScrapeRequest(BaseModel):
    song_ids: list[int] | None = None
    source_id: int | None = None
    allow_network: bool = True
    overwrite: bool = False
    write_file_tags: bool = True
    limit: int = Field(20, ge=0)
    async_mode: bool = True


@router.post("/songs/scrape")
def scrape_songs(
    body: SongsScrapeRequest,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """批量刮削元数据（默认异步任务）。"""
    import json
    from datetime import datetime, timezone

    from app.models import Task
    from app.services.task_worker import worker

    payload = {
        "source_id": body.source_id,
        "song_ids": body.song_ids,
        "allow_network": bool(body.allow_network),
        "overwrite": bool(body.overwrite),
        "write_file_tags": bool(body.write_file_tags),
        "limit": int(body.limit or 20),
    }
    if body.async_mode:
        task = Task(
            type="scrape",
            status="pending",
            payload_json=json.dumps(payload, ensure_ascii=False),
            progress_json=json.dumps({"percent": 0, "message": "queued", "logs": []}, ensure_ascii=False),
            result_json="{}",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        try:
            worker.enqueue(task.id)
        except Exception:
            pass
        return {"async": True, "task_id": task.id, "status": task.status, "payload": payload}
    try:
        from app.services.scrape.job import run_scrape_job
        return run_scrape_job(db, **payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

