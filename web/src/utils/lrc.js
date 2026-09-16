/**
 * Parse LRC lyrics into [{ time, text }] sorted by time (seconds).
 */
export function parseLrc(raw) {
  if (!raw) return []
  const re = /\[(\d{1,2}):(\d{1,2})(?:[.:](\d{1,3}))?\](.*)/g
  const lines = []
  for (const line of String(raw).split(/\r?\n/)) {
    let m
    const textLine = line.trim()
    if (!textLine) continue
    re.lastIndex = 0
    while ((m = re.exec(textLine)) !== null) {
      const minutes = Number(m[1])
      const seconds = Number(m[2])
      const frac = m[3] || '0'
      let fracSec = 0
      if (frac.length === 1) fracSec = Number(frac) / 10
      else if (frac.length === 2) fracSec = Number(frac) / 100
      else fracSec = Number(frac.slice(0, 3)) / 1000
      const text = (m[4] || '').trim()
      if (!text) continue
      lines.push({ time: minutes * 60 + seconds + fracSec, text })
    }
  }
  lines.sort((a, b) => a.time - b.time)
  return lines
}

/** Binary-search the active lyric index for currentTime. */
export function findLyricIndex(lines, currentTime) {
  if (!lines?.length) return -1
  let lo = 0
  let hi = lines.length - 1
  let ans = -1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (lines[mid].time <= currentTime + 0.05) {
      ans = mid
      lo = mid + 1
    } else {
      hi = mid - 1
    }
  }
  return ans
}

// 时间轴格式化（原 formatTime）已统一到 utils/format.js 的 formatClock()：
// 歌词解析与格式化本属两件事，混在一个文件里会让别处也来 import lrc 拿格式化函数。
