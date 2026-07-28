"""歌词来源配置注册表。"""
from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

DEFAULT_LYRICS_SOURCES = [
    {
        "id": "lrclib",
        "name": "LRCLIB",
        "enabled": True,
        "auto_enabled": True,
        "priority": 10,
        "timeout": 18,
        "capabilities": ["synced", "plain", "instrumental"],
        "description": "无需 API Key；公共服务；后端串行节流；优先同步歌词。",
    },
    {
        "id": "netease",
        "name": "网易云音乐",
        "enabled": True,
        "auto_enabled": True,
        "priority": 20,
        "timeout": 15,
        "capabilities": ["synced", "plain"],
        "description": "先搜索歌曲，再按歌曲 ID 获取歌词。",
    },
    {
        "id": "migu",
        "name": "咪咕音乐",
        "enabled": True,
        "auto_enabled": True,
        "priority": 30,
        "timeout": 15,
        "capabilities": ["synced", "plain"],
        "description": "先搜索歌曲，再按版权 ID 获取歌词。",
    },
]
LYRICS_SOURCE_IDS = {item["id"] for item in DEFAULT_LYRICS_SOURCES}


def lyrics_source_configs(raw: str | None, *, scrape_raw: str | None = None) -> list[dict[str, Any]]:
    stored: dict[str, dict[str, Any]] = {}
    try:
        for item in json.loads(raw or "[]"):
            if isinstance(item, dict) and item.get("id") in LYRICS_SOURCE_IDS:
                stored[str(item["id"])] = item
    except (TypeError, ValueError):
        pass

    scrape_enabled: dict[str, bool] = {}
    if not stored and scrape_raw:
        try:
            scrape_enabled = {
                str(item.get("id")): bool(item.get("enabled", True))
                for item in json.loads(scrape_raw or "[]")
                if isinstance(item, dict)
            }
        except (TypeError, ValueError):
            scrape_enabled = {}

    configs = []
    for default in DEFAULT_LYRICS_SOURCES:
        item = deepcopy(default)
        saved = stored.get(default["id"], {})
        for key in ("enabled", "auto_enabled", "priority", "timeout"):
            if key in saved:
                item[key] = saved[key]
        if not stored and default["id"] in {"netease", "migu"} and default["id"] in scrape_enabled:
            item["enabled"] = scrape_enabled[default["id"]]
            item["auto_enabled"] = scrape_enabled[default["id"]]
        item["priority"] = int(item.get("priority") or default["priority"])
        item["timeout"] = max(5, min(60, int(item.get("timeout") or default["timeout"])))
        configs.append(item)
    return sorted(configs, key=lambda item: (item["priority"], item["id"]))


def dump_lyrics_source_configs(configs: list[dict[str, Any]]) -> str:
    allowed = {item["id"]: item for item in configs if item.get("id") in LYRICS_SOURCE_IDS}
    merged = []
    for default in DEFAULT_LYRICS_SOURCES:
        item = deepcopy(default)
        saved = allowed.get(default["id"], {})
        for key in ("enabled", "auto_enabled", "priority", "timeout"):
            if key in saved:
                item[key] = saved[key]
        merged.append(item)
    return json.dumps(lyrics_source_configs(json.dumps(merged, ensure_ascii=False)), ensure_ascii=False)


def select_lyrics_source_configs(raw: str | None, *, automatic: bool, scrape_raw: str | None = None) -> list[dict[str, Any]]:
    return [
        item
        for item in lyrics_source_configs(raw, scrape_raw=scrape_raw)
        if item["enabled"] and (item["auto_enabled"] if automatic else True)
    ]
