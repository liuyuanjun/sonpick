"""源配置注册表的公共基元（刮削源 / 歌词源共用）。

两者的字段 schema 不同（刮削有 ``tier``/``region``，歌词有 ``timeout``/``capabilities``），
但"解析存储 → 合并进默认 → 按 (priority, id) 排序" 的核心逻辑一致。这里收口为通用
函数，各自注册表只保留默认值、可变字段集合与类型专属的字段约束（``coerce``）。
"""
from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Callable, Optional


def _parse_stored(raw: str | None, ids: set[str]) -> dict[str, dict[str, Any]]:
    stored: dict[str, dict[str, Any]] = {}
    try:
        for item in json.loads(raw or "[]"):
            if isinstance(item, dict) and item.get("id") in ids:
                stored[str(item["id"])] = item
    except (TypeError, ValueError):
        pass
    return stored


def load_configs(
    raw: str | None,
    defaults: list[dict[str, Any]],
    *,
    mutable_keys: set[str],
    coerce: Optional[Callable[[dict[str, Any], dict[str, Any]], None]] = None,
) -> list[dict[str, Any]]:
    """解析存储 JSON，合并进默认配置，经 ``coerce`` 归一后按 (priority, id) 排序。"""
    ids = {d["id"] for d in defaults}
    stored = _parse_stored(raw, ids)
    configs: list[dict[str, Any]] = []
    for default in defaults:
        item = deepcopy(default)
        saved = stored.get(default["id"], {})
        for key in mutable_keys:
            if key in saved:
                item[key] = saved[key]
        if coerce is not None:
            coerce(item, default)
        configs.append(item)
    return sorted(configs, key=lambda c: (c.get("priority"), c.get("id")))


def dump_configs(
    configs: list[dict[str, Any]],
    defaults: list[dict[str, Any]],
    *,
    mutable_keys: set[str],
    coerce: Optional[Callable[[dict[str, Any], dict[str, Any]], None]] = None,
) -> str:
    """把（可能被前端改过的）configs 合并回默认，归一后序列化为存储 JSON。"""
    ids = {d["id"] for d in defaults}
    allowed = {item["id"]: item for item in configs if item.get("id") in ids}
    merged: list[dict[str, Any]] = []
    for default in defaults:
        item = deepcopy(default)
        saved = allowed.get(default["id"], {})
        for key in mutable_keys:
            if key in saved:
                item[key] = saved[key]
        merged.append(item)
    return json.dumps(
        load_configs(json.dumps(merged, ensure_ascii=False), defaults, mutable_keys=mutable_keys, coerce=coerce),
        ensure_ascii=False,
    )


def select_configs(configs: list[dict[str, Any]], *, automatic: bool) -> list[dict[str, Any]]:
    return [item for item in configs if item["enabled"] and (item["auto_enabled"] if automatic else True)]
