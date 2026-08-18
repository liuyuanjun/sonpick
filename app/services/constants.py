"""全库共享的媒体格式 / 扩展名常量（单一权威）。

为避免各模块各自定义一份"什么是音频 / 无损 / 图片 / 歌词"（曾出现两处
``LOSSLESS_FORMATS`` 内容不一致、四处 ``AUDIO_EXTS`` 重复定义），统一收口于此。
新增格式 / 扩展名请只在此登记。
"""
from __future__ import annotations

# 无损格式。dsf/dff（DSD）为无损；当前扫描源 DEFAULT_SCAN_EXTS 尚未收录，
# 保留在此以正语义（播放选择已按无损对待）。转码能力是另一维度，不在此处约束。
LOSSLESS_FORMATS: frozenset[str] = frozenset({"flac", "wav", "aiff", "alac", "ape", "dsf", "dff"})

# 受支持的音频扩展名（小写、带点）。扫描 / 整理 / 去重 / 播放选择共用。
AUDIO_EXTS: frozenset[str] = frozenset({
    ".mp3", ".flac", ".m4a", ".wav", ".ogg", ".aac", ".ape", ".wma", ".opus",
})

# 图片 / 封面扩展名（小写、带点）。
IMAGE_EXTS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif"})

# 歌词侧车扩展名（含大小写变体）。
LRC_EXTS: tuple[str, ...] = (".lrc", ".LRC", ".txt", ".TXT")
