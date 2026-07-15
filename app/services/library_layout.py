"""曲库目录与命名规范（行业常见布局，对齐 Plex / Navidrome / foobar2000 习惯）。

目录结构
--------
    {storage_root}/
      {Artist}/
        artist.jpg          # 艺术家图（兼认 folder.jpg / Artist.jpg）
        {Album}/
          cover.jpg         # 专辑封面（兼认 folder/front/AlbumArt*）
          {Title}.flac      # 音频
          {Title}.lrc       # 歌词（与音频同 stem；可 .txt 兜底）
          {Title}.jpg       # 可选：单曲封面（优先仍用 cover.jpg / 内嵌图）

优先级（元数据解析）
--------------------
1. 音频内嵌标签 / 内嵌图 / 内嵌词
2. 目录侧车文件（同 stem 歌词、专辑 cover、艺术家图）
3. 数据库已有路径
4. 网络补全（musicdl 等，可选）

文件名清洗：去掉路径分隔符与 Windows 非法字符，截断过长名称。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Optional

# 音频 / 侧车扩展
AUDIO_EXTS: tuple[str, ...] = (
    ".mp3",
    ".flac",
    ".m4a",
    ".wav",
    ".ogg",
    ".aac",
    ".ape",
    ".wma",
    ".opus",
)
LRC_EXTS: tuple[str, ...] = (".lrc", ".LRC", ".txt", ".TXT")
COVER_IMAGE_EXTS: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".webp", ".gif")

# 专辑目录内封面候选（按优先级）
ALBUM_COVER_NAMES: tuple[str, ...] = (
    "cover.jpg",
    "cover.jpeg",
    "cover.png",
    "cover.webp",
    "folder.jpg",
    "folder.jpeg",
    "folder.png",
    "Folder.jpg",
    "front.jpg",
    "front.png",
    "AlbumArt.jpg",
    "AlbumArtSmall.jpg",
    "albumart.jpg",
    "album.jpg",
    "Album.jpg",
)

# 艺术家目录内封面候选
ARTIST_IMAGE_NAMES: tuple[str, ...] = (
    "artist.jpg",
    "artist.jpeg",
    "artist.png",
    "artist.webp",
    "Artist.jpg",
    "folder.jpg",
    "folder.png",
    "Folder.jpg",
)

# 绝不能当作艺术家/专辑的集合目录名
GENERIC_DIR_NAMES: frozenset[str] = frozenset(
    {
        "music",
        "songs",
        "audio",
        "download",
        "downloads",
        "flac",
        "mp3",
        "m4a",
        "wav",
        "media",
        "library",
        "music library",
        "musiclibrary",
        "favorite",
        "favorites",
        "favourite",
        "favourites",
        "liked",
        "liked songs",
        "all",
        "misc",
        "various",
        "various artists",
        "va",
        "inbox",
        "import",
        "imports",
        "new",
        "temp",
        "tmp",
        "cache",
        "shared",
        "public",
        "data",
        "storage",
        "unknown",
        "unknown artist",
        "unknown album",
        "未知",
        "未知艺术家",
        "未知专辑",
    }
)

UNKNOWN_ARTIST = "Unknown Artist"
UNKNOWN_ALBUM = "Unknown Album"

# 下载页 / 文档说明（中文）
LIBRARY_LAYOUT_HELP_ZH = """曲库目录与命名规范

推荐布局（与常见播放器/NAS 曲库一致）：
  艺术家/专辑/歌名.flac
  艺术家/专辑/歌名.lrc          （歌词与音频同名）
  艺术家/专辑/cover.jpg         （专辑封面；也认 folder/front/AlbumArt）
  艺术家/artist.jpg             （艺术家图；也认 folder.jpg）

元数据读取顺序：
  1. 歌曲内嵌标签 / 内嵌封面 / 内嵌歌词
  2. 目录侧车文件（同目录 cover、同名 lrc/txt）
  3. 库内已保存路径
  4. 网络搜索补全（可选）

说明：Favorite / Downloads 等收藏夹目录不会被当成艺术家。
新下载会自动按「艺术家/专辑」建目录；旧库可用整理脚本迁移。
"""


def sanitize_component(name: Optional[str], fallback: str, *, max_len: int = 120) -> str:
    """清洗单层目录/文件名组件。"""
    s = (name or "").strip() or fallback
    for ch in '\\/:*?"<>|\r\n\t':
        s = s.replace(ch, "_")
    s = s.strip(" .")
    # 避免 Windows 保留名
    if s.upper() in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "LPT1",
        "LPT2",
        "LPT3",
    }:
        s = f"_{s}"
    if not s:
        s = fallback
    return s[:max_len]


def is_generic_dir_name(name: Optional[str]) -> bool:
    if not name:
        return True
    s = str(name).strip().lower()
    if not s:
        return True
    if s in GENERIC_DIR_NAMES:
        return True
    if s.startswith("playlist") or s.endswith(" playlist"):
        return True
    return False


def artist_dir_name(artist: Optional[str]) -> str:
    if is_generic_dir_name(artist):
        return UNKNOWN_ARTIST
    return sanitize_component(artist, UNKNOWN_ARTIST)


def album_dir_name(album: Optional[str]) -> str:
    if is_generic_dir_name(album):
        return UNKNOWN_ALBUM
    return sanitize_component(album, UNKNOWN_ALBUM)


def track_stem(title: Optional[str], fallback: str = "track") -> str:
    return sanitize_component(title, fallback, max_len=160)


def library_relative_dir(artist: Optional[str], album: Optional[str]) -> Path:
    """返回相对路径：Artist/Album。"""
    return Path(artist_dir_name(artist)) / album_dir_name(album)


def library_audio_relpath(
    artist: Optional[str],
    album: Optional[str],
    title: Optional[str],
    ext: str,
) -> Path:
    """返回相对路径：Artist/Album/Title.ext。"""
    e = ext if ext.startswith(".") else f".{ext}"
    return library_relative_dir(artist, album) / f"{track_stem(title)}{e.lower()}"


def lrc_path_for_audio(audio_path: str | Path) -> Path:
    return Path(audio_path).with_suffix(".lrc")


def preferred_album_cover_path(album_dir: str | Path, ext: str = ".jpg") -> Path:
    e = ext if ext.startswith(".") else f".{ext}"
    if e.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
        e = ".jpg"
    # 规范名统一 cover.jpg（jpeg 也落到 .jpg）
    if e.lower() in {".jpg", ".jpeg"}:
        return Path(album_dir) / "cover.jpg"
    return Path(album_dir) / f"cover{e.lower()}"


def preferred_artist_image_path(artist_dir: str | Path, ext: str = ".jpg") -> Path:
    e = ext if ext.startswith(".") else f".{ext}"
    if e.lower() in {".jpg", ".jpeg"}:
        return Path(artist_dir) / "artist.jpg"
    return Path(artist_dir) / f"artist{e.lower()}"


def find_album_cover_file(album_dir: str | Path) -> Optional[Path]:
    d = Path(album_dir)
    if not d.is_dir():
        return None
    # 固定名优先
    for name in ALBUM_COVER_NAMES:
        p = d / name
        if p.is_file():
            return p
    # 大小写不敏感扫描
    try:
        wanted = {n.lower() for n in ALBUM_COVER_NAMES}
        for child in d.iterdir():
            if child.is_file() and child.name.lower() in wanted:
                return child
    except Exception:
        pass
    return None


def find_artist_image_file(artist_dir: str | Path) -> Optional[Path]:
    d = Path(artist_dir)
    if not d.is_dir():
        return None
    for name in ARTIST_IMAGE_NAMES:
        p = d / name
        if p.is_file():
            return p
    try:
        wanted = {n.lower() for n in ARTIST_IMAGE_NAMES}
        for child in d.iterdir():
            if child.is_file() and child.name.lower() in wanted:
                return child
    except Exception:
        pass
    return None


def find_track_cover_file(audio_path: str | Path) -> Optional[Path]:
    """同 stem 单曲封面：Title.jpg / Title.png ..."""
    audio = Path(audio_path)
    stem = audio.with_suffix("")
    for ext in COVER_IMAGE_EXTS:
        for cand in (Path(str(stem) + ext), audio.with_suffix(ext)):
            if cand.is_file():
                return cand
    # 大小写
    try:
        wanted = {audio.stem.lower() + e for e in COVER_IMAGE_EXTS}
        for child in audio.parent.iterdir():
            if child.is_file() and child.name.lower() in wanted:
                return child
    except Exception:
        pass
    return None


def find_lrc_sidecar(audio_path: str | Path) -> Optional[Path]:
    """查找与音频同目录的歌词侧车。"""
    audio = Path(audio_path)
    for ext in LRC_EXTS:
        for cand in (audio.with_suffix(ext), Path(str(audio.with_suffix("")) + ext)):
            if cand.is_file():
                return cand
    try:
        stem_low = audio.stem.lower()
        fuzzy: list[Path] = []
        for child in audio.parent.iterdir():
            if not child.is_file():
                continue
            low = child.name.lower()
            if not low.endswith((".lrc", ".txt")):
                continue
            cstem = child.stem.lower()
            if cstem == stem_low or stem_low in cstem or cstem in stem_low:
                fuzzy.append(child)
        fuzzy.sort(
            key=lambda c: (
                0 if c.suffix.lower() == ".lrc" else 1,
                abs(len(c.stem) - len(audio.stem)),
                c.name,
            )
        )
        if fuzzy:
            return fuzzy[0]
    except Exception:
        pass
    return None


def unique_path(directory: Path, stem: str, ext: str) -> Path:
    """在 directory 下生成不冲突的文件路径。"""
    e = ext if ext.startswith(".") else f".{ext}"
    directory.mkdir(parents=True, exist_ok=True)
    candidate = directory / f"{stem}{e}"
    if not candidate.exists():
        return candidate
    i = 1
    while True:
        candidate = directory / f"{stem}_{i}{e}"
        if not candidate.exists():
            return candidate
        i += 1


def iter_layout_doc_lines() -> Iterable[str]:
    for line in LIBRARY_LAYOUT_HELP_ZH.strip().splitlines():
        yield line


def parse_filename_meta(name: str | Path) -> dict[str, Optional[str]]:
    """从文件名启发式解析 title/artist。

    支持：
    - ``Artist - Title``（空格连字符，偏国际习惯）
    - ``Title - Artist`` / ``Title-Artist``（中文网盘常见：歌名-歌手，如 画-赵雷）
    - ``01 - Title`` 曲序号
    """
    if isinstance(name, Path):
        stem = name.stem.strip()
    else:
        s = str(name).strip()
        stem = Path(s).stem.strip() if any(ch in s for ch in "/\\") or Path(s).suffix.lower() in AUDIO_EXTS else s
        stem = stem or s

    title: Optional[str] = stem
    artist: Optional[str] = None
    matched = False

    for sep in (" - ", " – ", " — ", " | "):
        if sep in stem:
            left, right = stem.split(sep, 1)
            left_s, right_s = left.strip(), right.strip()
            if left_s and right_s:
                if re.fullmatch(r"\d{1,3}[.)]?", left_s):
                    title, artist = right_s, None
                elif _looks_like_title_artist(left_s, right_s):
                    title, artist = left_s, right_s
                else:
                    artist, title = left_s, right_s
                matched = True
            break

    if not matched and "-" in stem:
        # 画-赵雷 / 成都-赵雷 → 歌名-歌手（取最后一个 -）
        left_s, right_s = [x.strip() for x in stem.rsplit("-", 1)]
        if left_s and right_s and not re.fullmatch(r"\d{1,3}", left_s):
            # 无空格连字符在中文曲库几乎都是 歌名-歌手
            title, artist = left_s, right_s
            matched = True

    if title:
        title = re.sub(r"^\s*\d{1,3}[\s._-]+", "", str(title)).strip() or stem
    if artist and is_generic_dir_name(artist):
        artist = None
    if artist:
        artist = str(artist).strip(" _-") or None

    return {"title": title, "artist": artist}


def _looks_like_title_artist(left: str, right: str) -> bool:
    """粗判「空格分隔」时是否更像「歌名 - 歌手」。

    默认偏「歌手 - 歌名」。仅当左侧像较长歌名、右侧像短人名时反转。
    无空格的 ``歌名-歌手`` 不走此函数（固定按歌名-歌手）。
    """
    if not left or not right:
        return False
    if re.search(r"(?i)\bfeat\.?\b|\bft\.?\b|、|/|&", left):
        return False
    cjk_left = len(re.findall(r"[\u4e00-\u9fff]", left))
    cjk_right = len(re.findall(r"[\u4e00-\u9fff]", right))
    # 右侧 2~4 字中文人名 + 左侧更长歌名（>=4 字）
    if cjk_left >= 4 and 2 <= cjk_right <= 4 and cjk_left > cjk_right:
        return True
    # 非中文：左侧明显更长
    if cjk_left == 0 and len(left) >= len(right) + 4 and len(right) <= 20:
        return True
    return False
