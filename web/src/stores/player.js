import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { fetchLyrics, recordPlay, streamUrl, coverUrl, scrapeSongs, waitTask } from '@/api/music'
import { useAuthStore } from '@/stores/auth'
import { useIsMobile } from '@/composables/useIsMobile'
import { findLyricIndex, parseLrc } from '@/utils/lrc'

const MODES = ['order', 'loop', 'single', 'shuffle']
const MODE_LABELS = {
  order: '顺序播放',
  loop: '列表循环',
  single: '单曲循环',
  shuffle: '随机播放',
}

/**
 * 播放器页的二级列表（路由 /player/:section）。
 * 侧边栏菜单、移动端横向 Tab、路由校验都从这里取，避免多处各写一份。
 */
export const PLAYER_SECTIONS = ['favorites', 'playlists', 'artists', 'albums', 'songs', 'history']

export function normalizePlayerSection(value) {
  return PLAYER_SECTIONS.includes(value) ? value : 'favorites'
}

function clampLyricFontSize(size) {
  const n = Number(size)
  if (Number.isNaN(n)) return 18
  return Math.min(28, Math.max(14, Math.round(n)))
}

function normalizeStageView(view) {
  return ['cover', 'blend', 'lyrics'].includes(view) ? view : 'cover'
}

function legacyStageView() {
  // 兼容旧 key sonpick-show-lyrics
  return localStorage.getItem('sonpick-show-lyrics') === '1' ? 'lyrics' : 'cover'
}

/**
 * 播放器皮肤（一套完整布局方案），注册表驱动、可扩展，用户可选并持久化。
 * skin 即布局，不再有单独的"内容视图"切换。每个皮肤自带响应式处理。
 *   card   叠层卡：左播放卡（封面/元信息/控制）+ 右歌词（默认，飞牛式）— 仅桌面
 *   vinyl  唱片：巨大旋转唱片挂右上出血作背景 + 左侧歌词（保留原窄屏风格）
 *   lyrics 纯歌词：整幅模糊封面铺底 + 居中歌词
 *   art    纯封面：大封面居中（无歌词）
 * desktopOnly：竖屏手机放不下两栏，叠层卡在移动端隐藏（移动端用封面/歌词这两个单栏皮肤）。
 */
export const PLAYER_SKINS = [
  { id: 'card', label: '叠层卡', hasLyrics: true, desktopOnly: true },
  { id: 'vinyl', label: '唱片', hasLyrics: true },
  { id: 'lyrics', label: '歌词', hasLyrics: true },
  { id: 'art', label: '封面', hasLyrics: false },
]
const PLAYER_SKIN_IDS = new Set(PLAYER_SKINS.map((s) => s.id))
const PLAYER_SKIN_MAP = Object.fromEntries(PLAYER_SKINS.map((s) => [s.id, s]))
export const DEFAULT_PLAYER_SKIN = 'card'
// 移动端兜底皮肤：叠层卡不可用时落到纯歌词（本身带封面模糊底，最接近"封面+歌词"的沉浸感）
export const DEFAULT_PLAYER_SKIN_MOBILE = 'lyrics'

export function normalizePlayerSkin(id) {
  return PLAYER_SKIN_IDS.has(id) ? id : DEFAULT_PLAYER_SKIN
}

// 旧 stageView（cover/blend/lyrics）→ 皮肤：有歌词的两种并到叠层卡，纯歌词并到歌词皮肤
function migrateLegacySkin() {
  const legacy = normalizeStageView(localStorage.getItem('sonpick-stage-view') || legacyStageView())
  return legacy === 'lyrics' ? 'lyrics' : DEFAULT_PLAYER_SKIN
}

export const usePlayerStore = defineStore('player', () => {
  const current = ref(null)
  const src = ref('')
  const cover = ref('')
  const playing = ref(false)
  const showPlayer = ref(false)
  const queue = ref([])
  const currentIndex = ref(-1)
  const playHistory = ref([])
  const historyIndex = ref(-1)
  const mode = ref(localStorage.getItem('sonpick-play-mode') || 'loop')
  const losslessPreferred = ref(localStorage.getItem('sonpick-lossless-preferred') === '1')
  const volume = ref(Number(localStorage.getItem('sonpick-volume') ?? 0.8))
  const muted = ref(false)
  const currentTime = ref(0)
  const duration = ref(0)
  const lyrics = ref([])
  const lyricsMeta = ref({ type: null, provider: null, sourceId: null, fetchedAt: null, instrumental: false })
  const lyricIndex = ref(-1)
  const showQueue = ref(false)
  const expanded = ref(false)
  // 移动端全屏「正在播放」浮层开关（桌面端不使用）
  const fullPlayerOpen = ref(false)
  // 舞台皮肤：叠层卡 | 唱片 | 歌词 | 封面（持久化，切歌保留）
  const playerSkin = ref(normalizePlayerSkin(localStorage.getItem('sonpick-player-skin') || migrateLegacySkin()))
  // 歌词字号（px），默认 22（宽屏大播放器下的舒适阅读档位；老用户读本地存档不受影响）
  const lyricFontSize = ref(clampLyricFontSize(Number(localStorage.getItem('sonpick-lyric-font-size') ?? 22)))
  // 皮肤可用集合按视口收敛：桌面全部；移动端隐藏 desktopOnly 的叠层卡（竖屏放不下两栏）
  const isMobile = useIsMobile()
  const availableSkins = computed(() => PLAYER_SKINS.filter((s) => !s.desktopOnly || !isMobile.value))
  // 实际生效的皮肤：持久化的偏好若在当前视口不可用，落到该视口的默认皮肤（不覆盖用户偏好）
  const effectiveSkinId = computed(() => {
    const ids = availableSkins.value.map((s) => s.id)
    if (ids.includes(playerSkin.value)) return playerSkin.value
    return isMobile.value ? DEFAULT_PLAYER_SKIN_MOBILE : DEFAULT_PLAYER_SKIN
  })
  const currentSkin = computed(() => PLAYER_SKIN_MAP[effectiveSkinId.value] || PLAYER_SKIN_MAP[DEFAULT_PLAYER_SKIN])
  const showLyrics = computed(() => currentSkin.value.hasLyrics)

  const modeLabel = computed(() => MODE_LABELS[mode.value] || MODE_LABELS.loop)
  const hasPrev = computed(() => queue.value.length > 0)
  const hasNext = computed(() => queue.value.length > 0)

  function token() {
    return useAuthStore().token || ''
  }

  function toggleLosslessPreferred() {
    losslessPreferred.value = !losslessPreferred.value
    if (current.value?.id) src.value = streamUrl(current.value.id, token(), losslessPreferred.value)
  }

  let lyricsRequestSeq = 0

  function applySong(song, autoplay = true) {
    if (!song?.id) return
    current.value = song
    src.value = streamUrl(song.id, token(), losslessPreferred.value)
    // 有 song id 即尝试拉封面；L0 无图时 /cover 404，由 UI onerror 占位
    cover.value = song.id ? coverUrl(song.id, token()) : ''
    showPlayer.value = true
    playing.value = !!autoplay
    currentTime.value = 0
    duration.value = song.duration || 0
    lyricIndex.value = -1
    lyrics.value = []
    const requestSeq = ++lyricsRequestSeq
    loadLyrics(song.id, requestSeq)
    recordPlay(song.id).catch(() => {})
  }

  async function scrapeCurrent(options = {}) {
    const song = current.value
    if (!song?.id) throw new Error('当前没有播放中的歌曲')
    const res = await scrapeSongs({
      song_ids: [song.id],
      async_mode: true,
      allow_network: options.allow_network !== false,
      write_file_tags: options.write_file_tags !== false,
      overwrite: !!options.overwrite,
      limit: 1,
    })
    return res.data || res || {}
  }

  async function waitScrapeTask(taskId, { onProgress } = {}) {
    return waitTask(taskId, {
      timeoutMs: 15 * 60 * 1000,
      onProgress,
    })
  }

  async function loadLyrics(songId, requestSeq = ++lyricsRequestSeq) {
    try {
      const res = await fetchLyrics(songId)
      if (requestSeq !== lyricsRequestSeq || current.value?.id !== songId) return false
      const data = res?.data || res || {}
      let lines = Array.isArray(data?.lines) ? data.lines : []
      if (!lines.length && data?.raw) lines = parseLrc(data.raw)
      lyrics.value = lines
      lyricsMeta.value = {
        type: data.lyrics_type || current.value?.lyrics_type || null,
        provider: data.provider || current.value?.lyrics_provider || null,
        sourceId: data.source_id || current.value?.lyrics_source_id || null,
        fetchedAt: data.fetched_at || current.value?.lyrics_fetched_at || null,
        instrumental: !!data.instrumental || current.value?.lyrics_type === 'instrumental',
      }
      lyricIndex.value = findLyricIndex(lyrics.value, currentTime.value)
      return true
    } catch {
      if (requestSeq !== lyricsRequestSeq || current.value?.id !== songId) return false
      lyrics.value = []
      lyricsMeta.value = { type: null, provider: null, sourceId: null, fetchedAt: null, instrumental: false }
      lyricIndex.value = -1
      return false
    }
  }

  function play(song, list = null) {
    if (list && Array.isArray(list) && list.length) {
      queue.value = list.slice()
      currentIndex.value = Math.max(0, list.findIndex((s) => s.id === song.id))
      if (currentIndex.value < 0) {
        queue.value.unshift(song)
        currentIndex.value = 0
      }
    } else {
      const idx = queue.value.findIndex((s) => s.id === song.id)
      if (idx >= 0) currentIndex.value = idx
      else {
        queue.value.push(song)
        currentIndex.value = queue.value.length - 1
      }
    }
    playHistory.value = [song]
    historyIndex.value = 0
    applySong(song, true)
  }

  function playList(list, startIndex = 0) {
    if (!list?.length) return
    queue.value = list.slice()
    currentIndex.value = Math.min(Math.max(0, startIndex), queue.value.length - 1)
    playHistory.value = [queue.value[currentIndex.value]]
    historyIndex.value = 0
    applySong(queue.value[currentIndex.value], true)
  }

  function shuffleSongs(list) {
    const shuffled = list.slice()
    for (let i = shuffled.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]]
    }
    return shuffled
  }

  function playShuffledList(list) {
    if (!list?.length) return
    mode.value = 'shuffle'
    playList(shuffleSongs(list), 0)
  }

  function enqueue(song) {
    if (!song?.id) return
    if (!queue.value.some((s) => s.id === song.id)) queue.value.push(song)
  }

  function removeFromQueue(index) {
    if (index < 0 || index >= queue.value.length) return
    const removingCurrent = index === currentIndex.value
    queue.value.splice(index, 1)
    if (!queue.value.length) {
      close()
      return
    }
    if (index < currentIndex.value) currentIndex.value -= 1
    else if (removingCurrent) {
      currentIndex.value = Math.min(index, queue.value.length - 1)
      applySong(queue.value[currentIndex.value], playing.value)
    }
  }

  function clearQueue() {
    queue.value = current.value ? [current.value] : []
    currentIndex.value = current.value ? 0 : -1
  }

  function jumpTo(index) {
    if (index < 0 || index >= queue.value.length) return
    currentIndex.value = index
    if (historyIndex.value < playHistory.value.length - 1) {
      playHistory.value = playHistory.value.slice(0, historyIndex.value + 1)
    }
    playHistory.value.push(queue.value[index])
    historyIndex.value = playHistory.value.length - 1
    applySong(queue.value[index], true)
  }

  function recordHistory(song) {
    if (!song?.id) return
    if (historyIndex.value < playHistory.value.length - 1) {
      playHistory.value = playHistory.value.slice(0, historyIndex.value + 1)
    }
    if (playHistory.value.at(-1)?.id !== song.id) playHistory.value.push(song)
    if (playHistory.value.length > 1000) playHistory.value.shift()
    historyIndex.value = playHistory.value.length - 1
  }

  function next() {
    if (!queue.value.length) return
    if (historyIndex.value < playHistory.value.length - 1) {
      historyIndex.value += 1
      const song = playHistory.value[historyIndex.value]
      currentIndex.value = queue.value.findIndex((item) => item.id === song.id)
      applySong(song, true)
      return
    }
    if (mode.value === 'single') {
      applySong(queue.value[currentIndex.value], true)
      return
    }
    let nextIdx = currentIndex.value + 1
    if (nextIdx >= queue.value.length) {
      if (mode.value === 'shuffle') {
        const previousId = current.value?.id
        queue.value = shuffleSongs(queue.value)
        if (queue.value.length > 1 && queue.value[0]?.id === previousId) {
          ;[queue.value[0], queue.value[1]] = [queue.value[1], queue.value[0]]
        }
        nextIdx = 0
      } else if (mode.value === 'loop') nextIdx = 0
      else {
        playing.value = false
        return
      }
    }
    currentIndex.value = nextIdx
    recordHistory(queue.value[nextIdx])
    applySong(queue.value[nextIdx], true)
  }

  function prev() {
    if (!queue.value.length || historyIndex.value <= 0) return
    historyIndex.value -= 1
    const song = playHistory.value[historyIndex.value]
    currentIndex.value = queue.value.findIndex((item) => item.id === song.id)
    applySong(song, true)
  }

  function toggleMode() {
    const idx = MODES.indexOf(mode.value)
    mode.value = MODES[(idx + 1) % MODES.length]
  }

  function setVolume(v) {
    volume.value = Math.min(1, Math.max(0, Number(v) || 0))
    if (volume.value > 0) muted.value = false
    localStorage.setItem('sonpick-volume', String(volume.value))
  }

  function toggleMute() {
    muted.value = !muted.value
  }

  function pause() {
    playing.value = false
  }

  function resume() {
    if (current.value) playing.value = true
  }

  function togglePlay() {
    if (!current.value) return
    playing.value = !playing.value
  }

  // UI 兼容别名：部分组件可能调用 player.toggle()
  function toggle() {
    togglePlay()
  }

  function setProgress(time, total) {
    currentTime.value = Number(time) || 0
    const d = Number(total)
    if (Number.isFinite(d) && d > 0) duration.value = d
    lyricIndex.value = findLyricIndex(lyrics.value, currentTime.value)
  }

  function setPlayerSkin(id) {
    const next = normalizePlayerSkin(id)
    // 只接受当前视口可用的皮肤（移动端不接受 desktopOnly 的叠层卡）
    if (!availableSkins.value.some((s) => s.id === next)) return
    playerSkin.value = next
  }

  function setLyricFontSize(size) {
    lyricFontSize.value = clampLyricFontSize(size)
  }

  function close() {
    lyricsRequestSeq += 1
    current.value = null
    src.value = ''
    cover.value = ''
    playing.value = false
    showPlayer.value = false
    queue.value = []
    currentIndex.value = -1
    playHistory.value = []
    historyIndex.value = -1
    lyrics.value = []
    lyricsMeta.value = { type: null, provider: null, sourceId: null, fetchedAt: null, instrumental: false }
    lyricIndex.value = -1
    currentTime.value = 0
    duration.value = 0
    expanded.value = false
    showQueue.value = false
    fullPlayerOpen.value = false
  }

  watch(mode, (v) => localStorage.setItem('sonpick-play-mode', v))
  watch(losslessPreferred, (v) => localStorage.setItem('sonpick-lossless-preferred', v ? '1' : '0'))
  watch(playerSkin, (v) => localStorage.setItem('sonpick-player-skin', normalizePlayerSkin(v)))
  watch(lyricFontSize, (v) => localStorage.setItem('sonpick-lyric-font-size', String(v)))

  return {
    current, src, cover, playing, showPlayer, queue, currentIndex, mode, modeLabel,
    losslessPreferred,
    volume, muted, currentTime, duration, lyrics, lyricsMeta, lyricIndex, showQueue, expanded, fullPlayerOpen,
    playerSkin, availableSkins, currentSkin, showLyrics, lyricFontSize,
    hasPrev, hasNext, play, playList, playShuffledList, enqueue, removeFromQueue, clearQueue, jumpTo,
    next, prev, toggleMode, toggleLosslessPreferred, setVolume, toggleMute, pause, resume, togglePlay, toggle,
    setProgress, setPlayerSkin, setLyricFontSize, loadLyrics,
    scrapeCurrent, waitScrapeTask, close,
  }
})
