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
from app.services.scrape.source_registry import SOURCE_IDS, select_source_configs, source_configs

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
            mp3_output_path=str(Path(cfg.storage_path) / "MP3"),
            lossless_output_path=str(Path(cfg.storage_path) / "LOSSLESS"),
            lossless_preferred=False,
            auto_convert_when_lossless_not_preferred=False,
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
    from app.services.scrape.providers.acoustid import fingerprint_status
    from app.services.scrape.source_registry import source_configs

    acoustid_key = decrypt_text(getattr(s, "acoustid_api_key_enc", None))
    acoustid = fingerprint_status(acoustid_key)
    sources = source_configs(getattr(s, "scrape_sources_json", None))
    for source in sources:
        if source["id"] == "acoustid":
            source["available"] = acoustid["available"]
            source["status_message"] = acoustid["message"]
    return SettingsResponse(
        storage_path=s.storage_path,
        webdav_url=s.webdav_url,
        webdav_username=s.webdav_username,
        webdav_password=decrypt_text(s.webdav_password_enc) or "",
        prefer_format=s.prefer_format or "any",
        mp3_output_path=getattr(s, "mp3_output_path", None) or str(Path(s.storage_path) / "MP3"),
        lossless_output_path=getattr(s, "lossless_output_path", None) or str(Path(s.storage_path) / "LOSSLESS"),
        lossless_preferred=bool(getattr(s, "lossless_preferred", False)),
        auto_convert_when_lossless_not_preferred=bool(getattr(s, "auto_convert_when_lossless_not_preferred", False)),
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
        scrape_sources=sources,
        acoustid_ready=acoustid["available"],
        acoustid_message=acoustid["message"],
        updated_at=s.updated_at.isoformat() if s.updated_at else None,
    )


@router.post("/scrape-sources/{source_id}/test")
def test_scrape_source(source_id: str, keyword: str = "周杰伦", user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    if source_id not in SOURCE_IDS:
        raise HTTPException(status_code=404, detail="未知刮削源")
    settings = _ensure_settings(db)
    config = next((item for item in source_configs(settings.scrape_sources_json) if item["id"] == source_id), None)
    if not config or not config["enabled"]:
        raise HTTPException(status_code=400, detail="请先启用该刮削源")
    from app.services.scrape.base import ScrapeQuery
    from app.services.scrape.providers.acoustid import fingerprint_status
    from app.services.scrape.providers.deezer import DeezerProvider
    from app.services.scrape.providers.http_sources import MiguProvider, NetEaseProvider
    from app.services.scrape.providers.itunes import ITunesProvider
    from app.services.scrape.providers.musicbrainz import MusicBrainzProvider
    from app.services.scrape.providers.smart_cn_provider import SmartCNProvider

    if source_id == "acoustid":
        return fingerprint_status(decrypt_text(settings.acoustid_api_key_enc))
    provider_map = {
        "netease": NetEaseProvider(), "migu": MiguProvider(), "qq": SmartCNProvider(db=db, enable_qq=True),
        "itunes": ITunesProvider(country=config["region"]), "deezer": DeezerProvider(), "musicbrainz": MusicBrainzProvider(),
    }
    hit = provider_map[source_id].lookup(ScrapeQuery(title=keyword), timeout=15)
    return {"ok": bool(hit), "message": "连接正常" if hit else "未得到候选，请更换关键词或稍后重试", "result": hit.raw if hit else None}


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
    if req.mp3_output_path:
        # 空串/None 表示不修改；默认值由 _to_response 回退提供
        s.mp3_output_path = req.mp3_output_path.strip()
    if req.lossless_output_path:
        s.lossless_output_path = req.lossless_output_path.strip()
    if req.lossless_preferred is not None:
        s.lossless_preferred = req.lossless_preferred
    if req.auto_convert_when_lossless_not_preferred is not None:
        s.auto_convert_when_lossless_not_preferred = req.auto_convert_when_lossless_not_preferred
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
    if req.scrape_sources is not None:
        from app.services.scrape.source_registry import dump_source_configs

        s.scrape_sources_json = dump_source_configs(req.scrape_sources)
    if req.acoustid_api_key is not None and req.acoustid_api_key != "":
        s.acoustid_api_key_enc = encrypt_text(req.acoustid_api_key.strip())

    s.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(s)
    return _to_response(s)
