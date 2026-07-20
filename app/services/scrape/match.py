"""Chinese metadata match scoring (inspired by music-tag-web smart_tag, not a copy).

Score model:
- title/artist/album each contribute 0/1/2 (exact / contains / none)
- artist-empty queries use title for artist-field scoring (fused names like 画 赵雷)
- optional duration closeness bonus
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Mapping, Optional

# Lightweight traditional→simplified map for common music-meta chars (no zhconv dep).
_TRAD_TO_SIMP = str.maketrans(
    {
        "輸": "输",
        "贏": "赢",
        "個": "个",
        "開": "开",
        "語": "语",
        "愛": "爱",
        "國": "国",
        "東": "东",
        "車": "车",
        "長": "长",
        "風": "风",
        "雲": "云",
        "電": "电",
        "開": "开",
        "關": "关",
        "時": "时",
        "間": "间",
        "樂": "乐",
        "對": "对",
        "會": "会",
        "來": "来",
        "這": "这",
        "還": "还",
        "與": "与",
        "無": "无",
        "為": "为",
        "們": "们",
        "點": "点",
        "過": "过",
        "後": "后",
        "從": "从",
        "當": "当",
        "經": "经",
        "現": "现",
        "發": "发",
        "總": "总",
        "學": "学",
        "兒": "儿",
        "裡": "里",
        "麼": "么",
        "妳": "你",
        "牠": "它",
        "祇": "只",
        "隻": "只",
        "臺": "台",
        "灣": "湾",
        "眾": "众",
        "華": "华",
        "廣": "广",
        "傳": "传",
        "優": "优",
        "傷": "伤",
        "夢": "梦",
        "戀": "恋",
        "離": "离",
        "陽": "阳",
        "陰": "阴",
        "聲": "声",
        "響": "响",
        "聽": "听",
        "見": "见",
        "親": "亲",
        "認": "认",
        "識": "识",
        "記": "记",
        "憶": "忆",
        "歲": "岁",
        "餘": "余",
        "餘": "余",
        "溫": "温",
        "熱": "热",
        "燙": "烫",
        "幣": "币",
        "楓": "枫",
        "燈": "灯",
        "館": "馆",
        "牆": "墙",
        "樓": "楼",
        "橋": "桥",
        "島": "岛",
        "鄉": "乡",
        "鎮": "镇",
        "縣": "县",
        "醫": "医",
        "藥": "药",
        "體": "体",
        "髮": "发",
        "鬚": "须",
        "魚": "鱼",
        "鳥": "鸟",
        "馬": "马",
        "龍": "龙",
        "鳳": "凤",
        "雞": "鸡",
        "貓": "猫",
        "豬": "猪",
        "賣": "卖",
        "買": "买",
        "貴": "贵",
        "賤": "贱",
        "質": "质",
        "寶": "宝",
        "實": "实",
        "專": "专",
        "輯": "辑",
        "藝": "艺",
        "術": "术",
        "術": "术",
        "傑": "杰",
        "倫": "伦",
        "劉": "刘",
        "張": "张",
        "陳": "陈",
        "楊": "杨",
        "黃": "黄",
        "趙": "赵",
        "周": "周",
        "吳": "吴",
        "鄭": "郑",
        "孫": "孙",
        "馬": "马",
        "朱": "朱",
        "胡": "胡",
        "郭": "郭",
        "何": "何",
        "高": "高",
        "羅": "罗",
        "梁": "梁",
        "宋": "宋",
        "唐": "唐",
        "許": "许",
        "鄧": "邓",
        "馮": "冯",
        "韓": "韩",
        "曹": "曹",
        "袁": "袁",
        "鄧": "邓",
        "蕭": "萧",
        "程": "程",
        "蔡": "蔡",
        "彭": "彭",
        "潘": "潘",
        "袁": "袁",
        "于": "于",
        "蔣": "蒋",
        "蔡": "蔡",
        "余": "余",
        "杜": "杜",
        "葉": "叶",
        "程": "程",
        "蘇": "苏",
        "魏": "魏",
        "呂": "吕",
        "丁": "丁",
        "任": "任",
        "沈": "沈",
        "姚": "姚",
        "盧": "卢",
        "姜": "姜",
        "崔": "崔",
        "鍾": "钟",
        "譚": "谭",
        "陸": "陆",
        "汪": "汪",
        "范": "范",
        "金": "金",
        "石": "石",
        "廖": "廖",
        "賈": "贾",
        "夏": "夏",
        "韋": "韦",
        "付": "付",
        "方": "方",
        "白": "白",
        "鄒": "邹",
        "孟": "孟",
        "熊": "熊",
        "秦": "秦",
        "邱": "邱",
        "江": "江",
        "尹": "尹",
        "薛": "薛",
        "闞": "阚",
        "段": "段",
        "雷": "雷",
        "侯": "侯",
        "龍": "龙",
        "史": "史",
        "陶": "陶",
        "黎": "黎",
        "賀": "贺",
        "顧": "顾",
        "毛": "毛",
        "郝": "郝",
        "龔": "龚",
        "邵": "邵",
        "萬": "万",
        "錢": "钱",
        "嚴": "严",
        "覃": "覃",
        "武": "武",
        "戴": "戴",
        "莫": "莫",
        "孔": "孔",
        "向": "向",
        "湯": "汤",
    }
)

_SPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[\s\-–—_/\\|·•,，.。:：;；'\"“”‘’()（）\[\]【】{}<>《》!！?？~～@#￥$%^&*+=]+")


def to_simplified(text: str) -> str:
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", str(text))
    return s.translate(_TRAD_TO_SIMP)


def normalize_for_match(value: Optional[str]) -> str:
    if value is None:
        return ""
    s = to_simplified(str(value)).lower()
    s = _PUNCT_RE.sub("", s)
    return s.strip()


def match_score(my_value: Optional[str], other_value: Optional[str]) -> int:
    """0 none / 1 contains / 2 exact (after simplify + strip punct)."""
    a = normalize_for_match(my_value)
    b = normalize_for_match(other_value)
    if not a or not b:
        return 0
    if a == b:
        return 2
    if a in b or b in a:
        return 1
    return 0


def match_artist(my_value: Optional[str], other_value: Optional[str]) -> int:
    """Score artist; candidate may contain multiple artists.

    If query artist is contained by `刘惜君,王赫野`, it should score as exact artist hit.
    """
    if not other_value:
        return match_score(my_value, other_value)
    q = normalize_for_match(my_value)
    c = normalize_for_match(other_value)
    if q and c:
        if q == c:
            return 2
        if q in c or c in q:
            return 2 if len(q) >= 2 else 1
    parts = re.split(r"[,，/、&＆|+＋和与]", str(other_value))
    parts = [p.strip() for p in parts if p and p.strip()]
    if not parts:
        return 0
    return min(2, sum(match_score(my_value, part) for part in parts[:4]))


def duration_bonus(query_duration: Optional[int], candidate_duration: Optional[int]) -> float:
    """Local file duration vs candidate. Prefer mutagen/tinytag/ffprobe, not scrape.

    Strong signal for Chinese multi-version tracks (live / remix / same title).
    """
    if not query_duration or not candidate_duration:
        return 0.0
    try:
        qd = int(query_duration)
        cd = int(candidate_duration)
    except Exception:
        return 0.0
    if qd <= 0 or cd <= 0:
        return 0.0
    diff = abs(qd - cd)
    if diff <= 2:
        return 2.0
    if diff <= 5:
        return 1.2
    if diff <= 10:
        return 0.5
    if diff <= 15:
        return 0.0
    if diff > 30:
        return -2.0
    return -0.8


def score_candidate(
    *,
    query_title: Optional[str],
    query_artist: Optional[str] = None,
    query_album: Optional[str] = None,
    query_duration: Optional[int] = None,
    cand_title: Optional[str] = None,
    cand_artist: Optional[str] = None,
    cand_album: Optional[str] = None,
    cand_duration: Optional[int] = None,
    simple_mode: bool = False,
) -> dict[str, Any]:
    """Return breakdown + total score. Title score 0 → total forced 0 (drop).

    Duration should come from local file probe, then compare to candidate.
    """
    title_s = match_score(query_title, cand_title)
    artist_key = query_artist if (query_artist and str(query_artist).strip()) else query_title
    artist_s = match_artist(artist_key, cand_artist)
    album_s = match_score(query_album, cand_album) if query_album else 0
    bonus = duration_bonus(query_duration, cand_duration)
    penalty = 0.0
    cand_title_norm = normalize_for_match(cand_title)
    query_title_norm = normalize_for_match(query_title)
    if "伴奏" in str(cand_title or "") or "instrumental" in str(cand_title or "").lower():
        # only penalize when query is not explicitly accompaniment
        if "伴奏" not in str(query_title or "") and "instrumental" not in str(query_title or "").lower():
            penalty -= 1.5
    if cand_title_norm and query_title_norm and cand_title_norm != query_title_norm and query_title_norm in cand_title_norm:
        # extra descriptors (live/dj/etc.) are ok, but not as good as exact
        penalty -= 0.2

    if title_s <= 0:
        total = 0.0
    elif simple_mode and title_s >= 2:
        total = float(title_s + artist_s + album_s) + bonus + penalty + penalty + 0.5
    else:
        total = float(title_s + artist_s + album_s) + bonus + penalty

    return {
        "title": title_s,
        "artist": artist_s,
        "album": album_s,
        "duration_bonus": bonus,
        "penalty": penalty,
        "total": total,
        "accept": total > 0 and title_s > 0,
    }


def pick_best_candidate(
    candidates: list[Mapping[str, Any]],
    *,
    query_title: Optional[str],
    query_artist: Optional[str] = None,
    query_album: Optional[str] = None,
    query_duration: Optional[int] = None,
    simple_mode: bool = False,
    min_total: float = 2.0,
) -> tuple[Optional[Mapping[str, Any]], dict[str, Any]]:
    """Pick highest-scoring candidate. Keys: title/artist/album/duration."""
    best = None
    best_detail: dict[str, Any] = {"total": -1.0}
    ranked: list[dict[str, Any]] = []
    for c in candidates or []:
        detail = score_candidate(
            query_title=query_title,
            query_artist=query_artist,
            query_album=query_album,
            query_duration=query_duration,
            cand_title=c.get("title") or c.get("name"),
            cand_artist=c.get("artist") or c.get("singers"),
            cand_album=c.get("album"),
            cand_duration=c.get("duration"),
            simple_mode=simple_mode,
        )
        ranked.append(
            {
                "title": c.get("title") or c.get("name"),
                "artist": c.get("artist") or c.get("singers"),
                "album": c.get("album"),
                "score": detail["total"],
                "detail": detail,
                "source": c.get("source"),
            }
        )
        if detail["total"] > best_detail.get("total", -1.0):
            best = c
            best_detail = detail
    best_detail["ranked"] = sorted(ranked, key=lambda x: x["score"], reverse=True)[:8]
    if not best or best_detail.get("total", 0) < min_total:
        return None, best_detail
    return best, best_detail
