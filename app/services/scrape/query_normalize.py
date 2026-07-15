"""Normalize noisy titles/artists before network scrape.

Common pollution from ripped/shared Chinese music files:
- QQ Music songmid prefixes like ``002mNoNz3sZvaI 人间道``
- track numbers, quality tags, bracketed extras
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

# QQ songmid-like: often starts with 00 + alnum, total 12–16 chars
_SONGMID_PREFIX = re.compile(
    r"^(?:"
    r"00[0-9A-Za-z]{10,14}"  # classic QQ mid prefix
    r"|[0-9A-Za-z]{12,16}"   # generic opaque id token
    r")(?=[\s_\-\.]+|[\u4e00-\u9fff])",
    re.I,
)
_LEADING_TRACKNO = re.compile(r"^\s*\d{1,3}[\s._\-]+")
_QUALITY_TAG = re.compile(
    r"[\s_\-]*(?:\(|\[|【)?"
    r"(?:live|remix|伴奏|纯音乐|instrumental|official|mv|audio|flac|320k|hi-?res|sq|hq)"
    r"(?:\)|\]|】)?\s*$",
    re.I,
)
_MULTI_SPACE = re.compile(r"[\s_\-]+")
_GARBAGE_ONLY = re.compile(r"^[0-9A-Za-z_\-]{8,}$")


def _nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s)


def clean_title(value: Optional[str]) -> str:
    if value is None:
        return ""
    s = _nfkc(str(value)).strip()
    if not s:
        return ""
    # drop songmid / opaque id prefix
    s2 = _SONGMID_PREFIX.sub("", s).strip()
    if s2:
        s = s2
    s = _LEADING_TRACKNO.sub("", s).strip()
    # remove common quality / live tags at end
    for _ in range(3):
        s2 = _QUALITY_TAG.sub("", s).strip()
        if s2 == s:
            break
        s = s2
    # if title still has "id + real title", keep chinese/latin title part
    m = re.match(r"^([0-9A-Za-z]{8,16})[\s_\-\.]+(.+)$", s)
    if m and re.search(r"[\u4e00-\u9fffA-Za-z]", m.group(2)):
        s = m.group(2).strip()
    s = _MULTI_SPACE.sub(" ", s).strip(" -_.")
    if _GARBAGE_ONLY.fullmatch(s or ""):
        return ""
    return s


def clean_artist(value: Optional[str]) -> str:
    if value is None:
        return ""
    s = _nfkc(str(value)).strip()
    if not s:
        return ""
    s2 = _SONGMID_PREFIX.sub("", s).strip()
    if s2:
        s = s2
    # drop feat. extras for search (keep primary artist)
    s = re.split(r"\s*(?:feat\.?|ft\.?|featuring|with|和|＆|&|/|、|,|，)\s*", s, maxsplit=1, flags=re.I)[0]
    s = _MULTI_SPACE.sub(" ", s).strip(" -_.")
    if _GARBAGE_ONLY.fullmatch(s or ""):
        return ""
    low = s.lower()
    if low in {"unknown", "unknown artist", "各种艺术家", "群星", "va", "various artists", "未知", "未知艺术家"}:
        return ""
    return s


def build_search_keyword(title: Optional[str], artist: Optional[str] = None) -> str:
    t = clean_title(title)
    a = clean_artist(artist)
    if t and a:
        return f"{t} {a}".strip()
    return t or a or ""


def looks_like_opaque_id(value: Optional[str]) -> bool:
    if not value:
        return False
    s = str(value).strip()
    if _SONGMID_PREFIX.match(s):
        return True
    return bool(_GARBAGE_ONLY.fullmatch(s))


def split_title_artist(
    title: Optional[str],
    artist: Optional[str] = None,
) -> tuple[str, str]:
    """Split fused ``画 赵雷`` / ``画-赵雷`` into title+artist when artist missing.

    Common NAS filenames end up as DB title with artist glued on, while artist is empty.
    """
    t = clean_title(title)
    a = clean_artist(artist) if artist else ""
    if a:
        # if title still ends with artist, strip it
        if t and a and (t.endswith(a) or t.endswith(" " + a) or t.endswith("-" + a)):
            for sep in (f" - {a}", f"-{a}", f" {a}", a):
                if t.endswith(sep) and len(t) > len(sep):
                    t2 = t[: -len(sep)].strip(" -_")
                    if t2:
                        t = t2
                        break
        return t, a

    if not t:
        return "", ""

    # dash forms: 画-赵雷 / 画 - 赵雷
    for sep in (" - ", " – ", " — ", "-", "—", "–", "_", "|"):
        if sep in t:
            left, right = t.rsplit(sep, 1)
            left, right = left.strip(), right.strip()
            if left and right and 1 <= len(right) <= 20 and not _GARBAGE_ONLY.fullmatch(right):
                # prefer shorter right as artist for Chinese names
                if re.fullmatch(r"\d{1,3}", left):
                    continue
                return clean_title(left) or left, clean_artist(right) or right

    # space form: 画 赵雷 / 成都 赵雷 / 背叛 曹格 (2-3 CJK chunks)
    parts = [x for x in re.split(r"\s+", t) if x]
    if len(parts) == 2:
        left, right = parts[0], parts[1]
        # both mostly CJK/short latin → treat as title + artist
        if re.search(r"[\u4e00-\u9fff]", left) and re.search(r"[\u4e00-\u9fff]", right):
            if 1 <= len(right) <= 12 and 1 <= len(left) <= 40:
                return left, right
    if len(parts) >= 3:
        # last token as artist: 说好不哭 周杰伦
        right = parts[-1]
        left = " ".join(parts[:-1])
        if re.search(r"[\u4e00-\u9fff]", right) and 1 <= len(right) <= 12:
            return left, right

    return t, ""


def build_search_parts(title: Optional[str], artist: Optional[str] = None) -> tuple[str, str, str]:
    """Return (title, artist, keyword)."""
    t, a = split_title_artist(title, artist)
    if t and a:
        kw = f"{t} {a}".strip()
    else:
        kw = t or a or ""
    return t, a, kw


def build_search_keyword(title: Optional[str], artist: Optional[str] = None) -> str:  # noqa: F811
    _t, _a, kw = build_search_parts(title, artist)
    return kw

_TITLE_ARTIST_HINTS = re.compile(
    r"\b(live|伴奏|remix|dj|版|合唱|cover|翻唱|纯音乐|instrumental)\b|[（(]",
    re.I,
)


def repair_shifted_meta(
    title: Optional[str],
    artist: Optional[str] = None,
    album: Optional[str] = None,
) -> tuple[str, str, str]:
    """Repair common bad tag shift: title=songmid, artist=title, album=artist.

    Example from QQ files:
      title='002pVHHu3sjaAW', artist='晚风心里吹 (Live)', album='王赫野'
    should become:
      title='晚风心里吹', artist='王赫野', album=''
    """
    raw_title = str(title or "").strip()
    raw_artist = str(artist or "").strip()
    raw_album = str(album or "").strip()

    ct = clean_title(raw_title)
    ca = clean_artist(raw_artist)
    al = raw_album.strip()

    title_is_id = looks_like_opaque_id(raw_title) or (not ct and raw_title)
    artist_looks_title = bool(raw_artist) and (
        _TITLE_ARTIST_HINTS.search(raw_artist) is not None
        or not clean_artist(raw_artist)
        or len(raw_artist) > 8
    )
    album_looks_artist = bool(al) and not looks_like_opaque_id(al) and not _TITLE_ARTIST_HINTS.search(al) and len(al) <= 20

    if title_is_id and raw_artist:
        new_title = clean_title(raw_artist) or raw_artist
        new_artist = clean_artist(raw_album) if album_looks_artist else ""
        return new_title, new_artist, ""

    # title is empty/id, artist has song name, album has artist
    if (not ct) and raw_artist:
        new_title = clean_title(raw_artist) or raw_artist
        new_artist = clean_artist(raw_album) if album_looks_artist else ca
        return new_title, new_artist or "", ""

    return ct or raw_title, ca or raw_artist, al

