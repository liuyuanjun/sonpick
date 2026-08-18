"""Configurable scrape source registry and provider factory."""
from __future__ import annotations

from typing import Any

from app.services.source_config import dump_configs, load_configs, select_configs

DEFAULT_SCRAPE_SOURCES = [
    {"id": "netease", "name": "网易云音乐", "tier": "domestic", "enabled": True, "auto_enabled": True, "priority": 10, "region": "cn"},
    {"id": "migu", "name": "咪咕音乐", "tier": "domestic", "enabled": True, "auto_enabled": True, "priority": 20, "region": "cn"},
    {"id": "qq", "name": "QQ 音乐", "tier": "domestic", "enabled": True, "auto_enabled": True, "priority": 30, "region": "cn"},
    {"id": "itunes", "name": "Apple Music（iTunes）", "tier": "overseas", "enabled": True, "auto_enabled": True, "priority": 100, "region": "hk"},
    {"id": "deezer", "name": "Deezer", "tier": "overseas", "enabled": True, "auto_enabled": True, "priority": 110, "region": "global"},
    {"id": "musicbrainz", "name": "MusicBrainz + Cover Art Archive", "tier": "overseas", "enabled": True, "auto_enabled": True, "priority": 120, "region": "global"},
    {"id": "acoustid", "name": "AcoustID（Chromaprint）", "tier": "fingerprint", "enabled": False, "auto_enabled": True, "priority": 200, "region": "global"},
]
SOURCE_IDS = {item["id"] for item in DEFAULT_SCRAPE_SOURCES}
# 所有默认字段均可被存储配置覆盖（含 name/tier/region）。
_MUTABLE_KEYS = {key for item in DEFAULT_SCRAPE_SOURCES for key in item}


def _coerce(item: dict[str, Any], default: dict[str, Any]) -> None:
    item["enabled"] = bool(item["enabled"])
    item["auto_enabled"] = bool(item["auto_enabled"])
    item["priority"] = max(1, min(int(item["priority"]), 9999))
    item["region"] = str(item["region"] or default["region"]).lower()


def source_configs(raw: str | None) -> list[dict[str, Any]]:
    return load_configs(raw, DEFAULT_SCRAPE_SOURCES, mutable_keys=_MUTABLE_KEYS, coerce=_coerce)


def dump_source_configs(configs: list[dict[str, Any]]) -> str:
    return dump_configs(configs, DEFAULT_SCRAPE_SOURCES, mutable_keys=_MUTABLE_KEYS, coerce=_coerce)


def select_source_configs(raw: str | None, *, automatic: bool) -> list[dict[str, Any]]:
    return select_configs(source_configs(raw), automatic=automatic)
