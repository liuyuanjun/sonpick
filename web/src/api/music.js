import api from './client'
import { taskEventsUrl } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

export function fetchSongs(params = {}) {
  return api.get('/songs', { params })
}

export function fetchFavorites() {
  return api.get('/favorites')
}

export function addFavorite(songId) {
  return api.post(`/songs/${songId}/favorite`)
}

export function removeFavorite(songId) {
  return api.delete(`/songs/${songId}/favorite`)
}

export function fetchArtists() {
  return api.get('/artists')
}

export function fetchArtistSongs(name) {
  return api.get(`/artists/${encodeURIComponent(name)}/songs`)
}

export function fetchAlbums() {
  return api.get('/albums')
}

export function fetchAlbumSongs(name, artist) {
  return api.get('/albums/songs', { params: { name, artist } })
}

export function fetchPlaylists() {
  return api.get('/playlists')
}

export function createPlaylist(payload) {
  return api.post('/playlists', payload)
}

export function updatePlaylist(id, payload) {
  return api.put(`/playlists/${id}`, payload)
}

export function deletePlaylist(id) {
  return api.delete(`/playlists/${id}`)
}

export function fetchPlaylistSongs(id) {
  return api.get(`/playlists/${id}/songs`)
}

export function addSongsToPlaylist(id, songIds) {
  return api.post(`/playlists/${id}/songs`, { song_ids: songIds })
}

export function removeSongFromPlaylist(playlistId, songId) {
  return api.delete(`/playlists/${playlistId}/songs/${songId}`)
}

export function fetchHistory(limit = 50) {
  return api.get('/history', { params: { limit } })
}

export function fetchLibraryStats() {
  return api.get('/library/stats')
}

export function fetchLyrics(songId) {
  return api.get(`/songs/${songId}/lyrics`)
}

export function recordPlay(songId) {
  return api.post(`/songs/${songId}/play`)
}


export function fetchSongTags(songId) {
  return api.get(`/songs/${songId}/tags`)
}

export function fetchScrapeCandidates(songId, payload = {}) {
  return api.post(`/songs/${songId}/scrape/candidates`, { source: 'auto', limit: 8, ...payload }, { timeout: 120000 })
}

export function applyScrapeCandidate(songId, candidate, options = {}) {
  return api.post(`/songs/${songId}/scrape/apply`, {
    candidate,
    write_file_tags: options.write_file_tags !== false,
  }, { timeout: 120000 })
}

export function enrichSong(songId, params = {}) {
  // 默认异步：避免播放/反代超时；返回 {async, task_id}
  return api.post(`/songs/${songId}/enrich`, null, {
    params: { async_mode: true, allow_network: true, write_file_tags: true, ...params },
    timeout: 30000,
  })
}

export function streamUrl(songId, token, losslessPreferred = false) {
  return `/api/songs/${songId}/stream?token=${encodeURIComponent(token || '')}&lossless_preferred=${losslessPreferred ? 'true' : 'false'}`
}

export function coverUrl(songId, token) {
  if (!songId) return ''
  return `/api/songs/${songId}/cover?token=${encodeURIComponent(token || '')}`
}

export function fetchSources() {
  return api.get('/sources')
}

export function createSource(payload) {
  return api.post('/sources', payload)
}

export function updateSource(id, payload) {
  return api.put(`/sources/${id}`, payload)
}

export function deleteSource(id) {
  return api.delete(`/sources/${id}`)
}

export function testSource(id) {
  return api.post(`/sources/${id}/test`)
}

export function setDefaultUploadSource(id) {
  return api.post(`/sources/${id}/set-default-upload`)
}

export function scanSource(id) {
  return api.post(`/sources/${id}/scan`, null, { timeout: 30000 })
}

export function scanLibrary(payload = { all: true }) {
  const body = {}
  if (payload.all) {
    body.source = 'all'
  } else if (payload.source) {
    body.source = payload.source
  }
  if (payload.source_ids?.length) {
    body.source_ids = payload.source_ids
    if (!body.source) body.source = 'all'
  }
  if (!body.source && !body.source_ids) body.source = 'all'
  return api.post('/library/scan', body, { timeout: 30000 })
}

export function searchMusic(q, page = 1, pageSize = 20, source = 'all') {
  // musicdl 搜索需逐条探测下载链接，可能耗时 1 分钟以上，前端超时放宽到 120s
  return api.get('/search', { params: { q, page, page_size: pageSize, source }, timeout: 120000 })
}

export function uploadSongToWebdav(songId, sourceId, policy = null) {
  const params = {}
  if (sourceId) params.source_id = sourceId
  if (policy) params.policy = policy
  return api.post(`/songs/${songId}/upload-webdav`, null, {
    params,
    timeout: 120000,
  })
}

export function checkUploadConflicts(songId, sourceId) {
  return api.post(`/songs/${songId}/upload-webdav/check`, null, {
    params: sourceId ? { source_id: sourceId } : {},
    timeout: 30000,
  })
}

export function convertSong(songId) {
  return api.post(`/songs/${songId}/convert`)
}

export function deleteSong(songId, deleteFiles = true) {
  return api.delete(`/songs/${songId}`, { params: { delete_files: deleteFiles } })
}

export function listWebdav(path = '', sourceId = null) {
  const params = { path }
  if (sourceId != null) params.source_id = sourceId
  return api.get('/webdav/list', { params })
}

export function browseLocalSource(sourceId, path = '') {
  return api.get(`/sources/${sourceId}/browse`, {
    params: { path: path || '' },
  })
}

export function deleteBrowseItem(sourceId, path) {
  return api.delete(`/sources/${sourceId}/browse`, {
    params: { path },
  })
}

export function deleteWebdavItem(path, sourceId = null) {
  const params = { path }
  if (sourceId != null) params.source_id = sourceId
  return api.delete('/webdav/item', { params })
}

export function listReorganizeDirs(sourceId, path = '') {
  return api.get(`/sources/${sourceId}/reorganize/dirs`, {
    params: { path: path || '' },
  })
}

export function previewReorganize(sourceId, payload = {}) {
  const body = {
    limit: payload.limit ?? 20,
    relative_dir: payload.relative_dir || '',
    include_failed: !!payload.include_failed,
    allow_network: !!payload.allow_network,
    relocate_format_dirs: !!payload.relocate_format_dirs,
  }
  return api.post(`/sources/${sourceId}/reorganize/preview`, body, { timeout: 120000 })
}

export function applyReorganize(sourceId, payload = {}) {
  const body = {
    limit: payload.limit ?? 20,
    relative_dir: payload.relative_dir || '',
    include_failed: !!payload.include_failed,
    allow_network: !!payload.allow_network,
    relocate_format_dirs: !!payload.relocate_format_dirs,
  }
  return api.post(`/sources/${sourceId}/reorganize/apply`, body, { timeout: 600000 })
}

export function scrapeSource(sourceId, payload = {}) {
  return api.post(`/sources/${sourceId}/scrape`, {
    async_mode: true,
    allow_network: true,
    write_file_tags: true,
    ...payload,
  }, { timeout: 60000 })
}

export function scrapeSongs(payload = {}) {
  return api.post('/songs/scrape', {
    async_mode: true,
    allow_network: true,
    write_file_tags: true,
    ...payload,
  }, { timeout: 60000 })
}


export function getTask(taskId) {
  return api.get(`/tasks/${taskId}`)
}

export function listTasks(params = {}) {
  return api.get('/tasks', { params })
}

export function cancelTask(taskId) {
  return api.delete(`/tasks/${taskId}`)
}


/**
 * SSE 监听任务进度。返回取消函数。
 */
export function watchTask(taskId, { onUpdate, onError, onEnd } = {}) {
  const auth = useAuthStore()
  const url = taskEventsUrl(taskId, auth.token || '')
  const es = new EventSource(url)
  let closed = false

  const close = () => {
    if (closed) return
    closed = true
    try { es.close() } catch (_) {}
  }

  es.onmessage = (ev) => {
    if (!ev?.data) return
    try {
      const task = JSON.parse(ev.data)
      if (typeof onUpdate === 'function') onUpdate(task)
      if (task && (task.status === 'completed' || task.status === 'failed' || task.status === 'cancelled')) {
        if (typeof onEnd === 'function') onEnd(task)
        close()
      }
    } catch (err) {
      if (typeof onError === 'function') onError(err)
    }
  }
  es.addEventListener('end', () => {
    if (typeof onEnd === 'function') onEnd(null)
    close()
  })
  es.onerror = (ev) => {
    if (closed) return
    if (typeof onError === 'function') onError(ev)
  }

  return close
}

/** Promise 版：等到任务终态或超时（SSE，不再轮询 GET /tasks/:id） */
export function waitTask(taskId, { timeoutMs = 15 * 60 * 1000, onProgress } = {}) {
  return new Promise((resolve, reject) => {
    let done = false
    let close = () => {}
    const timer = setTimeout(() => {
      if (done) return
      done = true
      close()
      reject(new Error('任务等待超时'))
    }, timeoutMs)

    close = watchTask(taskId, {
      onUpdate: (task) => {
        if (typeof onProgress === 'function') onProgress(task)
        if (task && (task.status === 'completed' || task.status === 'failed' || task.status === 'cancelled')) {
          if (done) return
          done = true
          clearTimeout(timer)
          close()
          resolve(task)
        }
      },
      onEnd: (task) => {
        if (done) return
        if (task) {
          done = true
          clearTimeout(timer)
          resolve(task)
        }
      },
    })
  })
}
