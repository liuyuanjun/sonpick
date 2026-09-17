<template>
  <div class="player-page">
    <!-- 桌面端二级导航已上移到系统侧边栏；移动端保留这里的横向 Tab，避免丢失入口 -->
    <nav class="player-tabs" aria-label="音乐列表">
      <button
        v-for="item in menus"
        :key="item.key"
        type="button"
        class="player-tab"
        :class="{ active: section === item.key }"
        :aria-current="section === item.key ? 'page' : undefined"
        @click="switchSection(item.key)"
      >
        <n-icon size="18"><component :is="item.icon" /></n-icon>
        <span>{{ item.label }}</span>
      </button>
    </nav>

    <main class="player-body">
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
        <n-space v-else class="content-actions" :size="6">
          <n-button v-if="section === 'playlists'" type="primary" @click="showCreatePlaylist = true">
            新建歌单
          </n-button>
          <n-tooltip>
            <template #trigger>
              <n-button quaternary circle aria-label="扫描曲库" @click="openScanModal">
                <n-icon size="18"><scan-outline /></n-icon>
              </n-button>
            </template>
            扫描曲库
          </n-tooltip>
          <n-tooltip>
            <template #trigger>
              <n-button quaternary circle :loading="scrapingVisible" :disabled="!visibleSongIds.length" aria-label="刮削信息" @click="scrapeVisibleSongs">
                <n-icon v-if="!scrapingVisible" size="18"><color-wand-outline /></n-icon>
              </n-button>
            </template>
            刮削信息
          </n-tooltip>
          <n-tooltip>
            <template #trigger>
              <n-button quaternary circle :disabled="!visibleSongIds.length" aria-label="获取歌词" @click="openBatchLyrics">
                <n-icon size="18"><document-text-outline /></n-icon>
              </n-button>
            </template>
            获取歌词
          </n-tooltip>
          <n-tooltip>
            <template #trigger>
              <n-button quaternary circle aria-label="刷新" @click="refresh">
                <n-icon size="18"><refresh-outline /></n-icon>
              </n-button>
            </template>
            刷新
          </n-tooltip>
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
            <n-empty v-if="!artists.length" class="card-grid-empty" description="暂无艺术家，先扫描曲库" />
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
            <n-empty v-if="!albums.length" class="card-grid-empty" description="暂无专辑，先扫描曲库" />
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
            <n-empty v-if="!playlists.length" class="card-grid-empty" description="还没有歌单，点右上角新建" />
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

    <BatchLyricsModal
      v-model:show="showBatchLyrics"
      :song-ids="batchLyricsSongIds"
      :target-label="`当前列表 ${batchLyricsSongIds.length} 首歌曲`"
    />
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
import BatchLyricsModal from '@/components/BatchLyricsModal.vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import { useRoute, useRouter } from 'vue-router'
import {
  Heart,
  HeartOutline,
  MusicalNotes,
  People,
  Disc,
  List,
  TimeOutline,
  EllipsisHorizontal,
  ScanOutline,
  ColorWandOutline,
  DocumentTextOutline,
  RefreshOutline,
} from '@vicons/ionicons5'
import { useAuthStore } from '@/stores/auth'
import { usePlayerStore, normalizePlayerSection } from '@/stores/player'
import { useIsMobile } from '@/composables/useIsMobile'
import SongTable from '@/components/player/SongTable.vue'
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
  fetchRandomPool,
  fetchSources,
  removeSongFromPlaylist,
  scanLibrary,
  scrapeSongs,
  waitTask,
} from '@/api/music'

const player = usePlayerStore()
const auth = useAuthStore()
const message = useMessage()
const dialog = useDialog()
const isMobile = useIsMobile()
const route = useRoute()
const router = useRouter()

const normalizeSection = normalizePlayerSection

// section 的唯一真相源是路由：/player/<section>，非法值回落到 favorites
const section = ref(normalizeSection(route.params.section))
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
  { key: 'favorites', label: '喜欢', icon: Heart },
  { key: 'playlists', label: '歌单', icon: List },
  { key: 'artists', label: '歌手', icon: People },
  { key: 'albums', label: '专辑', icon: Disc },
  { key: 'songs', label: '歌曲', icon: MusicalNotes },
  { key: 'history', label: '最近', icon: TimeOutline },
]

const sectionTitle = computed(() => menus.find((m) => m.key === section.value)?.label || '播放器')
const scrapingVisible = ref(false)
const showBatchLyrics = ref(false)
const batchLyricsSongIds = ref([])
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
  opts.push({ label: '刮削信息', key: 'scrape', disabled: !visibleSongIds.value.length })
  opts.push({ label: '获取歌词', key: 'lyrics', disabled: !visibleSongIds.value.length })
  opts.push({ label: '刷新', key: 'refresh' })
  return opts
})

function openBatchLyrics() {
  batchLyricsSongIds.value = [...visibleSongIds.value]
  showBatchLyrics.value = true
}

function onMobileAction(key) {
  if (key === 'create-playlist') showCreatePlaylist.value = true
  else if (key === 'scrape') scrapeVisibleSongs()
  else if (key === 'lyrics') openBatchLyrics()
  else if (key === 'refresh') refresh()
}
const playlistOptions = computed(() => playlists.value.map((p) => ({ label: p.name, value: p.id })))
const isLibraryEmpty = computed(() => !stats.value || !stats.value.song_count)

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

function resetDetailState() {
  selectedArtist.value = null
  selectedAlbum.value = null
  selectedPlaylist.value = null
}

// 切换二级列表 = 切换路由；同一 section 重复点击时只刷新
function switchSection(key) {
  const next = normalizeSection(key)
  resetDetailState()
  if (route.params.section !== next) {
    router.replace({ name: 'Player', params: { section: next } })
  }
  if (section.value === next) {
    refresh()
    return
  }
  section.value = next
  refresh()
}

// 深链、浏览器前进后退都由路由驱动 section
watch(
  () => route.params.section,
  (value) => {
    const next = normalizeSection(value)
    if (next === section.value) return
    resetDetailState()
    section.value = next
    refresh()
  },
)

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
    const res = await fetchRandomPool({ q: songsQuery.value || undefined })
    const items = res.data?.items || []
    if (!items.length) return
    player.playShuffledList(items)
    message.success(`已随机加载 ${items.length} 首可播放歌曲到播放队列`)
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
</script>

<style scoped>
/* 播放器页只承载列表；「正在播放」大视图由 GlobalPlayerDrawer 统一承担 */
.player-page {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.player-body {
  min-width: 0;
}
/* 桌面端的二级导航在系统侧边栏；这里只在移动端出现 */
.player-tabs {
  display: none;
}

.content-actions {
  position: sticky;
  top: 0;
  z-index: 5;
  padding: 0 0 10px 10px;
  margin: -4px -4px 0 0;
  border-radius: 0 0 0 18px;
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--sp-ui-body) 90%, transparent),
    color-mix(in srgb, var(--sp-ui-body) 0%, transparent)
  );
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
  border: 1px dashed color-mix(in srgb, var(--sp-ui-text-3) 30%, transparent);
  border-radius: 16px;
  background: var(--sp-ui-hover);
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(136px, 1fr));
  gap: 14px;
  padding-bottom: 12px;
}
.card-grid-empty {
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
  color: var(--sp-ui-text-3);
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
  color: var(--sp-ui-text-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.card-actions {
  margin-top: 8px;
}

/* ---------- 移动端（≤768px）：顶部横向二级 Tab + 全宽列表 ---------- */
@media (max-width: 768px) {
  .player-tabs {
    display: flex;
    gap: 6px;
    align-items: center;
    overflow-x: auto;
    overflow-y: hidden;
    padding-bottom: 10px;
    scrollbar-width: none;
  }
  .player-tabs::-webkit-scrollbar {
    display: none;
  }
  .player-tab {
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 7px 12px;
    font-size: 13px;
    line-height: 1;
    white-space: nowrap;
    color: var(--sp-ui-text-2);
    background: transparent;
    border: 1px solid transparent;
    border-radius: 999px;
    cursor: pointer;
    transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
  }
  .player-tab:hover {
    background: var(--sp-ui-hover);
  }
  .player-tab.active {
    color: var(--sp-ui-primary);
    background: var(--sp-ui-primary-soft);
    border-color: color-mix(in srgb, var(--sp-ui-primary) 35%, transparent);
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
</style>
