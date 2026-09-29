import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/api/client'

/**
 * 全局设置的共享缓存。
 *
 * 只放「别的模块也要读」的那几项；各设置页的表单仍自己拉 `/settings`（免得为一个字段
 * 把整张表单塞进 store）。这里的值是**只读快照**：改了设置后由设置页调 `refresh()` 同步回来。
 */

/** 与后端 `AppSettings.recent_play_threshold_s` 的默认值保持一致（3 秒） */
export const DEFAULT_RECENT_PLAY_THRESHOLD_S = 3

export const useSettingsStore = defineStore('settings', () => {
  /**
   * 播放阈值（秒）：累计真实播放时长达标才计入最近播放。
   * 加载完成前用默认值兜底，所以播放逻辑不必等接口。
   */
  const recentPlayThresholdS = ref(DEFAULT_RECENT_PLAY_THRESHOLD_S)

  let inflight = null

  function applyPayload(data) {
    const value = Number(data?.recent_play_threshold_s)
    if (Number.isFinite(value) && value >= 0) recentPlayThresholdS.value = value
  }

  async function refresh() {
    const res = await api.get('/settings')
    applyPayload(res.data)
    return res.data
  }

  /**
   * 幂等加载：多处调用只发一次请求。
   * 失败静默 —— 拿不到设置时保留默认阈值，不该因此挡住播放。
   */
  function ensure() {
    if (!inflight) {
      inflight = refresh().catch(() => {})
    }
    return inflight
  }

  return { recentPlayThresholdS, applyPayload, refresh, ensure }
})
