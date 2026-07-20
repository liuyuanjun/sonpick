"""Configurable scrape source registry and provider factory."""
from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

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


def source_configs(raw: str | None) -> list[dict[str, Any]]:
    stored: dict[str, dict[str, Any]] = {}
    try:
        for item in json.loads(raw or "[]"):
            if isinstance(item, dict) and item.get("id") in SOURCE_IDS:
                stored[str(item["id"])] = item
    except (TypeError, ValueError):
        pass
    configs: list[dict[str, Any]] = []
    for default in DEFAULT_SCRAPE_SOURCES:
        item = deepcopy(default)
        item.update({key: value for key, value in stored.get(default["id"], {}).items() if key in item})
        item["enabled"] = bool(item["enabled"])
        item["auto_enabled"] = bool(item["auto_enabled"])
        item["priority"] = max(1, min(int(item["priority"]), 9999))
        item["region"] = str(item["region"] or default["region"]).lower()
        configs.append(item)
    return sorted(configs, key=lambda item: (item["priority"], item["id"]))


def dump_source_configs(configs: list[dict[str, Any]]) -> str:
    allowed = {item["id"]: item for item in configs if item.get("id") in SOURCE_IDS}
    defaults = {item["id"]: item for item in DEFAULT_SCRAPE_SOURCES}
    merged = []
    for source_id, default in defaults.items():
        item = deepcopy(default)
        item.update({key: value for key, value in allowed.get(source_id, {}).items() if key in item})
        merged.append(item)
    return json.dumps(source_configs(json.dumps(merged, ensure_ascii=False)), ensure_ascii=False)


def select_source_configs(raw: str | None, *, automatic: bool) -> list[dict[str, Any]]:
    return [item for item in source_configs(raw) if item["enabled"] and (item["auto_enabled"] if automatic else True)]
