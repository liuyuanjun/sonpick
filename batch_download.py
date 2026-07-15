#!/usr/bin/env python3
"""
批量下载 qq-music-list.txt 中的歌曲。
优先输出到外置硬盘 /Volumes/Y/Music；若不可写则回退到本机 qq_music_car_downloads。
仅使用 QQMusicClient，下载后按 "歌名-歌手" 重命名，并同步移动 .lrc 歌词和 .jpg 封面。
支持交互式选择优先下载格式，也支持命令行参数 --prefer。
"""
import os
import re
import sys
import time
import json
import shutil
import argparse
from pathlib import Path
from datetime import datetime

# 当前目录下有 musicdl/ 源码目录，会干扰已安装的 musicdl 包。
# 先把当前工作目录从 sys.path 里移除，并把脚本所在目录也移除。
_cwd = os.getcwd()
_script_dir = Path(__file__).resolve().parent
for _p in list(sys.path):
    if _p == "" or os.path.realpath(_p) == os.path.realpath(_cwd) or os.path.realpath(_p) == os.path.realpath(_script_dir):
        sys.path.remove(_p)

from musicdl import musicdl

# 配置
LIST_FILE = Path(__file__).resolve().parent / "qq-music-list.txt"
EXTERNAL_DIR = Path("/Volumes/Y/Music")
LOCAL_DIR = Path(__file__).resolve().parent / "qq_music_car_downloads"
OUTPUT_DIR = EXTERNAL_DIR
MUSIC_SOURCES = ["QQMusicClient"]
MAX_RETRIES = 2
COVER_FETCH = True

# 格式优先级映射
PREFER_FORMATS = {
    "flac": ["flac"],
    "mp3": ["mp3", "m4a"],
    "m4a": ["m4a", "mp3"],
    "any": [],
}


def normalize(text: str) -> str:
    return re.sub(r"[\\/:*?"<>|]", "_", text).strip()


def get_output_dir() -> Path:
    """优先外置硬盘，不可写则回退到本地目录"""
    for d in (EXTERNAL_DIR, LOCAL_DIR):
        try:
            d.mkdir(parents=True, exist_ok=True)
            test = d / ".write_test"
            test.write_text("ok")
            test.unlink()
            return d
        except Exception:
            continue
    raise RuntimeError("无法找到可写的输出目录")


def parse_line(line: str) -> tuple[str, str]:
    """解析 '歌名 - 歌手' 格式"""
    line = line.strip()
    if not line:
        return "", ""
    line = re.sub(r"^\d+\s*[.、\.\-]?\s*", "", line)
    if " - " in line:
        song, singer = line.split(" - ", 1)
    elif "-" in line:
        song, singer = line.split("-", 1)
    else:
        song, singer = line, ""
    return song.strip(), singer.strip()


def unique_path(directory: Path, stem: str, ext: str) -> Path:
    target = directory / f"{stem}{ext}"
    idx = 1
    while target.exists():
        target = directory / f"{stem} ({idx}){ext}"
        idx += 1
    return target


def find_work_dir(base_dir: Path, keyword: str) -> Path | None:
    """
    根据 musicdl 命名规则定位本次下载生成的子目录：
    OUTPUT_DIR/QQMusicClient/YYYY-MM-DD-HH-MM-SS <keyword>
    由于时间戳是实时生成的，取该 keyword 最新创建的子目录。
    """
    source_dir = base_dir / "QQMusicClient"
    if not source_dir.exists():
        return None
    candidates = []
    for d in source_dir.iterdir():
        if d.is_dir() and keyword in d.name:
            try:
                mtime = d.stat().st_mtime
                candidates.append((mtime, d))
            except Exception:
                continue
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def download_cover(cover_url: str, target_path: Path):
    """单独下载封面图"""
    if not cover_url or not str(cover_url).startswith("http"):
        return
    try:
        import requests
        r = requests.get(cover_url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        r.raise_for_status()
        target_path.write_bytes(r.content)
    except Exception as e:
        print(f"    封面下载失败: {e}")


def move_song_files(work_dir: Path, song_name: str, singers: str) -> Path | None:
    """仅移动指定子目录里的音频、歌词、封面文件，按 歌名-歌手 重命名"""
    if not work_dir or not work_dir.exists():
        return None

    stem = normalize(f"{song_name}-{singers}")
    moved_audio = None

    for f in work_dir.iterdir():
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        if ext in {".mp3", ".flac", ".m4a", ".wav", ".ogg", ".ape", ".wma"}:
            target = unique_path(OUTPUT_DIR, stem, ext)
            shutil.move(str(f), str(target))
            moved_audio = target
            print(f"    音乐 -> {target.name}")
        elif ext == ".lrc":
            target = unique_path(OUTPUT_DIR, stem, ".lrc")
            shutil.move(str(f), str(target))
            print(f"    歌词 -> {target.name}")

    return moved_audio


def pick_song_info(items: list, prefer: str) -> object | None:
    """
    根据优先格式从搜索结果中选择一首。
    prefer 为 "flac"/"mp3"/"m4a"/"any"
    """
    prefer = prefer.lower().strip()
    if prefer not in PREFER_FORMATS:
        prefer = "any"
    wanted = PREFER_FORMATS[prefer]

    valid_items = [it for it in items if getattr(it, "with_valid_download_url", False)]
    if not valid_items:
        return None

    if wanted:
        for ext in wanted:
            for item in valid_items:
                item_ext = (getattr(item, "ext", "") or "").lower().lstrip(".")
                if item_ext == ext:
                    return item
        print(f"    未找到 {prefer.upper()} 格式，回退到首个有效结果")

    return valid_items[0]


def search_and_download(client, song_name: str, singers: str, prefer: str, retry: int = 0):
    keyword = f"{song_name} {singers}".strip()
    print(f"  搜索: {keyword}")

    try:
        results = client.search(keyword=keyword)
    except Exception as e:
        print(f"  搜索失败: {e}")
        if retry < MAX_RETRIES:
            time.sleep(2)
            return search_and_download(client, song_name, singers, prefer, retry + 1)
        return False

    items = results.get("QQMusicClient", [])
    song_info = pick_song_info(items, prefer)

    if not song_info:
        print(f"  未找到有效下载链接")
        return False

    ext = (getattr(song_info, "ext", "") or "").upper()
    print(f"  命中: {song_info.song_name} - {song_info.singers} [{song_info.source}] [{ext}] {song_info.file_size}")

    try:
        client.download([song_info])
        # 定位本次下载生成的子目录并移动文件
        work_dir = find_work_dir(OUTPUT_DIR, keyword)
        moved_audio = move_song_files(work_dir, song_name, singers)
        if moved_audio and getattr(song_info, "cover_url", None):
            cover_path = moved_audio.with_suffix(".jpg")
            if not cover_path.exists():
                download_cover(song_info.cover_url, cover_path)
        print(f"  ✅ 完成")
        return True
    except Exception as e:
        print(f"  下载失败: {e}")
        if retry < MAX_RETRIES:
            time.sleep(2)
            return search_and_download(client, song_name, singers, prefer, retry + 1)
        return False


def ask_prefer_format() -> str:
    """交互式询问优先格式"""
    print("\n请选择优先下载格式：")
    print("  1) FLAC - 无损音质，文件较大")
    print("  2) MP3/M4A - 兼容性好，适合车机")
    print("  3) 任意 - 哪个先找到用哪个（默认）")
    choice = input("请输入 [1/2/3，默认3]: ").strip()
    mapping = {"1": "flac", "2": "mp3", "3": "any", "": "any"}
    return mapping.get(choice, "any")


def main():
    parser = argparse.ArgumentParser(description="批量下载 QQ 音乐歌单")
    parser.add_argument(
        "--prefer",
        choices=["flac", "mp3", "m4a", "any"],
        default=None,
        help="优先下载格式（不指定则进入交互式选择）"
    )
    args = parser.parse_args()

    prefer = args.prefer or ask_prefer_format()
    print(f"优先格式: {prefer.upper()}")

    global OUTPUT_DIR
    OUTPUT_DIR = get_output_dir()
    print(f"输出目录: {OUTPUT_DIR}")

    progress_file = OUTPUT_DIR / ".download_progress.json"
    progress = {}
    if progress_file.exists():
        try:
            progress = json.loads(progress_file.read_text(encoding="utf-8"))
        except Exception:
            progress = {}

    init_cfg = {
        "QQMusicClient": {"work_dir": str(OUTPUT_DIR), "search_size_per_source": 5}
    }

    print("正在初始化 musicdl...")
    client = musicdl.MusicClient(
        music_sources=MUSIC_SOURCES,
        init_music_clients_cfg=init_cfg,
        clients_threadings={"QQMusicClient": 3},
    )

    lines = [
        line.strip()
        for line in LIST_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    total = len(lines)
    success = 0
    failed = []

    for idx, line in enumerate(lines, 1):
        song_name, singers = parse_line(line)
        if not song_name:
            continue

        key = f"{song_name} - {singers}"
        if key in progress and progress[key].get("done"):
            print(f"[{idx}/{total}] 已跳过（已下载）: {key}")
            success += 1
            continue

        print(f"\n[{idx}/{total}] {key}")
        ok = search_and_download(client, song_name, singers, prefer)
        if ok:
            progress[key] = {"done": True}
            success += 1
        else:
            progress[key] = {"done": False, "line": line}
            failed.append(key)

        progress_file.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(0.8)

    print(f"\n==========")
    print(f"总计: {total} 首")
    print(f"成功: {success} 首")
    print(f"失败: {len(failed)} 首")
    if failed:
        print("失败的歌曲:")
        for x in failed:
            print("  ", x)


if __name__ == "__main__":
    main()
