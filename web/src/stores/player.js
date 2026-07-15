import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { fetchLyrics, recordPlay, streamUrl, coverUrl, scrapeSongs, waitTask } from '@/api/music'
import { useAuthStore } from '@/stores/auth'
import { findLyricIndex, parseLrc } from '@/utils/lrc'

const MODES = ['order', 'loop', 'single', 'shuffle']
const MODE_LABELS = {
  order: '顺序播放',
  loop: '列表循环',
  single: '单曲循环',
  shuffle: '随机播放',
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

export const usePlayerStore = defineStore('player', () => {
  const current = ref(null)
  const src = ref('')
  const cover = ref('')
  const playing = ref(false)
  const showPlayer = ref(false)
  const queue = ref([])
  const currentIndex = ref(-1)
  const mode = ref(localStorage.getItem('sonpick-play-mode') || 'loop')
  const volume = ref(Number(localStorage.getItem('sonpick-volume') ?? 0.8))
  const muted = ref(false)
  const currentTime = ref(0)
  const duration = ref(0)
  const lyrics = ref([])
  const lyricIndex = ref(-1)
  const showQueue = ref(false)
  const expanded = ref(false)
  // 舞台视图：cover | blend | lyrics（切歌保留）
  const stageView = ref(normalizeStageView(localStorage.getItem('sonpick-stage-view') || legacyStageView()))
  // 歌词字号（px），默认比原先略大
  const lyricFontSize = ref(clampLyricFontSize(Number(localStorage.getItem('sonpick-lyric-font-size') ?? 18)))
  const showLyrics = computed(() => stageView.value !== 'cover')

  const modeLabel = computed(() => MODE_LABELS[mode.value] || MODE_LABELS.loop)
  const hasPrev = computed(() => queue.value.length > 0)
  const hasNext = computed(() => queue.value.length > 0)

  function token() {
    return useAuthStore().token || ''
  }

  function applySong(song, autoplay = true) {
    if (!song?.id) return
    current.value = song
    src.value = streamUrl(song.id, token())
    cover.value = song.cover_path ? coverUrl(song.id, token()) : ''
    showPlayer.value = true
    playing.value = !!autoplay
    currentTime.value = 0
    duration.value = song.duration || 0
    lyricIndex.value = -1
    lyrics.value = []
    loadLyrics(song.id)
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

  async function loadLyrics(songId) {
    try {
      const res = await fetchLyrics(songId)
      const data = res?.data || res || {}
      // API: { lines:[{time,text}], raw }
      let lines = Array.isArray(data?.lines) ? data.lines : []
      if (!lines.length && data?.raw) lines = parseLrc(data.raw)
      lyrics.value = lines
      lyricIndex.value = findLyricIndex(lyrics.value, currentTime.value)
    } catch {
      lyrics.value = []
      lyricIndex.value = -1
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
    applySong(song, true)
  }

  function playList(list, startIndex = 0) {
    if (!list?.length) return
    queue.value = list.slice()
    currentIndex.value = Math.min(Math.max(0, startIndex), queue.value.length - 1)
    applySong(queue.value[currentIndex.value], true)
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
    applySong(queue.value[index], true)
  }

  function next() {
    if (!queue.value.length) return
    if (mode.value === 'single') {
      applySong(queue.value[currentIndex.value], true)
      return
    }
    if (mode.value === 'shuffle') {
      if (queue.value.length === 1) {
        applySong(queue.value[0], true)
        return
      }
      let nextIdx = currentIndex.value
      while (nextIdx === currentIndex.value) {
        nextIdx = Math.floor(Math.random() * queue.value.length)
      }
      currentIndex.value = nextIdx
      applySong(queue.value[nextIdx], true)
      return
    }
    let nextIdx = currentIndex.value + 1
    if (nextIdx >= queue.value.length) {
      if (mode.value === 'loop') nextIdx = 0
      else {
        playing.value = false
        return
      }
    }
    currentIndex.value = nextIdx
    applySong(queue.value[nextIdx], true)
  }

  function prev() {
    if (!queue.value.length) return
    if (currentTime.value > 3) {
      window.dispatchEvent(new CustomEvent('sonpick-seek', { detail: 0 }))
      return
    }
    if (mode.value === 'shuffle') {
      next()
      return
    }
    let prevIdx = currentIndex.value - 1
    if (prevIdx < 0) {
      if (mode.value === 'loop') prevIdx = queue.value.length - 1
      else prevIdx = 0
    }
    currentIndex.value = prevIdx
    applySong(queue.value[prevIdx], true)
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
    currentTime.value = time
    if (total && !Number.isNaN(total)) duration.value = total
    lyricIndex.value = findLyricIndex(lyrics.value, time)
  }

  function setStageView(view) {
    stageView.value = normalizeStageView(view)
  }

  function cycleStageView() {
    const order = ['cover', 'blend', 'lyrics']
    const idx = order.indexOf(stageView.value)
    stageView.value = order[(idx + 1) % order.length]
  }

  // 兼容旧调用：true→歌词纯净，false→封面
  function setShowLyrics(val) {
    stageView.value = val ? 'lyrics' : 'cover'
  }

  function toggleShowLyrics() {
    cycleStageView()
  }

  function setLyricFontSize(size) {
    lyricFontSize.value = clampLyricFontSize(size)
  }

  function close() {
    current.value = null
    src.value = ''
    cover.value = ''
    playing.value = false
    showPlayer.value = false
    queue.value = []
    currentIndex.value = -1
    lyrics.value = []
    lyricIndex.value = -1
    currentTime.value = 0
    duration.value = 0
    expanded.value = false
    showQueue.value = false
  }

  watch(mode, (v) => localStorage.setItem('sonpick-play-mode', v))
  watch(stageView, (v) => localStorage.setItem('sonpick-stage-view', normalizeStageView(v)))
  watch(lyricFontSize, (v) => localStorage.setItem('sonpick-lyric-font-size', String(v)))

  return {
    current, src, cover, playing, showPlayer, queue, currentIndex, mode, modeLabel,
    volume, muted, currentTime, duration, lyrics, lyricIndex, showQueue, expanded,
    stageView, showLyrics, lyricFontSize,
    hasPrev, hasNext, play, playList, enqueue, removeFromQueue, clearQueue, jumpTo,
    next, prev, toggleMode, setVolume, toggleMute, pause, resume, togglePlay, toggle,
    setProgress, setStageView, cycleStageView, setShowLyrics, toggleShowLyrics, setLyricFontSize, loadLyrics,
    scrapeCurrent, waitScrapeTask, close,
  }
})
