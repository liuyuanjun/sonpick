/**
 * 媒体格式知识的唯一入口（前端）。
 *
 * 对应后端 `app/services/constants.py`（`LOSSLESS_FORMATS` / `AUDIO_EXTS`）。
 * 前后端各有一份是语言边界造成的，无法直接共享模块；**但每一边都只能有一份**，
 * 组件里不要再写 `/\\.(mp3|flac|...)$/` 或 `['flac','wav',...]` 这类字面量
 * —— 历史上音频扩展名正则在 LibraryView 与 WebDAVView 各写了一份完全相同的。
 *
 * ⚠️ 改本文件时务必同步后端 constants.py；两边不一致会导致「列表显示无损、播放却选 MP3」
 * 这类难以定位的问题。建议后续加 CI 断言（见 AGENTS.md）。
 */

/** 无损格式（小写）。与后端 LOSSLESS_FORMATS 保持一致。 */
export const LOSSLESS_FORMATS = ['flac', 'wav', 'aiff', 'alac', 'ape', 'dsf', 'dff']

/** 受支持的音频扩展名（小写、不带点）。与后端 AUDIO_EXTS 保持一致。 */
export const AUDIO_EXTS = ['mp3', 'flac', 'm4a', 'wav', 'ogg', 'aac', 'ape', 'wma', 'opus']

const AUDIO_EXT_RE = new RegExp(`\\.(${AUDIO_EXTS.join('|')})$`, 'i')

/** 文件名是否音频（按扩展名判断）。 */
export function isAudioFile(name = '') {
  return AUDIO_EXT_RE.test(String(name))
}

/** 格式是否无损。 */
export function isLosslessFormat(format) {
  return LOSSLESS_FORMATS.includes(String(format || '').toLowerCase())
}

/** 格式名 → 展示用大写标签；空值返回 fallback。 */
export function formatLabel(format, fallback = '未知') {
  const value = String(format || '').trim()
  return value ? value.toUpperCase() : fallback
}

/**
 * 歌曲版本（SongFile 摘要）→ 位置标签。
 * 兼容两种形状：列表接口的 `SongFile.to_dict()`（有 local_path/webdav_path）
 * 与 `describe_files()` 的摘要（有 location）。
 */
export function versionLocationLabel(version) {
  if (!version) return '—'
  if (version.location) return version.location === 'webdav' ? 'WebDAV' : '本地'
  if (version.local_path) return '本地'
  if (version.webdav_path) return 'WebDAV'
  return '—'
}

/** 可用状态 → 展示标签。 */
export function availabilityLabel(status) {
  if (status === 'available') return '可用'
  if (status === 'unavailable') return '失效'
  return '未检查'
}

/** 可用状态 → Naive tag type。 */
export function availabilityTagType(status) {
  if (status === 'available') return 'success'
  if (status === 'unavailable') return 'error'
  return 'default'
}
