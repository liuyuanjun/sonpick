export function formatSongFileSize(bytes) {
  const value = Number(bytes)
  if (!Number.isFinite(value) || value < 0) return '大小未知'
  if (value < 1024) return `${value} B`
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 ** 2).toFixed(2)} MB`
}

export function normalizeSongFiles(files) {
  if (!Array.isArray(files)) return []
  return files.map((item) => {
    const localPath = item.local_path || (item.location === 'local' ? item.path : '')
    const remotePath = item.webdav_path || (item.location === 'webdav' ? item.path : '')
    const writable = item.writable ?? Boolean(localPath)
    return {
      ...item,
      writable,
      displayFormat: String(item.format || '未知格式').toUpperCase(),
      displayPath: item.path || localPath || remotePath || '位置未知',
      displaySource: item.source_name || (remotePath ? 'WebDAV' : '本地'),
      displaySize: formatSongFileSize(item.file_size),
      displayStatus: item.write_status || (writable ? '可写入本地文件' : (remotePath ? '远端只读，未写入' : '本地文件不可用')),
    }
  })
}

export function normalizedScrapeValue(value) {
  return value == null ? '' : String(value).trim()
}

export function shouldSelectScrapeField({ key, currentValue, newValue, currentCoverExists = false }) {
  const normalizedNewValue = normalizedScrapeValue(newValue)
  if (!normalizedNewValue) return false
  if (key === 'cover') return !currentCoverExists
  return normalizedNewValue !== normalizedScrapeValue(currentValue)
}
