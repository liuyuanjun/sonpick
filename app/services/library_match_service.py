"""搜索结果与本地曲库（Song + SongFile）的批量比对。

设计要点：
- 一次查询载入全部 Song 摘要，在内存中建索引后逐条比对，避免 N+1；
- 只对命中的 Song 查询 SongFile，版本大小优先读数据库持久化字段，
  缺失时仅对命中的本地文件 stat，绝不遍历下载目录；
- 匹配分三级：
    high   平台曲目 ID 与库内 Song.source_id 一致 -> exists
    medium 规范化 artist+title+album 一致，duration 在容差内 -> exists
    low    规范化 artist+title 一致，但专辑/版本/时长有差异 -> possible_duplicate
- remix / live / 伴奏 / 重制 等不同版本只判“疑似”，由用户决定。
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import Song, SongFile

# 时长容差：绝对 5 秒或相对 8%
_DURATION_TOL_SECONDS = 5
_DURATION_TOL_RATIO = 0.08

# 版本差异关键词：两侧标题任一包含而另一侧不含时，只判“疑似重复”
_VERSION_KEYWORDS = (
    "remix",
    "live",
    "acoustic",
    "demo",
    "instrumental",
    "karaoke",
    "extended",
    "radio edit",
    "club mix",
    "dj",
    "伴奏",
    "纯音乐",
    "现场",
    "演唱会",
    "翻唱",
    "重制",
    "重置",
    "混音",
    "剪辑版",
)

_BRACKET_RE = re.compile(r"[\(\[\【][^\)\]\】]*[\)\]\】]")
_MULTI_SPACE = re.compile(r"\s+")
_FEAT_SPLIT = re.compile(
    r"\s*(?:feat\.?|ft\.?|featuring|with|和|＆|&|/|、|,|，| x )\s*",
    re.IGNORECASE,
)


def _nfkc_lower(value: Optional[str]) -> str:
    if not value:
        return ""
    s = unicodedata.normalize("NFKC", str(value)).casefold()
    return _MULTI_SPACE.sub(" ", s).strip()


def _norm_title(value: Optional[str]) -> tuple[str, frozenset]:
    """返回（基础标题, 版本标记集合）。基础标题去除括号版本说明。"""
    raw = _nfkc_lower(value)
    if not raw:
        return "", frozenset()
    base = _BRACKET_RE.sub(" ", raw)
    base = _MULTI_SPACE.sub(" ", base).strip(" -_.")
    tokens = frozenset(kw for kw in _VERSION_KEYWORDS if kw in raw)
    return base, tokens


def _norm_artist(value: Optional[str]) -> str:
    """取主演唱者：去掉 feat./合作者差异，统一大小写与全半角。"""
    raw = _nfkc_lower(value)
    if not raw:
        return ""
    primary = _FEAT_SPLIT.split(raw, maxsplit=1)[0]
    return _MULTI_SPACE.sub(" ", primary).strip(" -_.")


def _norm_album(value: Optional[str]) -> str:
    return _nfkc_lower(value)


def parse_duration_seconds(value: Any) -> Optional[int]:
    """解析搜索结果时长：秒数 / 毫秒数 / ``mm:ss`` 字符串。"""
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            n = int(value)
            if n > 10000:
                n = int(round(n / 1000))
            return n if n > 0 else None
        s = str(value).strip()
        if not s:
            return None
        if ":" in s:
            parts = [int(float(x)) for x in s.split(":")]
            sec = 0
            for x in parts:
                sec = sec * 60 + x
            return sec if sec > 0 else None
        n = int(float(s))
        if n > 10000:
            n = int(round(n / 1000))
        return n if n > 0 else None
    except Exception:
        return None


def _duration_close(a: Optional[int], b: Optional[int]) -> Optional[bool]:
    """两侧都有时长时返回是否接近；任一缺失返回 None（无法判断）。"""
    if not a or not b or a <= 0 or b <= 0:
        return None
    diff = abs(a - b)
    return diff <= _DURATION_TOL_SECONDS or diff <= max(a, b) * _DURATION_TOL_RATIO


class _SongEntry:
    __slots__ = ("id", "title", "artist", "album", "duration", "source", "source_id",
                 "base_title", "version_tokens", "norm_artist", "norm_album")

    def __init__(self, row: Any):
        self.id = row.id
        self.title = row.title
        self.artist = row.artist
        self.album = row.album
        self.duration = row.duration
        self.source = row.source
        self.source_id = row.source_id
        self.base_title, self.version_tokens = _norm_title(row.title)
        self.norm_artist = _norm_artist(row.artist)
        self.norm_album = _norm_album(row.album)


def _load_song_index(db: Session) -> dict[str, Any]:
    rows = db.query(
        Song.id, Song.title, Song.artist, Song.album,
        Song.duration, Song.source, Song.source_id,
    ).all()
    by_source_id: dict[str, list[_SongEntry]] = {}
    by_key: dict[tuple[str, str], list[_SongEntry]] = {}
    by_title: dict[str, list[_SongEntry]] = {}
    for row in rows:
        entry = _SongEntry(row)
        if entry.source_id:
            by_source_id.setdefault(str(entry.source_id).strip(), []).append(entry)
        if entry.base_title:
            if entry.norm_artist:
                by_key.setdefault((entry.norm_artist, entry.base_title), []).append(entry)
            by_title.setdefault(entry.base_title, []).append(entry)
    return {"by_source_id": by_source_id, "by_key": by_key, "by_title": by_title}


def _grade(entry: _SongEntry, *, album: str, tokens: frozenset,
           duration: Optional[int]) -> str:
    """对同 (artist, base_title) 的候选定级：medium / low。"""
    if entry.version_tokens != tokens:
        return "low"
    entry_album = entry.norm_album
    if entry_album and album and entry_album == album:
        close = _duration_close(duration, entry.duration)
        if close is False:
            return "low"
        return "medium"
    return "low"


def _match_one(index: dict[str, Any], item: dict[str, Any]):
    """返回 (命中歌曲, 置信度 high/medium/low)，未命中返回 None。"""
    base_title, tokens = _norm_title(item.get("song_name"))
    if not base_title:
        return None
    artist = _norm_artist(item.get("singers"))
    album = _norm_album(item.get("album"))
    duration = parse_duration_seconds(item.get("duration"))

    # high：平台曲目 ID 一致
    sid = str(item.get("song_id") or "").strip()
    if sid:
        for entry in index["by_source_id"].get(sid, []):
            return entry, "high"

    candidates: list[_SongEntry] = []
    if artist:
        candidates = list(index["by_key"].get((artist, base_title), []))
    if not candidates:
        # 搜索侧或库内侧缺艺术家时退化为标题匹配
        title_only = [
            e for e in index["by_title"].get(base_title, [])
            if not artist or not e.norm_artist or e.norm_artist == artist
        ]
        best_low: Optional[_SongEntry] = None
        best_low_rank: Optional[tuple[int, int]] = None
        for entry in title_only:
            grade = _grade(entry, album=album, tokens=tokens, duration=duration)
            if grade == "medium" and (artist or entry.norm_artist):
                return entry, "medium"
            rank = (
                0 if entry.version_tokens == tokens else 1,
                0 if entry.norm_album and entry.norm_album == album else 1,
            )
            if best_low is None or rank < best_low_rank:
                best_low = entry
                best_low_rank = rank
        return (best_low, "low") if best_low else None

    best_medium: Optional[_SongEntry] = None
    best_low2: Optional[_SongEntry] = None
    best_low2_rank: Optional[tuple[int, int]] = None
    for entry in candidates:
        grade = _grade(entry, album=album, tokens=tokens, duration=duration)
        if grade == "medium" and best_medium is None:
            best_medium = entry
        elif grade == "low":
            rank = (
                0 if entry.version_tokens == tokens else 1,
                0 if entry.norm_album and entry.norm_album == album else 1,
            )
            if best_low2 is None or rank < best_low2_rank:
                best_low2 = entry
                best_low2_rank = rank
    if best_medium is not None:
        return best_medium, "medium"
    if best_low2 is not None:
        return best_low2, "low"
    return None


def _summarize_versions(db: Session, song_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    """批量查询命中歌曲的 SongFile 并组装版本摘要（不暴露服务器路径）。"""
    if not song_ids:
        return {}
    files = (
        db.query(SongFile)
        .filter(SongFile.song_id.in_(song_ids))
        .order_by(SongFile.id.asc())
        .all()
    )
    out: dict[int, list[dict[str, Any]]] = {}
    for sf in files:
        is_local = bool(sf.local_path)
        size = sf.file_size
        replaceable = False
        if is_local:
            path = Path(sf.local_path)
            exists = path.is_file()
            if exists and not size:
                try:
                    size = path.stat().st_size
                except OSError:
                    size = None
            replaceable = exists and sf.availability_status != "unavailable"
        out.setdefault(sf.song_id, []).append({
            "song_file_id": sf.id,
            "location": "local" if is_local else "webdav",
            "format": (sf.format or "").lower() or None,
            "size_bytes": int(size) if size else None,
            "duration_seconds": sf.duration,
            "replaceable": replaceable,
        })
    # 本地版本排前面，便于前端默认选中可替换项
    for versions in out.values():
        versions.sort(key=lambda v: (0 if v["location"] == "local" else 1, v["song_file_id"]))
    return out


def match_search_results(db: Session, items: list[dict[str, Any]]) -> list[Optional[dict[str, Any]]]:
    """对一页搜索结果批量比对曲库，返回与输入等长的 library_match 列表。

    每个命中元素形如::

        {
            "status": "exists" | "possible_duplicate",
            "confidence": "high" | "medium" | "low",
            "song_id": int,
            "title": str, "artist": str|None, "album": str|None,
            "versions": [ {...版本摘要...} ],
        }
    """
    if not items:
        return []
    index = _load_song_index(db)
    matched = [_match_one(index, it) for it in items]
    song_ids = [m[0].id for m in matched if m]
    versions_map = _summarize_versions(db, sorted(set(song_ids)))

    results: list[Optional[dict[str, Any]]] = []
    for m in matched:
        if not m:
            results.append(None)
            continue
        entry, confidence = m
        results.append({
            "status": "possible_duplicate" if confidence == "low" else "exists",
            "confidence": confidence,
            "song_id": entry.id,
            "title": entry.title,
            "artist": entry.artist,
            "album": entry.album,
            "versions": versions_map.get(entry.id, []),
        })
    return results
