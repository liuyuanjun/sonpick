/**
 * 展示格式化的唯一入口（前端）。
 *
 * 规矩：**任何"数字/时间 → 给人看的字符串"的转换都写在这里**。
 * 组件里不要再定义 formatSize / formatTime / formatDuration 之类的本地函数
 * —— 历史上这类函数在 Dashboard / Library / Logs / TaskCenter / TaskDetail / SearchDownload
 * 各写了一份，同一份数据在不同页面显示口径不一致（例如 512 字节在下载页显示 "0 KB"，
 * 在曲库页显示 "512 B"）。
 *
 * 各函数的语义边界（不要合并，也不要互相替代）：
 *   - formatClock      : 秒 → `mm:ss`，音频时间轴刻度（进度条、歌词时间）
 *   - formatDurationText: 秒 → `3 小时 25 分`，给人读的"时长"（总时长、任务耗时）
 *   - formatRelativeTime: 秒 → `3 分钟前`，相对当下
 *   - formatDateTime   : ISO/时间戳 → 本地时间字符串，给人读的"时刻"
 */

const UNITS = [
  { limit: 1024 ** 4, suffix: 'TB', digits: 2 },
  { limit: 1024 ** 3, suffix: 'GB', digits: 2 },
  { limit: 1024 ** 2, suffix: 'MB', digits: 2 },
  { limit: 1024, suffix: 'KB', digits: 1 },
]

/**
 * 严格数值化：注意 `Number(null) === 0`、`Number('') === 0`，
 * 直接用 Number() 会把"缺数据"当成"0 秒 / 0 字节"渲染出来。
 * 缺数据一律返回 null，由各函数决定占位符。
 */
function toFiniteNumber(value) {
  if (value === null || value === undefined || value === '') return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

/**
 * 字节 → 人类可读体积。
 * @param {unknown} bytes
 * @param {{ fallback?: string }} [options] 非法值或 0 时返回该占位符（默认「大小未知」；表格里通常传 "-"，统计卡片传 "0 B"）
 */
export function formatFileSize(bytes, { fallback = '大小未知' } = {}) {
  const value = toFiniteNumber(bytes)
  if (value === null || value <= 0) return fallback
  if (value < 1024) return `${Math.round(value)} B`
  for (const unit of UNITS) {
    if (value >= unit.limit) return `${(value / unit.limit).toFixed(unit.digits)} ${unit.suffix}`
  }
  return `${(value / 1024).toFixed(1)} KB`
}

/**
 * 秒 → `mm:ss`（超过 1 小时进位为 `h:mm:ss`）。音频时间轴专用。
 * 缺数据按 0 处理（进度条上显示 `0:00` 比空白更合理）；
 * 要展示"总时长"这类文案请用 formatDurationText。
 */
export function formatClock(seconds) {
  const total = toFiniteNumber(seconds)
  const s = Math.max(0, Math.floor(total ?? 0))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const r = s % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}`
  return `${m}:${String(r).padStart(2, '0')}`
}

/**
 * 秒 → `1 小时 2 分 3 秒` / `2 分 3 秒` / `42 秒`。
 * @param {unknown} seconds
 * @param {{ withSeconds?: boolean, fallback?: string }} [options]
 *   withSeconds=false 用于"总时长"这类不需要秒级精度的场景（`3 小时 25 分`）
 */
export function formatDurationText(seconds, { withSeconds = true, fallback = '-' } = {}) {
  const total = toFiniteNumber(seconds)
  if (total === null || total < 0) return fallback
  const s = Math.floor(total)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const rest = s % 60
  if (!withSeconds) {
    if (h) return `${h} 小时 ${m} 分`
    if (m) return `${m} 分钟`
    return `${rest} 秒`
  }
  if (h) return `${h} 小时 ${m} 分 ${rest} 秒`
  if (m) return `${m} 分 ${rest} 秒`
  return `${rest} 秒`
}

/**
 * 距今多少秒 → `3 分钟前`。
 * @param {unknown} seconds 已经过去的秒数
 * @param {{ coarse?: boolean, fallback?: string }} [options]
 *   coarse=true 用于活动流这类"大概多久前"的场景：`刚刚 / 3 分钟前 / 3 小时前 / 2 天前`
 *   （默认精确到秒与分，用于任务心跳这种需要判断是否卡死的场景）
 */
export function formatRelativeTime(seconds, { coarse = false, fallback = '' } = {}) {
  const total = toFiniteNumber(seconds)
  if (total === null || total < 0) return fallback
  const s = Math.round(total)
  if (coarse) {
    if (s < 60) return '刚刚'
    const m = Math.floor(s / 60)
    if (m < 60) return `${m} 分钟前`
    const h = Math.floor(m / 60)
    if (h < 24) return `${h} 小时前`
    return `${Math.floor(h / 24)} 天前`
  }
  if (s < 60) return `${s} 秒前`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m} 分钟前`
  const h = Math.floor(m / 60)
  return `${h} 小时 ${m % 60} 分钟前`
}

/**
 * 两个时间点之间的秒数。endAt 省略时取"现在"。
 * 解析失败返回 null，由调用方决定占位符 —— 避免各页面各写一遍 new Date().getTime() 的容错。
 */
export function secondsBetween(startAt, endAt = null) {
  if (!startAt) return null
  const start = new Date(startAt).getTime()
  if (Number.isNaN(start)) return null
  const end = endAt ? new Date(endAt).getTime() : Date.now()
  if (Number.isNaN(end)) return null
  return Math.max(0, Math.round((end - start) / 1000))
}

/**
 * 时刻 → 本地时间字符串。
 * @param {unknown} value ISO 字符串或时间戳
 * @param {{ withSeconds?: boolean, withYear?: boolean, fallback?: string }} [options]
 */
export function formatDateTime(value, { withSeconds = true, withYear = false, fallback = '—' } = {}) {
  if (!value) return fallback
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return fallback
  return date.toLocaleString('zh-CN', {
    ...(withYear ? { year: 'numeric' } : {}),
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    ...(withSeconds ? { second: '2-digit' } : {}),
  })
}

/**
 * 时刻 → 仅时间部分 `HH:mm:ss`（日志行内用）。
 * @param {unknown} value ISO 字符串或时间戳
 */
export function formatTimeOfDay(value, { fallback = '' } = {}) {
  if (!value) return fallback
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return fallback
  return date.toLocaleTimeString('zh-CN', { hour12: false })
}
