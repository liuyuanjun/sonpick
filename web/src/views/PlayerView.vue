<template>
  <div class="player-page" :class="{ 'queue-open': player.showQueue, 'is-dark': themeStore.isDark, 'no-mini': !hasMiniPlayer }" :style="playerPageStyle">
    <aside class="side-nav">
      <div
        v-for="item in menus"
        :key="item.key"
        class="nav-item"
        :class="{ active: section === item.key }"
        @click="switchSection(item.key)"
      >
        <n-icon size="18"><component :is="item.icon" /></n-icon>
        <span>{{ item.label }}</span>
      </div>
    </aside>

    <main class="content">
      <div class="content-head">
        <div>
          <h2 class="page-title">{{ sectionTitle }}</h2>
          <n-text depth="3" v-if="stats">
            {{ stats.song_count }} 首 · {{ stats.artist_count }} 位艺术家 · {{ stats.album_count }} 张专辑
          </n-text>
        </div>
        <n-space v-if="isMobile" class="content-actions" :size="8">
          <n-button secondary type="primary" size="small" @click="openScanModal">扫描曲库</n-button>
          <n-dropdown trigger="click" :options="mobileActions" @select="onMobileAction">
            <n-button quaternary circle size="small" aria-label="更多操作">
              <n-icon size="18"><ellipsis-horizontal /></n-icon>
            </n-button>
          </n-dropdown>
        </n-space>
        <n-space v-else class="content-actions">
          <n-button v-if="section === 'playlists'" type="primary" @click="showCreatePlaylist = true">
            新建歌单
          </n-button>
          <n-button secondary type="primary" @click="openScanModal">扫描曲库</n-button>
          <n-button secondary :loading="scrapingVisible" :disabled="!visibleSongIds.length" @click="scrapeVisibleSongs">
            刮削本页
          </n-button>
          <n-button quaternary @click="refresh">刷新</n-button>
        </n-space>
      </div>

      <div v-if="isLibraryEmpty && !loading" class="empty-library">
        <n-empty description="曲库还是空的">
          <template #extra>
            <n-space vertical align="center">
              <n-text depth="3">先扫描本地目录或 WebDAV，把音乐入库后再来播放</n-text>
              <n-space>
                <n-button type="primary" @click="openScanModal">选择源扫描</n-button>
                <n-button @click="refresh">刷新</n-button>
              </n-space>
            </n-space>
          </template>
        </n-empty>
      </div>

      <n-spin :show="loading">
        <song-table
          v-if="section === 'favorites'"
          :songs="favorites"
          @changed="loadFavorites"
          @add-to-playlist="openAddToPlaylist"
        />

        <song-table
          v-else-if="section === 'songs'"
          :songs="songs"
          :server-paginated="true"
          :total="songsTotal"
          :page="songsPage"
          :page-size="songsPageSize"
          :search-value="songsQuery"
          :playing-all="playingAllSongs"
          @changed="loadSongs"
          @search="searchSongs"
          @page-change="changeSongsPage"
          @play-all-results="playAllSongs"
          @add-to-playlist="openAddToPlaylist"
        />

        <song-table
          v-else-if="section === 'history'"
          :songs="history"
          :show-search="false"
          @changed="loadHistory"
          @add-to-playlist="openAddToPlaylist"
        />

        <div v-else-if="section === 'artists'">
          <div v-if="!selectedArtist" class="card-grid">
            <div
              v-for="a in artists"
              :key="a.name"
              class="media-card"
              @click="openArtist(a)"
            >
              <div class="media-cover circle">
                <img v-if="a.cover_song_id" :src="coverOf(a.cover_song_id)" alt="" />
                <n-icon v-else size="36"><person /></n-icon>
              </div>
              <div class="media-title">{{ a.name }}</div>
              <div class="media-sub">{{ a.song_count }} 首 · {{ a.album_count }} 张专辑</div>
            </div>
            <n-empty v-if="!artists.length" description="暂无艺术家，先扫描曲库" />
          </div>
          <div v-else>
            <n-space align="center" style="margin-bottom: 12px">
              <n-button quaternary @click="selectedArtist = null">← 返回</n-button>
              <n-text strong>{{ selectedArtist }}</n-text>
            </n-space>
            <song-table
              :songs="artistSongs"
              @changed="openArtist({ name: selectedArtist })"
              @add-to-playlist="openAddToPlaylist"
            />
          </div>
        </div>

        <div v-else-if="section === 'albums'">
          <div v-if="!selectedAlbum" class="card-grid">
            <div
              v-for="a in albums"
              :key="a.name + '::' + a.artist"
              class="media-card"
              @click="openAlbum(a)"
            >
              <div class="media-cover">
                <img v-if="a.cover_song_id" :src="coverOf(a.cover_song_id)" alt="" />
                <n-icon v-else size="36"><disc /></n-icon>
              </div>
              <div class="media-title">{{ a.name }}</div>
              <div class="media-sub">{{ a.artist }} · {{ a.song_count }} 首</div>
            </div>
            <n-empty v-if="!albums.length" description="暂无专辑，先扫描曲库" />
          </div>
          <div v-else>
            <n-space align="center" style="margin-bottom: 12px">
              <n-button quaternary @click="selectedAlbum = null">← 返回</n-button>
              <n-text strong>{{ selectedAlbum.name }}</n-text>
              <n-text depth="3">{{ selectedAlbum.artist }}</n-text>
            </n-space>
            <song-table
              :songs="albumSongs"
              @changed="openAlbum(selectedAlbum)"
              @add-to-playlist="openAddToPlaylist"
            />
          </div>
        </div>

        <div v-else-if="section === 'playlists'">
          <div v-if="!selectedPlaylist" class="card-grid">
            <div
              v-for="p in playlists"
              :key="p.id"
              class="media-card"
              @click="openPlaylist(p)"
            >
              <div class="media-cover">
                <img v-if="p.cover_song_id" :src="coverOf(p.cover_song_id)" alt="" />
                <n-icon v-else size="36"><list /></n-icon>
              </div>
              <div class="media-title">{{ p.name }}</div>
              <div class="media-sub">{{ p.song_count }} 首</div>
              <div class="card-actions" @click.stop>
                <n-button size="tiny" quaternary type="error" @click="onDeletePlaylist(p)">删除</n-button>
              </div>
            </div>
            <n-empty v-if="!playlists.length" class="playlist-empty" description="还没有歌单，点右上角新建" />
          </div>
          <div v-else>
            <n-space align="center" style="margin-bottom: 12px">
              <n-button quaternary @click="selectedPlaylist = null">← 返回</n-button>
              <n-text strong>{{ selectedPlaylist.name }}</n-text>
              <n-text depth="3">{{ selectedPlaylist.song_count }} 首</n-text>
            </n-space>
            <song-table
              :songs="playlistSongs"
              :playlist-id="selectedPlaylist.id"
              @changed="openPlaylist(selectedPlaylist)"
              @remove-from-playlist="onRemoveFromPlaylist"
              @add-to-playlist="openAddToPlaylist"
            />
          </div>
        </div>
      </n-spin>
    </main>

    <section v-if="!isMobile" class="stage">
      <div class="stage-main">
        <player-panel />
      </div>
      <transition name="queue-slide">
        <aside v-if="player.showQueue" class="queue-drawer">
          <player-queue />
        </aside>
      </transition>
    </section>

    <transition name="panel-slide">
      <div v-if="isMobile && player.fullPlayerOpen" class="mobile-player-overlay">
        <player-panel />
      </div>
    </transition>

    <transition name="panel-slide">
      <div v-if="isMobile && player.showQueue" class="mobile-queue-sheet">
        <player-queue />
      </div>
    </transition>

    <n-modal v-model:show="showCreatePlaylist" preset="dialog" title="新建歌单" positive-text="创建" negative-text="取消" @positive-click="createPlaylistAndClose">
      <n-form>
        <n-form-item label="名称">
          <n-input v-model:value="newPlaylistName" placeholder="我的歌单" />
        </n-form-item>
        <n-form-item label="描述">
          <n-input v-model:value="newPlaylistDesc" type="textarea" placeholder="可选" />
        </n-form-item>
      </n-form>
    </n-modal>

    <n-modal v-model:show="showAddToPlaylist" preset="dialog" title="加入歌单" positive-text="加入" negative-text="取消" @positive-click="confirmAddToPlaylist">
      <n-select
        v-model:value="targetPlaylistId"
        :options="playlistOptions"
        placeholder="选择歌单"
      />
    </n-modal>

    <n-modal v-model:show="showScanModal" preset="card" title="扫描曲库" style="width: 520px">
      <n-space vertical>
        <n-text depth="3">选择要扫描的歌曲源，或扫描全部已启用源。</n-text>
        <n-space>
          <n-button size="small" @click="selectAllSources">全选</n-button>
          <n-button size="small" @click="scanSourceIds = []">清空</n-button>
        </n-space>
        <n-space vertical>
          <n-space v-for="s in scanSources" :key="s.id" align="center">
            <n-switch
              :value="scanSourceIds.includes(s.id)"
              @update:value="(v) => toggleScanSource(s.id, v)"
            />
            <n-tag size="small" :type="s.type === 'webdav' ? 'info' : 'success'">
              {{ s.type === 'webdav' ? 'WebDAV' : '本地' }}
            </n-tag>
            <n-text>{{ s.name }}</n-text>
            <n-text depth="3">{{ s.song_count || 0 }} 首</n-text>
          </n-space>
        </n-space>
      </n-space>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showScanModal = false">取消</n-button>
          <n-button type="primary" :loading="scanningLibrary" @click="runLibraryScan(true)">扫描全部</n-button>
          <n-button type="success" :loading="scanningLibrary" @click="runLibraryScan(false)">扫描选中</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { onUnmounted } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import {
  Heart,
  HeartOutline,
  MusicalNotes,
  People,
  Disc,
  List,
  TimeOutline,
  EllipsisHorizontal,
} from '@vicons/ionicons5'
import { useAuthStore } from '@/stores/auth'
import { usePlayerStore } from '@/stores/player'
import { useThemeStore } from '@/stores/theme'
import { useIsMobile } from '@/composables/useIsMobile'
import SongTable from '@/components/player/SongTable.vue'
import PlayerPanel from '@/components/player/PlayerPanel.vue'
import PlayerQueue from '@/components/player/PlayerQueue.vue'
import { extractAccentFromImage } from '@/utils/color'
import {
  addSongsToPlaylist,
  coverUrl,
  createPlaylist,
  deletePlaylist,
  fetchAlbums,
  fetchAlbumSongs,
  fetchArtistSongs,
  fetchArtists,
  fetchFavorites,
  fetchHistory,
  fetchLibraryStats,
  fetchPlaylistSongs,
  fetchPlaylists,
  fetchSongs,
  fetchSources,
  removeSongFromPlaylist,
  scanLibrary,
  scrapeSongs,
  waitTask,
} from '@/api/music'

const player = usePlayerStore()
const auth = useAuthStore()
const themeStore = useThemeStore()
const message = useMessage()
const dialog = useDialog()
const isMobile = useIsMobile()

const section = ref('favorites')
const loading = ref(false)
const songs = ref([])
const songsTotal = ref(0)
const songsPage = ref(1)
const songsPageSize = 100
const songsQuery = ref('')
const playingAllSongs = ref(false)
let songsRequestId = 0
let songsSearchTimer = null
const favorites = ref([])
const artists = ref([])
const albums = ref([])
const playlists = ref([])
const history = ref([])
const stats = ref(null)
const pageAccent = ref(null)

const selectedArtist = ref(null)
const artistSongs = ref([])
const selectedAlbum = ref(null)
const albumSongs = ref([])
const selectedPlaylist = ref(null)
const playlistSongs = ref([])

const showCreatePlaylist = ref(false)
const newPlaylistName = ref('')
const newPlaylistDesc = ref('')
const showAddToPlaylist = ref(false)
const targetPlaylistId = ref(null)
const pendingSong = ref(null)

const showScanModal = ref(false)
const scanSources = ref([])
const scanSourceIds = ref([])
const scanningLibrary = ref(false)

const menus = [
  { key: 'favorites', label: '我喜欢的', icon: Heart },
  { key: 'playlists', label: '歌单', icon: List },
  { key: 'artists', label: '艺术家', icon: People },
  { key: 'albums', label: '专辑', icon: Disc },
  { key: 'songs', label: '歌曲', icon: MusicalNotes },
  { key: 'history', label: '最近播放', icon: TimeOutline },
]

const sectionTitle = computed(() => menus.find((m) => m.key === section.value)?.label || '播放器')
// 迷你播放器未展示时不为其预留底部空间，避免页面下方出现一条空白区域
const hasMiniPlayer = computed(() => player.showPlayer && !!player.current)
const scrapingVisible = ref(false)
const visibleSongIds = computed(() => {
  let list = []
  if (section.value === 'favorites') list = favorites.value
  else if (section.value === 'songs') list = songs.value
  else if (section.value === 'history') list = history.value
  else if (section.value === 'artists' && selectedArtist.value) list = artistSongs.value
  else if (section.value === 'albums' && selectedAlbum.value) list = albumSongs.value
  else if (section.value === 'playlists' && selectedPlaylist.value) list = playlistSongs.value
  return list.map((s) => s?.id).filter(Boolean)
})
const mobileActions = computed(() => {
  const opts = []
  if (section.value === 'playlists') opts.push({ label: '新建歌单', key: 'create-playlist' })
  opts.push({ label: '刮削本页', key: 'scrape', disabled: !visibleSongIds.value.length })
  opts.push({ label: '刷新', key: 'refresh' })
  return opts
})

function onMobileAction(key) {
  if (key === 'create-playlist') showCreatePlaylist.value = true
  else if (key === 'scrape') scrapeVisibleSongs()
  else if (key === 'refresh') refresh()
}
const playlistOptions = computed(() => playlists.value.map((p) => ({ label: p.name, value: p.id })))
const isLibraryEmpty = computed(() => !stats.value || !stats.value.song_count)
const playerPageStyle = computed(() => {
  const fallback = themeStore.isDark ? { r: 56, g: 189, b: 139 } : { r: 24, g: 160, b: 88 }
  const { r, g, b } = pageAccent.value || fallback
  const dark = themeStore.isDark
  return {
    '--cover-accent': `rgb(${r}, ${g}, ${b})`,
    '--cover-accent-seam': `rgba(${r}, ${g}, ${b}, ${dark ? 0.20 : 0.18})`,
    '--cover-accent-seam-soft': `rgba(${r}, ${g}, ${b}, ${dark ? 0.12 : 0.10})`,
    '--cover-accent-glow': `rgba(${r}, ${g}, ${b}, ${dark ? 0.18 : 0.13})`,
    '--cover-accent-wash': `rgba(${r}, ${g}, ${b}, ${dark ? 0.18 : 0.12})`,
    '--cover-accent-wash-soft': `rgba(${r}, ${g}, ${b}, ${dark ? 0.10 : 0.08})`,
  }
})

watch(
  () => player.cover,
  async (url) => {
    pageAccent.value = null
    if (!url) return
    pageAccent.value = await extractAccentFromImage(url)
  },
  { immediate: true }
)

function coverOf(songId) {
  return coverUrl(songId, auth.token)
}

async function scrapeVisibleSongs() {
  const ids = visibleSongIds.value
  if (!ids.length) {
    message.warning('当前列表没有可刮削歌曲')
    return
  }
  scrapingVisible.value = true
  try {
    const res = await scrapeSongs({
      song_ids: ids,
      async_mode: true,
      allow_network: true,
      write_file_tags: true,
      limit: ids.length,
    })
    const data = res.data || res || {}
    if (!data.task_id) {
      message.success('刮削完成')
      await refresh()
      return
    }
    message.success(`刮削任务 #${data.task_id} 已创建（${ids.length} 首）`)
    const task = await waitTask(data.task_id)
    if (task?.status === 'completed') {
      message.success('刮削完成')
      await refresh()
      return
    }
    message.error(task?.error_message || '刮削失败')
  } catch (err) {
    message.error(err.response?.data?.detail || err.message || '刮削失败')
  } finally {
    scrapingVisible.value = false
  }
}

async function openScanModal() {
  try {
    const res = await fetchSources()
    scanSources.value = (res.data || []).filter((s) => s.enabled !== false)
    scanSourceIds.value = scanSources.value.map((s) => s.id)
    showScanModal.value = true
  } catch (err) {
    message.error(err.response?.data?.detail || '加载歌曲源失败')
  }
}

function selectAllSources() {
  scanSourceIds.value = scanSources.value.map((s) => s.id)
}

function toggleScanSource(id, on) {
  if (on) {
    if (!scanSourceIds.value.includes(id)) scanSourceIds.value.push(id)
  } else {
    scanSourceIds.value = scanSourceIds.value.filter((x) => x !== id)
  }
}

async function runLibraryScan(all) {
  if (!all && !scanSourceIds.value.length) {
    message.warning('请先选择要扫描的源')
    return
  }
  scanningLibrary.value = true
  try {
    const payload = all ? { all: true } : { source_ids: [...scanSourceIds.value] }
    const res = await scanLibrary(payload)
    const d = res.data || {}
    const taskId = d.task_id
    message.info('扫描任务已创建，正在后台执行...')
    showScanModal.value = false
    const task = await waitTask(taskId)
    const result = task?.result || {}
    const st = task?.status || 'completed'
    if (st === 'completed') {
      const text = result.message
        || task?.progress?.message
        || `扫描完成：新增 ${result.total_added || 0}，更新 ${result.total_updated || 0}`
      message.success(text)
      await refresh()
    } else if (st === 'failed') {
      message.error(task?.error_message || result.message || '扫描失败')
    } else if (st === 'cancelled') {
      message.warning('扫描已取消')
    }
  } catch (err) {
    message.error(err.response?.data?.detail || err.message || '扫描失败')
  } finally {
    scanningLibrary.value = false
  }
}

function switchSection(key) {
  section.value = key
  selectedArtist.value = null
  selectedAlbum.value = null
  selectedPlaylist.value = null
  refresh()
}

async function refresh() {
  loading.value = true
  try {
    await loadStats()
    if (section.value === 'favorites') await loadFavorites()
    else if (section.value === 'songs') await loadSongs()
    else if (section.value === 'artists') await loadArtists()
    else if (section.value === 'albums') await loadAlbums()
    else if (section.value === 'playlists') await loadPlaylists()
    else if (section.value === 'history') await loadHistory()
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  try {
    const res = await fetchLibraryStats()
    stats.value = res.data
  } catch {
    stats.value = null
  }
}

async function loadSongs() {
  const requestId = ++songsRequestId
  const res = await fetchSongs({
    q: songsQuery.value || undefined,
    page: songsPage.value,
    page_size: songsPageSize,
  })
  if (requestId !== songsRequestId) return
  songs.value = res.data?.items || []
  songsTotal.value = res.data?.total || 0
  songsPage.value = res.data?.page || songsPage.value
}

function changeSongsPage(page) {
  songsPage.value = page
  loadSongs()
}

function searchSongs(value) {
  songsQuery.value = value
  songsPage.value = 1
  clearTimeout(songsSearchTimer)
  songsSearchTimer = setTimeout(loadSongs, 280)
}

async function playAllSongs() {
  if (!songsTotal.value) return
  playingAllSongs.value = true
  try {
    const res = await fetchSongs({
      q: songsQuery.value || undefined,
      page: 1,
      page_size: Math.min(songsTotal.value, 2000),
    })
    const items = res.data?.items || []
    if (!items.length) return
    player.playList(items, 0)
    message.success(`已将 ${items.length} 首歌曲加入播放队列`)
  } catch (err) {
    message.error(err.response?.data?.detail || '加载播放队列失败')
  } finally {
    playingAllSongs.value = false
  }
}

async function loadFavorites() {
  const res = await fetchFavorites()
  favorites.value = res.data || []
}

async function loadArtists() {
  const res = await fetchArtists()
  artists.value = res.data || []
}

async function openArtist(row) {
  selectedArtist.value = row.name
  loading.value = true
  try {
    const res = await fetchArtistSongs(row.name)
    artistSongs.value = res.data || []
  } finally {
    loading.value = false
  }
}

async function loadAlbums() {
  const res = await fetchAlbums()
  albums.value = res.data || []
}

async function openAlbum(row) {
  selectedAlbum.value = row
  loading.value = true
  try {
    const res = await fetchAlbumSongs(row.name, row.artist)
    albumSongs.value = res.data || []
  } finally {
    loading.value = false
  }
}

async function loadPlaylists() {
  const res = await fetchPlaylists()
  playlists.value = res.data || []
}

async function openPlaylist(row) {
  selectedPlaylist.value = row
  loading.value = true
  try {
    const res = await fetchPlaylistSongs(row.id)
    playlistSongs.value = res.data || []
    selectedPlaylist.value = { ...row, song_count: playlistSongs.value.length }
  } finally {
    loading.value = false
  }
}

async function loadHistory() {
  const res = await fetchHistory(80)
  history.value = (res.data || []).map((i) => i.song).filter(Boolean)
}

async function createPlaylistAndClose() {
  const name = newPlaylistName.value.trim()
  if (!name) {
    message.warning('请输入歌单名称')
    return false
  }
  try {
    await createPlaylist({ name, description: newPlaylistDesc.value || null })
    message.success('歌单已创建')
    newPlaylistName.value = ''
    newPlaylistDesc.value = ''
    await loadPlaylists()
    return true
  } catch (err) {
    message.error(err.response?.data?.detail || '创建失败')
    return false
  }
}

function onDeletePlaylist(pl) {
  dialog.warning({
    title: '删除歌单',
    content: `确定删除「${pl.name}」？歌曲文件不会被删除。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deletePlaylist(pl.id)
        message.success('已删除')
        await loadPlaylists()
      } catch (err) {
        message.error(err.response?.data?.detail || '删除失败')
      }
    },
  })
}

function openAddToPlaylist(song) {
  pendingSong.value = song
  targetPlaylistId.value = playlists.value[0]?.id || null
  if (!playlists.value.length) {
    loadPlaylists().then(() => {
      targetPlaylistId.value = playlists.value[0]?.id || null
    })
  }
  showAddToPlaylist.value = true
}

async function confirmAddToPlaylist() {
  if (!pendingSong.value || !targetPlaylistId.value) {
    message.warning('请选择歌单')
    return false
  }
  try {
    await addSongsToPlaylist(targetPlaylistId.value, [pendingSong.value.id])
    message.success('已加入歌单')
    await loadPlaylists()
    return true
  } catch (err) {
    message.error(err.response?.data?.detail || '加入失败')
    return false
  }
}

async function onRemoveFromPlaylist(song) {
  if (!selectedPlaylist.value) return
  try {
    await removeSongFromPlaylist(selectedPlaylist.value.id, song.id)
    message.success('已从歌单移除')
    await openPlaylist(selectedPlaylist.value)
  } catch (err) {
    message.error(err.response?.data?.detail || '移除失败')
  }
}

onMounted(async () => {
  await loadPlaylists()
  await refresh()
})

// 离开播放器页时收起移动端全屏浮层，避免下次进入时意外弹出
onUnmounted(() => {
  player.fullPlayerOpen = false
})
</script>

<style scoped>
.player-page {
  --player-surface: rgba(250, 252, 255, 0.74);
  --player-surface-strong: rgba(255, 255, 255, 0.86);
  --player-surface-soft: rgba(238, 243, 250, 0.50);
  --cover-accent: rgb(24, 160, 88);
  --cover-accent-seam: rgba(24, 160, 88, 0.18);
  --cover-accent-seam-soft: rgba(24, 160, 88, 0.10);
  --cover-accent-glow: rgba(24, 160, 88, 0.13);
  --cover-accent-wash: rgba(24, 160, 88, 0.12);
  --cover-accent-wash-soft: rgba(24, 160, 88, 0.08);
  --player-seam: var(--cover-accent-seam);
  --player-seam-soft: var(--cover-accent-seam-soft);
  --player-stage-wash: color-mix(in srgb, var(--cover-accent-wash) 34%, rgba(245, 248, 252, 0.70));
  --player-stage-wash-soft: color-mix(in srgb, var(--cover-accent-wash-soft) 42%, rgba(245, 248, 252, 0.18));
  --player-panel-glow: var(--cover-accent-glow);
  --player-scrollbar-thumb: rgba(86, 99, 118, 0.24);
  --player-scrollbar-thumb-hover: rgba(24, 160, 88, 0.46);
  --player-scrollbar-track: rgba(255, 255, 255, 0.18);
  display: grid;
  align-items: stretch;
  grid-template-columns: 168px minmax(260px, 0.9fr) minmax(420px, 1.25fr);
  gap: 0;
  height: calc(100vh - 56px - 84px);
  min-height: calc(100vh - 56px - 84px);
  margin: 0;
  background:
    radial-gradient(980px 440px at 78% -12%, var(--player-panel-glow), transparent 60%),
    radial-gradient(760px 360px at 10% 100%, rgba(64, 128, 255, 0.07), transparent 58%),
    var(--n-color);
  position: relative;
  overflow: hidden;
  border-radius: 0;
  border: none;
}
.player-page.is-dark {
  --player-surface: rgba(20, 24, 31, 0.72);
  --player-surface-strong: rgba(30, 34, 43, 0.82);
  --player-surface-soft: rgba(34, 40, 52, 0.38);
  --player-seam: var(--cover-accent-seam);
  --player-seam-soft: var(--cover-accent-seam-soft);
  --player-stage-wash: color-mix(in srgb, var(--cover-accent-wash) 36%, rgba(18, 22, 30, 0.78));
  --player-stage-wash-soft: color-mix(in srgb, var(--cover-accent-wash-soft) 42%, rgba(18, 22, 30, 0.22));
  --player-panel-glow: var(--cover-accent-glow);
  --player-scrollbar-thumb: rgba(172, 190, 214, 0.24);
  --player-scrollbar-thumb-hover: rgba(56, 189, 139, 0.48);
  --player-scrollbar-track: rgba(255, 255, 255, 0.06);
}
.player-page.queue-open {
  grid-template-columns: 168px minmax(240px, 0.8fr) minmax(600px, 1.4fr);
}
.player-page.no-mini {
  height: calc(100vh - 56px);
  min-height: calc(100vh - 56px);
}

.side-nav {
  border-right: 1px solid rgba(127, 127, 127, 0.10);
  padding: 16px 10px;
  background: linear-gradient(180deg, var(--player-surface-strong), var(--player-surface));
  overflow: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--player-scrollbar-thumb) transparent;
}
.side-nav::-webkit-scrollbar,
.content::-webkit-scrollbar {
  width: 8px;
}
.side-nav::-webkit-scrollbar-track,
.content::-webkit-scrollbar-track {
  background: transparent;
}
.side-nav::-webkit-scrollbar-thumb,
.content::-webkit-scrollbar-thumb {
  border: 2px solid transparent;
  border-radius: 999px;
  background: var(--player-scrollbar-thumb);
  background-clip: padding-box;
}
.side-nav::-webkit-scrollbar-thumb:hover,
.content::-webkit-scrollbar-thumb:hover {
  background: var(--player-scrollbar-thumb-hover);
  background-clip: padding-box;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 12px;
  border-radius: 12px;
  cursor: pointer;
  color: var(--n-text-color-2);
  margin-bottom: 4px;
  transition: all 0.15s ease;
  user-select: none;
}
.nav-item:hover {
  background: rgba(127, 127, 127, 0.08);
}
.nav-item.active {
  background: rgba(24, 160,  88, 0.14);
  color: var(--n-primary-color);
  font-weight: 600;
}

.content {
  padding: 18px 14px 22px 16px;
  overflow: auto;
  scrollbar-gutter: stable;
  scrollbar-width: thin;
  scrollbar-color: var(--player-scrollbar-thumb) transparent;
  min-width: 0;
  max-width: 100%;
  height: 100%;
  position: relative;
  background:
    linear-gradient(90deg, var(--player-surface-strong) 0%, var(--player-surface) 72%, var(--player-surface-soft) 100%),
    radial-gradient(520px 280px at 92% 16%, var(--player-panel-glow), transparent 66%);
  backdrop-filter: blur(20px) saturate(1.06);
  box-shadow: inset -1px 0 0 rgba(127, 127, 127, 0.08);
}
.content::before {
  content: '';
  position: absolute;
  inset: 0 -54px 0 auto;
  width: 108px;
  pointer-events: none;
  z-index: 1;
  background:
    linear-gradient(90deg, rgba(255, 255, 255, 0), var(--player-seam-soft) 40%, rgba(255, 255, 255, 0)),
    radial-gradient(180px 70% at 100% 48%, var(--player-seam), transparent 72%);
}
.content-actions {
  position: sticky;
  top: 0;
  z-index: 5;
  padding: 0 0 10px 10px;
  margin: -4px -4px 0 0;
  border-radius: 0 0 0 18px;
  background: linear-gradient(180deg, var(--player-surface-strong), rgba(255, 255, 255, 0));
  backdrop-filter: blur(16px);
}
.content-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 14px;
  gap: 12px;
  flex-wrap: wrap;
}
.page-title {
  margin: 0 0 4px;
  font-size: 22px;
  letter-spacing: 0.2px;
  line-height: 1.25;
}
.empty-library {
  margin: 24px 0 8px;
  padding: 28px 16px;
  border: 1px dashed rgba(127, 127, 127, 0.28);
  border-radius: 16px;
  background: rgba(127, 127, 127, 0.03);
}

.stage {
  display: flex;
  flex-direction: row;
  min-width: 0;
  min-height: 0;
  height: 100%;
  position: relative;
  background:
    linear-gradient(90deg, var(--player-stage-wash) 0%, var(--player-stage-wash-soft) 11%, rgba(0, 0, 0, 0) 30%),
    #0b0c10;
  overflow: hidden;
}
.stage::before {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: 118px;
  pointer-events: none;
  z-index: 2;
  background:
    linear-gradient(90deg, var(--player-surface-soft), rgba(255, 255, 255, 0)),
    radial-gradient(180px 72% at 0 48%, var(--player-seam), transparent 72%);
  mix-blend-mode: screen;
  opacity: 0.58;
}
.player-page.is-dark .stage::before {
  mix-blend-mode: normal;
  opacity: 0.76;
}
.stage-main {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.queue-drawer {
  width: 280px;
  flex: 0 0 280px;
  border-left: 1px solid var(--n-border-color);
  min-height: 0;
  overflow: hidden;
  background: var(--n-card-color);
  color: var(--n-text-color);
}
.queue-slide-enter-active,
.queue-slide-leave-active {
  transition: width 0.18s ease, opacity 0.18s ease, flex-basis 0.18s ease;
}
.queue-slide-enter-from,
.queue-slide-leave-to {
  width: 0 !important;
  flex-basis: 0 !important;
  opacity: 0;
  border-left-width: 0;
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(136px, 1fr));
  gap: 14px;
  padding-bottom: 12px;
}
.playlist-empty {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 240px;
  text-align: center;
}
.media-card {
  border-radius: 14px;
  padding: 12px;
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
  position: relative;
  background: rgba(127, 127, 127, 0.035);
  border: 1px solid rgba(127, 127, 127, 0.08);
  min-width: 0;
}
.media-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.08);
  background: rgba(127, 127, 127, 0.05);
}
.media-cover {
  width: 100%;
  aspect-ratio: 1;
  border-radius: 12px;
  overflow: hidden;
  background: rgba(127, 127, 127, 0.12);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 10px;
  color: var(--n-text-color-3);
}
.media-cover.circle {
  border-radius: 50%;
}
.media-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.media-title {
  font-weight: 600;
  font-size: 13px;
  line-height: 1.35;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.media-sub {
  margin-top: 3px;
  font-size: 12px;
  color: var(--n-text-color-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.card-actions {
  margin-top: 8px;
}

@media (max-width: 1280px) {
  .player-page {
    grid-template-columns: 156px minmax(240px, 0.9fr) minmax(340px, 1.1fr);
  }
  .player-page.queue-open {
    grid-template-columns: 156px minmax(220px, 0.8fr) minmax(500px, 1.3fr);
  }
}

@media (max-width: 1100px) {
  .player-page,
  .player-page.queue-open {
    grid-template-columns: 64px minmax(0, 1fr) minmax(300px, 1fr);
  }
  .nav-item span {
    display: none;
  }
  .nav-item {
    justify-content: center;
    padding: 12px 8px;
  }
}

/* ---------- 移动端（≤768px）：顶部横向 Tab + 全宽列表 + 全屏播放器浮层 ---------- */
@media (max-width: 768px) {
  .player-page,
  .player-page.queue-open {
    display: flex;
    flex-direction: column;
    height: calc(100dvh - 56px - 60px - 52px - env(safe-area-inset-bottom, 0px));
    min-height: calc(100dvh - 56px - 60px - 52px - env(safe-area-inset-bottom, 0px));
  }
  .player-page.no-mini {
    height: calc(100dvh - 56px - 52px - env(safe-area-inset-bottom, 0px));
    min-height: calc(100dvh - 56px - 52px - env(safe-area-inset-bottom, 0px));
  }
  .side-nav {
    flex: 0 0 auto;
    display: flex;
    flex-direction: row;
    gap: 2px;
    padding: 8px 10px;
    border-right: none;
    border-bottom: 1px solid rgba(127, 127, 127, 0.10);
    overflow-x: auto;
    overflow-y: hidden;
  }
  .nav-item {
    flex: 0 0 auto;
    justify-content: center;
    padding: 7px 12px;
    margin-bottom: 0;
    gap: 6px;
    font-size: 13px;
    white-space: nowrap;
  }
  .nav-item span {
    display: inline;
  }
  .content {
    flex: 1 1 auto;
    height: auto;
    padding: 12px 12px 16px;
  }
  .content::before {
    display: none;
  }
  .content-head {
    margin-bottom: 10px;
  }
  .content-actions {
    position: static;
    padding-bottom: 0;
  }
  .page-title {
    font-size: 18px;
  }
  .card-grid {
    grid-template-columns: repeat(auto-fill, minmax(108px, 1fr));
    gap: 10px;
  }
}

.mobile-player-overlay {
  position: fixed;
  inset: 0;
  z-index: 1400;
  background: #0b0c10;
}
.mobile-queue-sheet {
  position: fixed;
  inset: 0;
  z-index: 1500;
  background: var(--n-card-color);
}
.panel-slide-enter-active,
.panel-slide-leave-active {
  transition: transform 0.25s ease, opacity 0.25s ease;
}
.panel-slide-enter-from,
.panel-slide-leave-to {
  transform: translateY(100%);
  opacity: 0.4;
}
</style>
