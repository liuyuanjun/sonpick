import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import AppSettings
from app.schemas import SettingsResponse, SettingsUpdate, decrypt_text, encrypt_text
from app.routers.auth import get_current_user

router = APIRouter(prefix="/settings", tags=["settings"])


DEFAULT_SCAN_EXCLUDE = [
    "**/.*",
    "**/.@*",
    "**/@eaDir/**",
    "**/#recycle/**",
    "**/Thumbs.db",
    "**/*.tmp",
]
DEFAULT_SCAN_EXTS = "mp3,flac,m4a,wav,ogg,aac,ape,wma"


def _parse_json_list(raw, default):
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
    # multiline / comma separated fallback
    parts = []
    for line in str(raw).replace(",", "\n").splitlines():
        s = line.strip()
        if s:
            parts.append(s)
    return parts or list(default)


def _dump_json_list(items):
    clean = []
    for x in items or []:
        s = str(x).strip()
        # keep empty string (WebDAV root)
        if s not in clean:
            clean.append(s)
    return json.dumps(clean, ensure_ascii=False)



def _ensure_settings(db: Session) -> AppSettings:
    s = db.get(AppSettings, 1)
    if not s:
        cfg = get_settings()
        s = AppSettings(
            id=1,
            storage_path=cfg.storage_path,
            prefer_format="any",
            auto_convert_mp3=False,
            auto_upload_webdav=False,
            webdav_delete_local_after_upload=False,
            webdav_upload_sidecar=True,
            webdav_conflict_policy="rename",
            webdav_remote_dir="",
            scan_local_enabled=True,
            scan_local_dirs="[]",
            scan_webdav_enabled=True,
            scan_webdav_dirs='[""]',
            scan_exclude_globs=json.dumps(DEFAULT_SCAN_EXCLUDE, ensure_ascii=False),
            scan_audio_exts=DEFAULT_SCAN_EXTS,
        )
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


def _to_response(s: AppSettings) -> SettingsResponse:
    return SettingsResponse(
        storage_path=s.storage_path,
        webdav_url=s.webdav_url,
        webdav_username=s.webdav_username,
        webdav_password=decrypt_text(s.webdav_password_enc) or "",
        prefer_format=s.prefer_format or "any",
        auto_convert_mp3=bool(s.auto_convert_mp3),
        auto_upload_webdav=bool(s.auto_upload_webdav),
        webdav_delete_local_after_upload=bool(getattr(s, "webdav_delete_local_after_upload", False)),
        webdav_upload_sidecar=bool(getattr(s, "webdav_upload_sidecar", True)),
        webdav_conflict_policy=getattr(s, "webdav_conflict_policy", None) or "rename",
        webdav_remote_dir=getattr(s, "webdav_remote_dir", None) or "",
        scan_local_enabled=bool(getattr(s, "scan_local_enabled", True)),
        scan_local_dirs=_parse_json_list(getattr(s, "scan_local_dirs", None), []),
        scan_webdav_enabled=bool(getattr(s, "scan_webdav_enabled", True)),
        scan_webdav_dirs=_parse_json_list(getattr(s, "scan_webdav_dirs", None), [""]),
        scan_exclude_globs=_parse_json_list(getattr(s, "scan_exclude_globs", None), DEFAULT_SCAN_EXCLUDE),
        scan_audio_exts=getattr(s, "scan_audio_exts", None) or DEFAULT_SCAN_EXTS,
        updated_at=s.updated_at.isoformat() if s.updated_at else None,
    )


@router.get("", response_model=SettingsResponse)
def get_settings_api(user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    s = _ensure_settings(db)
    return _to_response(s)


@router.put("", response_model=SettingsResponse)
def update_settings(req: SettingsUpdate, user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    s = _ensure_settings(db)

    if req.storage_path is not None:
        p = Path(req.storage_path)
        try:
            p.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"无法创建存储路径: {e}")
        s.storage_path = str(p)

    if req.webdav_url is not None:
        s.webdav_url = req.webdav_url.strip() or None
    if req.webdav_username is not None:
        s.webdav_username = req.webdav_username
    if req.webdav_password is not None:
        # 空字符串表示不修改已有密码
        if req.webdav_password != "":
            s.webdav_password_enc = encrypt_text(req.webdav_password)
    if req.prefer_format is not None:
        s.prefer_format = req.prefer_format
    if req.auto_convert_mp3 is not None:
        s.auto_convert_mp3 = req.auto_convert_mp3
    if req.auto_upload_webdav is not None:
        s.auto_upload_webdav = req.auto_upload_webdav
    if req.webdav_delete_local_after_upload is not None:
        s.webdav_delete_local_after_upload = req.webdav_delete_local_after_upload
    if req.webdav_upload_sidecar is not None:
        s.webdav_upload_sidecar = req.webdav_upload_sidecar
    if req.webdav_conflict_policy is not None:
        s.webdav_conflict_policy = req.webdav_conflict_policy
    if req.webdav_remote_dir is not None:
        s.webdav_remote_dir = req.webdav_remote_dir.strip()
    if req.scan_local_enabled is not None:
        s.scan_local_enabled = req.scan_local_enabled
    if req.scan_local_dirs is not None:
        s.scan_local_dirs = _dump_json_list(req.scan_local_dirs)
    if req.scan_webdav_enabled is not None:
        s.scan_webdav_enabled = req.scan_webdav_enabled
    if req.scan_webdav_dirs is not None:
        s.scan_webdav_dirs = _dump_json_list(req.scan_webdav_dirs)
    if req.scan_exclude_globs is not None:
        s.scan_exclude_globs = _dump_json_list(req.scan_exclude_globs)
    if req.scan_audio_exts is not None:
        s.scan_audio_exts = (req.scan_audio_exts or DEFAULT_SCAN_EXTS).strip()

    s.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(s)
    return _to_response(s)
