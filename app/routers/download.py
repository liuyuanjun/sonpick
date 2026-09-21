from datetime import datetime, timezone
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Song, SongFile, Task
from app.routers.auth import get_current_user
from app.schemas import BatchDownloadRequest, DownloadRequest, PlaylistParseRequest, PlaylistParseOut, PlaylistTrackOut
from app.services.light_search_service import DEFAULT_DOWNLOAD_SOURCES, SOURCE_LABELS, clean_display_text
from app.services.playlist_import_service import parse_playlist
from app.services.task_worker import worker

router = APIRouter(prefix="/download", tags=["download"])

# 批量任务曲目数上限（歌单导入场景，防一次性打爆队列与平台限流）
_BATCH_ITEMS_LIMIT = 500


@router.post("/playlist/parse", response_model=PlaylistParseOut)
def playlist_parse(req: PlaylistParseRequest, user: str = Depends(get_current_user)):
    """解析歌单链接：只拉曲目元数据（每源 1~数页请求），曲目注册后供 worker 按 song_id 锁定下载。"""
    try:
        result = parse_playlist(req.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"歌单解析失败: {type(e).__name__}: {e}")
    tracks = [
        PlaylistTrackOut(
            song_id=str(song.identifier),
            song_name=clean_display_text(song.song_name),
            singers=clean_display_text(song.singers),
            album=clean_display_text(song.album),
            duration_s=getattr(song, "duration_s", None),
            duration=getattr(song, "duration", None),
        )
        for song in result["tracks"]
    ]
    return PlaylistParseOut(
        source=result["source"],
        source_label=SOURCE_LABELS.get(result["source"], result["source"]),
        playlist_id=result["playlist_id"],
        name=result["name"],
        track_count=len(tracks),
        tracks=tracks,
    )


def _validate_duplicate_decision(req: DownloadRequest, db: Session) -> None:
    """校验曲库重复决策字段；worker 执行前还会再次核对 SongFile。"""
    action = req.duplicate_action
    if not action:
        return
    if action == "replace":
        if not req.replace_song_file_id:
            raise HTTPException(status_code=422, detail="replace 需要提供 replace_song_file_id")
        sf = db.get(SongFile, req.replace_song_file_id)
        if not sf:
            raise HTTPException(status_code=422, detail="要替换的曲库版本不存在")
        if req.matched_song_id and sf.song_id != req.matched_song_id:
            raise HTTPException(status_code=422, detail="要替换的版本不属于匹配的曲库歌曲")
        if not sf.local_path:
            raise HTTPException(status_code=422, detail="远端版本暂不支持替换")
        if not Path(sf.local_path).is_file():
            raise HTTPException(status_code=422, detail="要替换的本地文件已不可访问")
    elif action == "keep_both":
        if req.matched_song_id and not db.get(Song, req.matched_song_id):
            raise HTTPException(status_code=422, detail="匹配的曲库歌曲不存在")


@router.post("")
def download(req: DownloadRequest, user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    _validate_duplicate_decision(req, db)
    if req.song_id and (not req.source or req.source == "all"):
        raise HTTPException(status_code=422, detail="锁定单曲下载需要指定具体音乐源")
    if not req.song_id and not req.keyword.strip():
        raise HTTPException(status_code=422, detail="缺少下载关键词")
    task = Task(
        type="search_download",
        status="pending",
        payload_json=json.dumps({
            "keyword": req.keyword,
            "prefer": req.prefer,
            "source": req.source,
            "song_id": req.song_id,
            "format": req.format,
            "duplicate_action": req.duplicate_action,
            "replace_song_file_id": req.replace_song_file_id,
            "matched_song_id": req.matched_song_id,
        }),
        progress_json=json.dumps({"message": "等待执行", "percent": 0}),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    worker.enqueue(task.id)
    return {"task_id": task.id}


@router.post("/batch")
def batch_download(req: BatchDownloadRequest, user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    # items 模式（歌单导入）：确切曲目 song_id 锁定，无需关键词搜索
    items = None
    if req.items:
        if len(req.items) > _BATCH_ITEMS_LIMIT:
            raise HTTPException(status_code=422, detail=f"单次最多导入 {_BATCH_ITEMS_LIMIT} 首")
        invalid = [it.source for it in req.items if it.source not in DEFAULT_DOWNLOAD_SOURCES]
        if invalid:
            raise HTTPException(status_code=422, detail=f"不支持的音乐源: {invalid[0]}")
        items = [
            {"keyword": it.keyword.strip(), "source": it.source, "song_id": str(it.song_id)}
            for it in req.items
            if str(it.song_id).strip()
        ]
        if not items:
            raise HTTPException(status_code=400, detail="曲目清单为空")
    keywords = list(dict.fromkeys(
        line.strip() for line in (req.content or "").splitlines() if line.strip()
    ))
    if not items and not keywords:
        raise HTTPException(status_code=400, detail="歌单为空，请每行填写一首歌曲")
    # source 支持逗号分隔的有序多源（按顺序优先），all 表示全部默认源
    requested = (req.source or "all").strip()
    if requested != "all":
        invalid = [s for s in requested.split(",") if s.strip() and s.strip() not in DEFAULT_DOWNLOAD_SOURCES]
        if invalid:
            raise HTTPException(status_code=422, detail=f"不支持的音乐源: {', '.join(invalid)}")
    task = Task(
        type="batch_download",
        status="pending",
        payload_json=json.dumps({
            "keywords": keywords,
            "items": items,
            "prefer": req.prefer,
            "source": req.source,
            "duplicate_action": req.duplicate_action or "skip",
        }),
        progress_json=json.dumps({"message": "等待执行", "percent": 0}),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    worker.enqueue(task.id)
    return {"task_id": task.id}
