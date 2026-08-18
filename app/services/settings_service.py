"""Settings 获取 / 播种与扫描常量（跨路由与服务共享）。

把原本散落在 ``routers/settings.py``、``routers/sources.py``、``database.py`` 的
``_ensure_settings`` / ``_parse_json_list`` / ``_dump_json_list`` / 扫描默认值收口到
服务层，消灭 service / database → router 的反向 import。

``parse_json_list`` / ``dump_json_list`` 是 JSON 列表的读写助手；``ensure_settings``
确保单行 ``AppSettings(id=1)`` 存在并返回。扫描默认值与 ``constants.AUDIO_EXTS``
（运行时扩展名集合）语义不同：这里是用户可配置的 ``scan_audio_exts`` 字符串默认值。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AppSettings

DEFAULT_SCAN_EXCLUDE = [
    "**/.*",
    "**/.@*",
    "**/@eaDir/**",
    "**/#recycle/**",
    "**/Thumbs.db",
    "**/*.tmp",
]
DEFAULT_SCAN_EXTS = "mp3,flac,m4a,wav,ogg,aac,ape,wma"


def parse_json_list(raw: Any, default: list) -> list:
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


def dump_json_list(items: Optional[list]) -> str:
    clean = []
    for x in items or []:
        s = str(x).strip()
        # keep empty string (WebDAV root)
        if s not in clean:
            clean.append(s)
    return json.dumps(clean, ensure_ascii=False)


def ensure_settings(db: Session) -> AppSettings:
    s = db.get(AppSettings, 1)
    if not s:
        cfg = get_settings()
        s = AppSettings(
            id=1,
            storage_path=cfg.storage_path,
            prefer_format="any",
            auto_convert_mp3=False,
            lossy_output_path=str(Path(cfg.storage_path) / "LOSSY"),
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
