"""歌词来源配置注册表。"""
from __future__ import annotations

import json
from typing import Any

from app.services.source_config import dump_configs, load_configs, select_configs

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
_MUTABLE_KEYS = {"enabled", "auto_enabled", "priority", "timeout"}


def _coerce(item: dict[str, Any], default: dict[str, Any]) -> None:
    item["priority"] = int(item.get("priority") or default["priority"])
    item["timeout"] = max(5, min(60, int(item.get("timeout") or default["timeout"])))


def _inherit_enabled_from_scrape(
    configs: list[dict[str, Any]], raw: str | None, scrape_raw: str | None
) -> None:
    """迁移兼容：歌词源从未单独配置时，从刮削源继承网易/咪咕的开关状态。

    这是历史遗留的一次性兼容逻辑（歌词源曾与刮削源共享开关），集中在此并标注为
    迁移 shim，不应再扩展新的跨注册表耦合。
    """
    if not scrape_raw:
        return
    try:
        stored_items = [
            item
            for item in json.loads(raw or "[]")
            if isinstance(item, dict) and item.get("id") in LYRICS_SOURCE_IDS
        ]
    except (TypeError, ValueError):
        stored_items = []
    if stored_items:
        return
    try:
        scrape_enabled = {
            str(item.get("id")): bool(item.get("enabled", True))
            for item in json.loads(scrape_raw or "[]")
            if isinstance(item, dict)
        }
    except (TypeError, ValueError):
        return
    for item in configs:
        if item["id"] in {"netease", "migu"} and item["id"] in scrape_enabled:
            item["enabled"] = scrape_enabled[item["id"]]
            item["auto_enabled"] = scrape_enabled[item["id"]]


def lyrics_source_configs(raw: str | None, *, scrape_raw: str | None = None) -> list[dict[str, Any]]:
    configs = load_configs(raw, DEFAULT_LYRICS_SOURCES, mutable_keys=_MUTABLE_KEYS, coerce=_coerce)
    _inherit_enabled_from_scrape(configs, raw, scrape_raw)
    return configs


def dump_lyrics_source_configs(configs: list[dict[str, Any]]) -> str:
    return dump_configs(configs, DEFAULT_LYRICS_SOURCES, mutable_keys=_MUTABLE_KEYS, coerce=_coerce)


def select_lyrics_source_configs(
    raw: str | None, *, automatic: bool, scrape_raw: str | None = None
) -> list[dict[str, Any]]:
    return select_configs(lyrics_source_configs(raw, scrape_raw=scrape_raw), automatic=automatic)
