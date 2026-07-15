from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import MediaSource, Song
from app.routers.auth import get_current_user
from app.schemas import SourceCreate, SourceOut, SourceUpdate, encrypt_text, decrypt_text
from app.services.library_scan_service import LibraryScanService
from app.services.library_organize_service import LibraryOrganizeService
from app.services.webdav_service import WebDAVService

router = APIRouter(prefix="/sources", tags=["sources"])

DEFAULT_LOCAL_ROOT = "/app/downloads"


def _norm_path(value: str | None) -> str:
    return str(value or "").rstrip("/") or ""


def _is_builtin_local_source(source: MediaSource) -> bool:
    return source.type == "local" and _norm_path(source.root_path) == DEFAULT_LOCAL_ROOT



def _parse_json_list(raw: Any, default: list) -> list:
    if raw is None or raw == "":
        return list(default)
    if isinstance(raw, list):
        return [str(x) for x in raw]
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x) for x in data]
    except Exception:
        pass
    parts = []
    for line in str(raw).replace(",", "\n").splitlines():
        s = line.strip()
        if s:
            parts.append(s)
    return parts or list(default)


def _dump_json_list(items: Optional[list]) -> str:
    clean = []
    for x in items or []:
        s = str(x).strip()
        if s not in clean:
            clean.append(s)
    return json.dumps(clean, ensure_ascii=False)


def _source_out(source: MediaSource) -> dict:
    d = source.to_dict()
    locked = _is_builtin_local_source(source)
    d["is_builtin"] = locked
    d["locked_fields"] = ["name", "root_path"] if locked else []
    d["deletable"] = not locked
    # SourceOut 不返回 password；编辑时通过单独请求或重新输入更新
    d.pop("webdav_password", None)
    return d


@router.get("", response_model=list[SourceOut])
def list_sources(user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    sources = db.query(MediaSource).order_by(MediaSource.id.asc()).all()
    return [_source_out(s) for s in sources]


@router.post("", response_model=SourceOut)
def create_source(req: SourceCreate, user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    if req.type == "webdav" and req.is_default_upload:
        db.query(MediaSource).filter(MediaSource.is_default_upload == True).update({"is_default_upload": False})

    source = MediaSource(
        name=req.name,
        type=req.type,
        enabled=req.enabled,
        root_path=req.root_path,
        scan_dirs=_dump_json_list(req.scan_dirs),
        webdav_url=req.webdav_url,
        webdav_username=req.webdav_username,
        webdav_password_enc=encrypt_text(req.webdav_password) if req.webdav_password else None,
        remote_dir=req.remote_dir or "",
        scan_remote_dirs=_dump_json_list(req.scan_remote_dirs) if req.scan_remote_dirs is not None else '[""]',
        exclude_globs=_dump_json_list(req.exclude_globs) if req.exclude_globs is not None else None,
        audio_exts=req.audio_exts,
        is_default_upload=req.is_default_upload,
        upload_sidecar=req.upload_sidecar if req.upload_sidecar is not None else True,
        conflict_policy=req.conflict_policy or "rename",
        delete_local_after_upload=req.delete_local_after_upload if req.delete_local_after_upload is not None else False,
        connection_status="unknown",
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return _source_out(source)


@router.get("/{source_id}", response_model=SourceOut)
def get_source(source_id: int, user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    source = db.get(MediaSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="源不存在")
    return _source_out(source)


@router.get("/{source_id}/browse")
def browse_source(
    source_id: int,
    path: str = Query(""),
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    source = db.get(MediaSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="源不存在")
    if source.type != "local":
        raise HTTPException(status_code=400, detail="仅本地曲库支持此浏览接口")
    if not source.root_path:
        raise HTTPException(status_code=400, detail="本地曲库根目录未配置")

    root = Path(source.root_path).expanduser().resolve()
    rel = str(path or "").replace("\\", "/").strip("/")
    target = (root / rel).resolve() if rel else root
    try:
        target.relative_to(root)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="路径超出曲库根目录") from e
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="目录不存在")

    allowed_exts = {".mp3", ".flac", ".m4a", ".wav", ".ogg", ".aac", ".ape", ".wma", ".opus", ".lrc", ".jpg", ".jpeg", ".png", ".webp"}
    items = []
    try:
        entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError as e:
        raise HTTPException(status_code=400, detail=f"读取目录失败: {e}") from e

    for entry in entries:
        name = entry.name
        if name.startswith("."):
            continue
        is_dir = entry.is_dir()
        if not is_dir and entry.suffix.lower() not in allowed_exts:
            continue
        try:
            entry_rel = entry.resolve().relative_to(root).as_posix()
        except ValueError:
            continue
        stat = entry.stat()
        items.append({
            "name": name,
            "path": entry_rel,
            "type": "dir" if is_dir else "file",
            "is_dir": is_dir,
            "size": 0 if is_dir else stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        })
    return {"path": rel, "items": items}


@router.put("/{source_id}", response_model=SourceOut)
def update_source(
    source_id: int,
    req: SourceUpdate,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    source = db.get(MediaSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="源不存在")

    locked = _is_builtin_local_source(source)
    if req.name is not None:
        if locked and req.name != source.name:
            raise HTTPException(status_code=400, detail="内置本地曲库名称不可修改")
        source.name = req.name
    if req.enabled is not None:
        source.enabled = req.enabled
    if req.root_path is not None:
        if locked and _norm_path(req.root_path) != DEFAULT_LOCAL_ROOT:
            raise HTTPException(status_code=400, detail="内置本地曲库路径不可修改")
        source.root_path = req.root_path
    if req.scan_dirs is not None:
        source.scan_dirs = _dump_json_list(req.scan_dirs)
    if req.webdav_url is not None:
        source.webdav_url = req.webdav_url.strip() or None
    if req.webdav_username is not None:
        source.webdav_username = req.webdav_username
    if req.webdav_password is not None and req.webdav_password != "":
        source.webdav_password_enc = encrypt_text(req.webdav_password)
    if req.remote_dir is not None:
        source.remote_dir = req.remote_dir.strip()
    if req.scan_remote_dirs is not None:
        source.scan_remote_dirs = _dump_json_list(req.scan_remote_dirs)
    if req.exclude_globs is not None:
        source.exclude_globs = _dump_json_list(req.exclude_globs)
    if req.audio_exts is not None:
        source.audio_exts = req.audio_exts.strip()
    if req.is_default_upload is not None and source.type == "webdav":
        if req.is_default_upload:
            db.query(MediaSource).filter(MediaSource.is_default_upload == True).update({"is_default_upload": False})
        source.is_default_upload = req.is_default_upload
    if req.upload_sidecar is not None:
        source.upload_sidecar = req.upload_sidecar
    if req.conflict_policy is not None:
        source.conflict_policy = req.conflict_policy
    if req.delete_local_after_upload is not None:
        source.delete_local_after_upload = req.delete_local_after_upload

    source.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(source)
    return _source_out(source)


@router.delete("/{source_id}")
def delete_source(source_id: int, user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    source = db.get(MediaSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="源不存在")
    if _is_builtin_local_source(source):
        raise HTTPException(status_code=400, detail="内置本地曲库不可删除")

    # 解除歌曲关联
    db.query(Song).filter(Song.library_source_id == source_id).update({"library_source_id": None})

    # 若删除的是默认上传源，清标记（查询已不存在，直接清除）
    if source.is_default_upload:
        db.query(MediaSource).filter(MediaSource.is_default_upload == True).update({"is_default_upload": False})

    db.delete(source)
    db.commit()
    return {"ok": True}


@router.post("/{source_id}/test")
def test_source(source_id: int, user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    source = db.get(MediaSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="源不存在")

    source.last_checked_at = datetime.now(timezone.utc)
    try:
        if source.type == "local":
            root = (source.root_path or "").strip()
            if not root:
                source.connection_status = "not_configured"
                source.connection_message = "未配置本地根目录"
            else:
                p = Path(root).expanduser()
                if not p.exists():
                    source.connection_status = "failed"
                    source.connection_message = f"目录不存在: {root}"
                elif not p.is_dir():
                    source.connection_status = "failed"
                    source.connection_message = f"路径不是目录: {root}"
                elif not p.is_readable():
                    source.connection_status = "failed"
                    source.connection_message = f"目录不可读: {root}"
                else:
                    source.connection_status = "ok"
                    source.connection_message = f"目录可读: {root}"
        elif source.type == "webdav":
            if not (source.webdav_url or "").strip():
                source.connection_status = "not_configured"
                source.connection_message = "未配置 WebDAV 地址"
            else:
                ws = WebDAVService(db=db, source_id=source.id)
                ws.list()
                source.connection_status = "ok"
                source.connection_message = "WebDAV 连接成功"
        else:
            source.connection_status = "failed"
            source.connection_message = "未知源类型"
    except Exception as e:
        source.connection_status = "failed"
        source.connection_message = str(e)[:500]

    db.commit()
    db.refresh(source)
    return _source_out(source)


@router.post("/{source_id}/set-default-upload")
def set_default_upload(
    source_id: int,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    source = db.get(MediaSource, source_id)
    if not source or source.type != "webdav":
        raise HTTPException(status_code=404, detail="仅 WebDAV 源可设为默认上传目标")

    db.query(MediaSource).filter(MediaSource.is_default_upload == True).update({"is_default_upload": False})
    source.is_default_upload = True
    source.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(source)
    return _source_out(source)


@router.post("/{source_id}/scan")
def scan_source(
    source_id: int,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """快捷扫描单个源。"""
    source = db.get(MediaSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="源不存在")
    if not source.enabled:
        raise HTTPException(status_code=400, detail="源已禁用")

    result = LibraryScanService(db).scan(source_ids=[source_id])
    return result


class ReorganizeRequest(BaseModel):
    limit: int = Field(20, ge=0, description="最大整理数量；0 表示不限制")
    relative_dir: str = Field("", description="相对源根的子目录，空=整源")
    include_failed: bool = Field(False, description="是否包含 _failed 目录")
    allow_network: bool = Field(False, description="预览/整理时是否联网补专辑；默认关")


class ScrapeRequest(BaseModel):
    allow_network: bool = True
    overwrite: bool = False
    write_file_tags: bool = True
    limit: int = Field(20, ge=0)
    song_ids: list[int] | None = None
    async_mode: bool = True


@router.get("/{source_id}/reorganize/dirs")
def reorganize_dirs(
    source_id: int,
    path: str = "",
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """列出整理可选子目录（一层）。"""
    source = db.get(MediaSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="源不存在")
    try:
        return LibraryOrganizeService(db).list_reorganize_dirs(source_id, relative_dir=path or "")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"列目录失败: {type(e).__name__}: {e}",
        ) from e


@router.post("/{source_id}/reorganize/preview")
def reorganize_preview(
    source_id: int,
    body: ReorganizeRequest | None = None,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """预览整理计划（不改文件）。"""
    source = db.get(MediaSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="源不存在")
    body = body or ReorganizeRequest()
    try:
        return LibraryOrganizeService(db).preview_reorganize(
            source_id,
            limit=body.limit,
            relative_dir=body.relative_dir or "",
            include_failed=bool(body.include_failed),
            allow_network=bool(body.allow_network),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"整理预览失败: {type(e).__name__}: {e}",
        ) from e


@router.post("/{source_id}/reorganize/apply")
def reorganize_apply(
    source_id: int,
    body: ReorganizeRequest | None = None,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """应用整理：按艺术家/专辑落盘；失败文件进 _failed/。"""
    source = db.get(MediaSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="源不存在")
    body = body or ReorganizeRequest()
    try:
        return LibraryOrganizeService(db).apply_reorganize(
            source_id,
            limit=body.limit,
            relative_dir=body.relative_dir or "",
            include_failed=bool(body.include_failed),
            allow_network=bool(body.allow_network),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"整理失败: {type(e).__name__}: {e}",
        ) from e


@router.post("/{source_id}/scrape")
def scrape_source(
    source_id: int,
    body: ScrapeRequest | None = None,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """刮削并补全该源歌曲元数据（默认异步任务）。"""
    import json
    from datetime import datetime, timezone

    from app.models import Task
    from app.services.task_worker import worker

    source = db.get(MediaSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="源不存在")
    body = body or ScrapeRequest()
    payload = {
        "source_id": source_id,
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
        return {
            "async": True,
            "task_id": task.id,
            "status": task.status,
            "message": "刮削任务已创建",
            "payload": payload,
        }
    try:
        from app.services.scrape.job import run_scrape_job

        return run_scrape_job(db, **payload)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"刮削失败: {type(e).__name__}: {e}",
        ) from e

