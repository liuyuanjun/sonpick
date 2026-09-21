// 批量导入歌单文本解析：非空行保序去重
export function parseBatchLines(text) {
  const seen = new Set()
  const lines = []
  for (const raw of String(text || '').split('\n')) {
    const line = raw.trim()
    if (!line || seen.has(line)) continue
    seen.add(line)
    lines.push(line)
  }
  return lines
}

// 原始非空行数（含重复），用于「共 N 行，去重后 M 首」提示
export function countBatchLines(text) {
  const raw = String(text || '')
    .split('\n')
    .filter((l) => l.trim()).length
  return { raw, unique: parseBatchLines(text).length }
}
