"""Library extras: favorites, artists, albums, history, stats, cover, lyrics, play."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.library_organize_service import LibraryOrganizeService
from app.models import AppSettings, Favorite, MediaSource, PlayHistory, Playlist, Song, SongFile, Task, iso_utc
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
from app.services.scrape.cover_utils import download_cover_with_diagnostics, enrich_cover_fields, extract_qq_songmid, qq_song_detail_cover
from app.services.media_meta_service import (
    extract_embedded_cover_bytes,
    is_local_file,
    materialize_song_cover,
    read_audio_duration,
    read_audio_tags,
    write_audio_tags,
)

router = APIRouter(tags=["library-extra"])


def _active_source_ids(db: Session) -> list[int]:
    return [r[0] for r in db.query(MediaSource.id).filter(MediaSource.enabled == True).all()]


def _active_song_query(db: Session):
    active_ids = _active_source_ids(db)
    return db.query(Song).filter((Song.library_source_id.is_(None)) | (Song.library_source_id.in_(active_ids)))


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
    )


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
    active_ids = _active_source_ids(db)
    rows = (
        db.query(Favorite, Song)
        .join(Song, Song.id == Favorite.song_id)
        .filter((Song.library_source_id.is_(None)) | (Song.library_source_id.in_(active_ids)))
        .order_by(Favorite.created_at.desc())
        .all()
    )
    return [_song_out(song, {song.id}) for _, song in rows]


@router.get("/artists", response_model=list[ArtistOut])
def list_artists(
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    songs = _active_song_query(db).all()
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
            _active_song_query(db)
            .filter((Song.artist.is_(None)) | (Song.artist == "") | (Song.artist == "未知艺术家"))
            .order_by(Song.title.asc())
            .all()
        )
    else:
        songs = (
            _active_song_query(db)
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
    songs = _active_song_query(db).all()
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
    q = _active_song_query(db)
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
    active_ids = set(_active_source_ids(db))
    rows = (
        db.query(PlayHistory)
        .join(Song, Song.id == PlayHistory.song_id)
        .filter((Song.library_source_id.is_(None)) | (Song.library_source_id.in_(active_ids)))
        .order_by(PlayHistory.played_at.desc())
        .limit(limit)
        .all()
    )
    song_ids = [r.song_id for r in rows]
    songs = _active_song_query(db).filter(Song.id.in_(song_ids)).all() if song_ids else []
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
    songs = _active_song_query(db).all()
    artists = {(s.artist or "未知艺术家").strip() or "未知艺术家" for s in songs}
    albums = {
        ((s.album or "未知专辑").strip() or "未知专辑", (s.artist or "").strip())
        for s in songs
    }
    fav_count = db.query(func.count(Favorite.id)).join(Song, Song.id == Favorite.song_id).filter((Song.library_source_id.is_(None)) | (Song.library_source_id.in_(_active_source_ids(db)))).scalar() or 0
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
            "song_count": db.query(Song).filter(Song.library_source_id == src.id).count(),
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


from pydantic import BaseModel, Field


class ScrapeCandidateRequest(BaseModel):
    source: str = "auto"  # auto / netease / migu / qq
    keyword: str | None = Field(default=None, max_length=500)
    limit: int = Field(8, ge=1, le=30)


class ApplyScrapeCandidateRequest(BaseModel):
    candidate: dict
    write_file_tags: bool = True


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
    return {"query": {"title": score_title, "artist": score_artist, "duration": duration, "keyword": keyword}, "candidates": candidates[:limit]}


def _write_lrc_for_song(db: Session, song: Song, lyrics: str | None) -> tuple[str | None, SongFile | None]:
    if not lyrics:
        return None, None
    song_file = _local_song_file(db, song)
    dest = Path(song_file.local_path).with_suffix(".lrc") if song_file else Path("/tmp/sonpick_lyrics") / f"song_{song.id}.lrc"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(str(lyrics).strip(), encoding="utf-8")
    if song_file:
        song_file.lrc_path = str(dest)
    return str(dest), song_file


def _download_candidate_cover(db: Session, song: Song, cover_url: str | None) -> tuple[dict, SongFile | None]:
    song_file = _local_song_file(db, song)
    dest = Path(song_file.local_path).parent / "cover.jpg" if song_file else Path("/tmp/sonpick_covers") / f"song_{song.id}.jpg"
    return download_cover_with_diagnostics(cover_url, dest, timeout=20), song_file


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
        "db": {"title": song.title, "artist": song.artist, "album": song.album, "duration": song.duration, "cover_path": song.cover_path, "lrc_path": song.lrc_path},
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
    cand = body.candidate or {}
    changes = {}
    for key in ("title", "artist", "album", "duration"):
        val = cand.get(key)
        if val not in (None, "") and str(getattr(song, key, "") or "") != str(val):
            setattr(song, key, val)
            changes[key] = val
    cover_url = cand.get("cover_url")
    cover_lookup = None
    candidate_source = str(cand.get("source") or "").lower()
    if not cover_url and candidate_source == "netease":
        from app.services.scrape.providers.netease_http import fetch_netease_song_cover

        cover_lookup = fetch_netease_song_cover(cand.get("id"))
        if cover_lookup.get("cover_url"):
            cover_url = cover_lookup["cover_url"]
            cand["cover_url"] = cover_url
            cand["cover_source"] = cover_lookup.get("source")
    if not cover_url:
        version_paths = [
            value
            for file in db.query(SongFile).filter(SongFile.song_id == song.id).all()
            for value in (file.webdav_path, file.lrc_path, file.local_path)
        ]
        for value in (cand.get("id"), *version_paths, song.title):
            mid = extract_qq_songmid(value)
            if mid:
                cover_lookup = qq_song_detail_cover(mid)
                if cover_lookup.get("cover_url"):
                    cover_url = cover_lookup["cover_url"]
                    cand["cover_url"] = cover_url
                    cand["cover_source"] = cover_lookup.get("source")
                    break
    cover_result, cover_file = _download_candidate_cover(db, song, cover_url)
    if cover_lookup:
        cover_result["lookup"] = cover_lookup
    cover_path = cover_result.get("path") if cover_result.get("ok") else None
    if cover_path:
        if cover_file:
            cover_file.cover_path = cover_path
        song.cover_path = cover_path
        changes["cover_path"] = cover_path
    lyrics = cand.get("lyrics")
    lrc_path, lrc_file = _write_lrc_for_song(db, song, lyrics)
    if lrc_path:
        if lrc_file:
            lrc_file.lrc_path = lrc_path
        song.lrc_path = lrc_path
        changes["lrc_path"] = lrc_path
    song.meta_provider = cand.get("provider") or cand.get("source") or "manual"
    song.meta_confidence = int(min(100, max(0, float(cand.get("score") or 0) * 20))) if cand.get("score") is not None else song.meta_confidence
    song.scrape_status = "done"
    song.updated_at = datetime.now(timezone.utc)
    db.add(song)
    db.commit()
    db.refresh(song)

    tag_written = {}
    song_file = _local_song_file(db, song)
    if body.write_file_tags and song_file:
        tag_written = write_audio_tags(
            song_file.local_path,
            title=song.title,
            artist=song.artist,
            album=song.album,
            lyrics=lyrics,
            cover_path=cover_path or song_file.cover_path or song.cover_path,
        )
    fav = _favorite_ids(db, [song.id])
    return {"ok": True, "changes": changes, "cover_result": cover_result, "file_tags": tag_written, "song": _song_out(song, fav).model_dump()}


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

