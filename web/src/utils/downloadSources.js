// 下载源清单（与后端 light_search_service.DEFAULT_DOWNLOAD_SOURCES / SOURCE_LABELS 对应，改一边必须改另一边）
//
// 展示名一律用**平台简称**（QQ / 网易云 / 咪咕 / 酷狗 / 酷我 / 千千），不加「音乐」后缀：
// 下载来源 chips、搜索结果「来源」列、后端错误提示三处同源，别再各写一份清单。
export const DOWNLOAD_SOURCES = [
  { value: 'QQMusicClient', label: 'QQ' },
  { value: 'NeteaseMusicClient', label: '网易云' },
  { value: 'MiguMusicClient', label: '咪咕' },
  { value: 'KugouMusicClient', label: '酷狗' },
  { value: 'KuwoMusicClient', label: '酷我' },
  { value: 'QianqianMusicClient', label: '千千' },
]

/** 源 key（`QQMusicClient`…）→ 展示名；未知 key 原样返回，便于排查新源没登记 */
export function sourceLabel(value) {
  if (!value) return ''
  return DOWNLOAD_SOURCES.find((s) => s.value === value)?.label || String(value)
}

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
