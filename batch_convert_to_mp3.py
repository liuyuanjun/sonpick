#!/usr/bin/env python3
"""
批量把指定目录中的 FLAC/MP3/M4A/WAV/OGG 等音频文件转成 320kbps MP3。
输出到同目录下的 mp3/ 子文件夹，保留原文件不变。

用法：
    python batch_convert_to_mp3.py /Volumes/Y/Music
    或默认当前目录：python batch_convert_to_mp3.py
"""
import os
import re
import sys
import subprocess
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed


AUDIO_EXTS = {".flac", ".m4a", ".wav", ".ogg", ".ape", ".wma", ".mp3"}
BITRATE = "320k"


def normalize(text: str) -> str:
    return re.sub(r"[\\/:*?\"<>|]", "_", text).strip()


def check_ffmpeg() -> bool:
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=10)
        return result.returncode == 0
    except Exception:
        return False


def convert_one(input_path: Path, output_dir: Path) -> tuple[Path, bool, str]:
    """转码单个文件，返回 (输出路径, 是否成功, 信息)"""
    stem = normalize(input_path.stem)
    output_path = output_dir / f"{stem}.mp3"

    # 避免重名
    idx = 1
    while output_path.exists():
        output_path = output_dir / f"{stem} ({idx}).mp3"
        idx += 1

    cmd = [
        "ffmpeg",
        "-y",                       # 覆盖输出
        "-i", str(input_path),      # 输入
        "-map", "0",                # 映射所有流（保留封面图）
        "-c:v", "copy",             # 复制封面图流
        "-ar", "44100",             # 采样率
        "-ac", "2",                 # 立体声
        "-b:a", BITRATE,            # 码率
        "-map_metadata", "0",       # 保留元数据
        "-id3v2_version", "3",      # 兼容旧车机
        str(output_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, errors="replace")
        if result.returncode != 0:
            return output_path, False, result.stderr[:300]
        return output_path, True, "OK"
    except Exception as e:
        return output_path, False, str(e)


def main():
    if len(sys.argv) > 1:
        input_dir = Path(sys.argv[1]).resolve()
    else:
        input_dir = Path.cwd().resolve()

    if not input_dir.exists():
        print(f"目录不存在: {input_dir}")
        sys.exit(1)

    if not check_ffmpeg():
        print("错误：未找到 ffmpeg。请先安装：")
        print("  macOS: brew install ffmpeg")
        print("  Windows: https://ffmpeg.org/download.html")
        sys.exit(1)

    output_dir = input_dir / "mp3"
    output_dir.mkdir(exist_ok=True)

    files = sorted([p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_EXTS])
    if not files:
        print(f"在 {input_dir} 中没有找到音频文件")
        sys.exit(0)

    print(f"输入目录: {input_dir}")
    print(f"输出目录: {output_dir}")
    print(f"找到 {len(files)} 个音频文件，开始转码为 {BITRATE} MP3...\n")

    success_count = 0
    failed = []

    # 并行转码，利用多核加速
    with ProcessPoolExecutor(max_workers=os.cpu_count() or 2) as executor:
        future_to_file = {executor.submit(convert_one, f, output_dir): f for f in files}
        for future in as_completed(future_to_file):
            src = future_to_file[future]
            try:
                output_path, ok, msg = future.result()
                if ok:
                    print(f"✅ {src.name} -> {output_path.name}")
                    success_count += 1
                else:
                    print(f"❌ {src.name}: {msg}")
                    failed.append(src.name)
            except Exception as e:
                print(f"❌ {src.name}: {e}")
                failed.append(src.name)

    print(f"\n==========")
    print(f"总计: {len(files)} 首")
    print(f"成功: {success_count} 首")
    print(f"失败: {len(failed)} 首")
    if failed:
        print("失败的文件:")
        for x in failed:
            print("  ", x)


if __name__ == "__main__":
    main()
