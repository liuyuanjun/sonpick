import { watch } from 'vue'

// Media Session 集成：把系统媒体命令（macOS 线控/媒体键、蓝牙耳机、锁屏/控制中心）
// 对接到播放器 store。
// 注意：网页收不到线控的原始按键次数，macOS/iOS/Android 会由系统翻译为媒体命令——
// 单击中键 = 播放/暂停，双击 = nexttrack，三击 = previoustrack；这里注册对应 handler 即可。
export function useMediaSession(player, audioRef) {
  const supported = typeof navigator !== 'undefined' && 'mediaSession' in navigator

  function absoluteUrl(url) {
    if (!url) return ''
    try {
      return new URL(url, window.location.href).href
    } catch {
      return ''
    }
  }

  function updateMetadata() {
    if (!supported) return
    const song = player.current
    if (!song) {
      navigator.mediaSession.metadata = null
      return
    }
    const artworkUrl = absoluteUrl(player.cover)
    navigator.mediaSession.metadata = new MediaMetadata({
      title: song.title || '未知歌曲',
      artist: song.artist || '',
      album: song.album || '',
      artwork: artworkUrl ? [{ src: artworkUrl, sizes: '512x512' }] : [],
    })
  }

  function updatePlaybackState() {
    if (!supported) return
    if (!player.current) {
      navigator.mediaSession.playbackState = 'none'
      return
    }
    navigator.mediaSession.playbackState = player.playing ? 'playing' : 'paused'
  }

  // Chrome 对非法 position state（NaN / position > duration）直接抛异常，需防御
  function updatePositionState() {
    if (!supported || typeof navigator.mediaSession.setPositionState !== 'function') return
    const el = audioRef.value
    const duration = Number(el?.duration ?? player.duration)
    if (!Number.isFinite(duration) || duration <= 0) return
    const raw = Number(el?.currentTime ?? player.currentTime) || 0
    const position = Math.min(Math.max(0, raw), duration)
    try {
      navigator.mediaSession.setPositionState({
        duration,
        position,
        playbackRate: el?.playbackRate || 1,
      })
    } catch {
      /* 忽略个别浏览器对边界值的拒绝 */
    }
  }

  function seekTo(time) {
    const el = audioRef.value
    if (!el || !Number.isFinite(time)) return
    const dur = Number(el.duration)
    el.currentTime = Number.isFinite(dur) && dur > 0 ? Math.min(Math.max(0, time), dur) : Math.max(0, time)
    player.setProgress(el.currentTime, el.duration || player.duration || 0)
    updatePositionState()
  }

  if (supported) {
    // play/pause 必须显式注册：一旦设置任意 action handler，
    // 部分浏览器会停用内置默认处理，显式注册可保住线控单击的既有行为
    navigator.mediaSession.setActionHandler('play', () => {
      player.resume()
      updatePlaybackState()
    })
    navigator.mediaSession.setActionHandler('pause', () => {
      player.pause()
      updatePlaybackState()
    })
    navigator.mediaSession.setActionHandler('nexttrack', () => player.next())
    navigator.mediaSession.setActionHandler('previoustrack', () => player.prev())
    navigator.mediaSession.setActionHandler('seekto', (details) => {
      if (details.seekTime != null) seekTo(details.seekTime)
    })
    navigator.mediaSession.setActionHandler('seekbackward', (details) => {
      const el = audioRef.value
      if (el) seekTo((el.currentTime || 0) - (details.seekOffset || 10))
    })
    navigator.mediaSession.setActionHandler('seekforward', (details) => {
      const el = audioRef.value
      if (el) seekTo((el.currentTime || 0) + (details.seekOffset || 10))
    })

    watch(() => [player.current?.id, player.cover], updateMetadata, { immediate: true })
    watch(() => [player.playing, player.current?.id], () => {
      updatePlaybackState()
      updatePositionState()
    }, { immediate: true })
  }

  return { updateMetadata, updatePlaybackState, updatePositionState }
}
