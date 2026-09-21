// 下载源清单（与后端 light_search_service.DEFAULT_DOWNLOAD_SOURCES / SOURCE_LABELS 对应，改一边必须改另一边）
export const DOWNLOAD_SOURCES = [
  { value: 'QQMusicClient', label: 'QQ 音乐' },
  { value: 'NeteaseMusicClient', label: '网易云音乐' },
  { value: 'MiguMusicClient', label: '咪咕音乐' },
  { value: 'KugouMusicClient', label: '酷狗音乐' },
  { value: 'KuwoMusicClient', label: '酷我音乐' },
  { value: 'QianqianMusicClient', label: '千千音乐' },
]

const STORAGE_KEY = 'sonpick_download_sources'

// 读取持久化的已选源（有序）；非法/未知项剔除，全空回退默认全选
export function loadSourcePref() {
  const allowed = new Set(DOWNLOAD_SOURCES.map((s) => s.value))
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')
    if (Array.isArray(saved)) {
      const valid = saved.filter((v) => allowed.has(v))
      if (valid.length) return valid
      if (saved.length) return [] // 用户曾显式清空（虽不建议），尊重其选择
    }
  } catch (_) {
    /* 损坏的本地数据按默认处理 */
  }
  return DOWNLOAD_SOURCES.map((s) => s.value)
}

export function saveSourcePref(list) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list || []))
  } catch (_) {
    /* 隐私模式等场景静默失败，不影响当次使用 */
  }
}
