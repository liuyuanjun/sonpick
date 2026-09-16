import { formatFileSize } from './format.js'
import { formatLabel, versionLocationLabel } from './media.js'

export function normalizeSongFiles(files) {
  if (!Array.isArray(files)) return []
  return files.map((item) => {
    const localPath = item.local_path || (item.location === 'local' ? item.path : '')
    const remotePath = item.webdav_path || (item.location === 'webdav' ? item.path : '')
    const writable = item.writable ?? Boolean(localPath)
    return {
      ...item,
      writable,
      displayFormat: formatLabel(item.format, '未知格式'),
      displayPath: item.path || localPath || remotePath || '位置未知',
      displaySource: item.source_name || versionLocationLabel(item),
      displaySize: formatFileSize(item.file_size),
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
