import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { fetchPlaylists } from '@/api/music'

/**
 * 歌单列表的共享缓存。
 *
 * 三个使用方都读它，避免各自拉一遍、也避免顺序不一致：
 *   · 侧边栏「歌单」子菜单（取排序后的前 N 个）
 *   · 播放器「歌单」区（完整列表）
 *   · 管理歌单页（拖拽排序后把新顺序写回这里）
 */

/** 侧边栏「歌单」子菜单最多列几个（子菜单只放歌单；「管理歌单」入口在歌单区页头） */
export const SIDEBAR_PLAYLIST_COUNT = 5

export const usePlaylistsStore = defineStore('playlists', () => {
  const items = ref([])
  const loading = ref(false)
  const loaded = ref(false)

  /** 侧边栏子菜单用：排序后的前几个 */
  const forSidebar = computed(() => items.value.slice(0, SIDEBAR_PLAYLIST_COUNT))

  /** 直接采用后端返回的列表（顺序即后端的 sort_order），供排序接口回填 */
  function apply(list) {
    items.value = Array.isArray(list) ? list : []
    loaded.value = true
  }

  async function refresh() {
    loading.value = true
    try {
      const res = await fetchPlaylists()
      apply(res.data)
      return items.value
    } finally {
      loading.value = false
    }
  }

  /** 幂等加载：侧边栏挂载时调一次，失败静默（不因为歌单拉不到就整个导航报错） */
  function ensure() {
    if (loaded.value || loading.value) return
    refresh().catch(() => {})
  }

  return { items, loading, loaded, forSidebar, apply, refresh, ensure }
})
