<template>
  <div class="dashboard-page" :class="{ mobile: isMobile }">
    <section class="hero">
      <div class="hero-main">
        <div class="hero-kicker">拾音 Sonpick</div>
        <h1 class="hero-title">{{ greeting }}</h1>
        <p class="hero-sub">
          曲库 {{ stats.song_count || 0 }} 首 · 总时长 {{ formatDuration(stats.total_duration) }}
          <span v-if="stats.total_size"> · {{ formatSize(stats.total_size) }}</span>
        </p>
        <div class="hero-chips">
          <button type="button" class="chip primary" @click="go('/download')">
            <n-icon size="16"><CloudDownloadOutline /></n-icon>
            搜索下载
          </button>
          <button type="button" class="chip" @click="go('/player')">
            <n-icon size="16"><PlayCircleOutline /></n-icon>
            播放器
          </button>
          <button type="button" class="chip" @click="go('/library')">
            <n-icon size="16"><LibraryOutline /></n-icon>
            曲库
          </button>
          <button type="button" class="chip ghost" @click="reload" :disabled="loading">
            <n-icon size="16" :class="{ spin: loading }"><RefreshOutline /></n-icon>
            刷新
          </button>
        </div>
      </div>

      <div class="hero-now" @click="openNowPlaying">
        <template v-if="player.current">
          <img
            v-if="player.cover && !nowCoverBroken"
            :src="player.cover"
            class="now-cover"
            alt=""
            @error="nowCoverBroken = true"
          />
          <div v-else class="now-cover placeholder">
            <n-icon size="22"><MusicalNotesOutline /></n-icon>
          </div>
          <div class="now-meta">
            <div class="now-label">{{ player.playing ? '正在播放' : '最近选中' }}</div>
            <div class="now-title">{{ player.current.title || '未知歌曲' }}</div>
            <div class="now-artist">{{ player.current.artist || player.current.album || '未知艺术家' }}</div>
          </div>
          <n-button quaternary circle class="now-play" @click.stop="player.togglePlay()">
            <n-icon size="22">
              <PauseOutline v-if="player.playing" />
              <PlayOutline v-else />
            </n-icon>
          </n-button>
        </template>
        <template v-else>
          <div class="now-cover placeholder">
            <n-icon size="22"><MusicalNotesOutline /></n-icon>
          </div>
          <div class="now-meta">
            <div class="now-label">尚未播放</div>
            <div class="now-title">从曲库或最近播放开始</div>
            <div class="now-artist">点这里打开播放器</div>
          </div>
        </template>
      </div>
    </section>

    <section class="kpi-grid">
      <article v-for="item in kpiItems" :key="item.key" class="kpi-card" @click="item.to && go(item.to)">
        <div class="kpi-icon" :style="{ background: item.bg, color: item.color }">
          <n-icon size="18"><component :is="item.icon" /></n-icon>
        </div>
        <div class="kpi-body">
          <div class="kpi-label">{{ item.label }}</div>
          <div class="kpi-value">{{ item.value }}</div>
          <div v-if="item.hint" class="kpi-hint">{{ item.hint }}</div>
        </div>
      </article>
    </section>

    <section class="main-grid">
      <div class="panel recent-panel">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">最近播放</h2>
            <p class="panel-desc">继续上次听到的位置</p>
          </div>
          <n-button text type="primary" @click="go('/player')">全部</n-button>
        </div>

        <n-spin :show="loadingHistory">
          <n-empty v-if="!history.length && !loadingHistory" description="还没有播放记录" size="small">
            <template #extra>
              <n-button size="small" type="primary" @click="go('/library')">去曲库挑几首</n-button>
            </template>
          </n-empty>
          <div v-else class="recent-list">
            <button
              v-for="(row, idx) in history"
              :key="row.id || `${row.song_id}-${idx}`"
              type="button"
              class="recent-item"
              @click="playHistory(row)"
            >
              <img
                v-if="row.song?.id && coverOf(row.song) && !brokenCovers[row.song.id]"
                :src="coverOf(row.song)"
                class="recent-cover"
                alt=""
                @error="markCoverBroken(row.song.id)"
              />
              <div v-else class="recent-cover placeholder">
                <n-icon size="18"><MusicalNotesOutline /></n-icon>
              </div>
              <div class="recent-meta">
                <div class="recent-title">{{ row.song?.title || '未知歌曲' }}</div>
                <div class="recent-sub">
                  {{ row.song?.artist || '未知艺术家' }}
                  <span v-if="row.played_at"> · {{ formatRelative(row.played_at) }}</span>
                </div>
              </div>
              <n-icon class="recent-play" size="18"><PlayOutline /></n-icon>
            </button>
          </div>
        </n-spin>
      </div>

      <div class="side-stack">
        <div class="panel">
          <div class="panel-head">
            <div>
              <h2 class="panel-title">元信息完整度</h2>
              <p class="panel-desc">封面 / 歌词 / 时长覆盖率</p>
            </div>
          </div>
          <div class="meta-list">
            <div v-for="m in metaItems" :key="m.key" class="meta-item">
              <div class="meta-top">
                <span>{{ m.label }}</span>
                <strong>{{ m.pct }}%</strong>
              </div>
              <div class="meta-bar">
                <div class="meta-fill" :style="{ width: `${m.pct}%`, background: m.color }"></div>
              </div>
              <div class="meta-foot">{{ m.count }} / {{ stats.song_count || 0 }} 首</div>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <div>
              <h2 class="panel-title">曲库源</h2>
              <p class="panel-desc">连通状态与曲目规模</p>
            </div>
            <n-button text type="primary" @click="go({ path: '/library', query: { manage: '1' } })">管理</n-button>
          </div>
          <n-empty v-if="!(stats.sources || []).length" description="暂无曲库源" size="small" />
          <div v-else class="source-list">
            <div v-for="s in stats.sources" :key="s.id" class="source-item">
              <div class="source-top">
                <div class="source-name-row">
                  <span class="source-dot" :class="statusClass(s.connection_status)"></span>
                  <strong class="source-name">{{ s.name }}</strong>
                </div>
                <n-tag size="small" :bordered="false" :type="s.type === 'webdav' ? 'info' : 'success'">
                  {{ s.type === 'webdav' ? 'WebDAV' : '本地' }}
                </n-tag>
              </div>
              <div class="source-sub">
                {{ s.song_count || 0 }} 首 · {{ statusLabel(s.connection_status) }}
                <span v-if="s.is_default_upload"> · 默认上传</span>
              </div>
              <div v-if="s.last_scan_at" class="source-scan">最近扫描 {{ formatRelative(s.last_scan_at) }}</div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="bottom-grid">
      <div class="panel">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">最近动态</h2>
            <p class="panel-desc">下载 / 上传 / 转码 / 删除</p>
          </div>
          <n-button text type="primary" @click="go('/logs')">日志</n-button>
        </div>
        <n-spin :show="loadingLogs">
          <n-empty v-if="!logs.length && !loadingLogs" description="暂无操作记录" size="small" />
          <div v-else class="activity-list">
            <div v-for="row in logs" :key="row.id" class="activity-item">
              <div class="activity-icon" :class="`act-${row.action || 'other'}`">
                <n-icon size="15"><component :is="actionIcon(row.action)" /></n-icon>
              </div>
              <div class="activity-body">
                <div class="activity-title">
                  <span>{{ row.title || actionLabel(row.action) }}</span>
                  <n-tag size="small" :bordered="false" :type="statusTagType(row.status)">{{ row.status || '-' }}</n-tag>
                </div>
                <div class="activity-sub">
                  {{ actionLabel(row.action) }}
                  <span v-if="row.created_at"> · {{ formatRelative(row.created_at) }}</span>
                </div>
                <div v-if="row.message" class="activity-msg">{{ row.message }}</div>
              </div>
            </div>
          </div>
        </n-spin>
      </div>

      <div class="panel">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">快捷入口</h2>
            <p class="panel-desc">常用操作一键直达</p>
          </div>
        </div>
        <div class="action-grid">
          <button
            v-for="a in quickActions"
            :key="a.key"
            type="button"
            class="action-tile"
            @click="go(a.to)"
          >
            <div class="action-icon" :style="{ background: a.bg, color: a.color }">
              <n-icon size="18"><component :is="a.icon" /></n-icon>
            </div>
            <div class="action-text">
              <div class="action-title">{{ a.title }}</div>
              <div class="action-desc">{{ a.desc }}</div>
            </div>
          </button>
        </div>

        <div class="task-summary">
          <div class="task-summary-head">
            <span>任务概况</span>
            <n-tag size="small" :bordered="false" :type="activeTaskCount ? 'info' : 'default'">
              {{ activeTaskCount ? `${activeTaskCount} 个进行中` : '空闲' }}
            </n-tag>
          </div>
          <div class="task-summary-body">
            <div>
              <strong>{{ tasks.running || 0 }}</strong>
              <span>运行</span>
            </div>
            <div>
              <strong>{{ tasks.pending || 0 }}</strong>
              <span>排队</span>
            </div>
            <div>
              <strong>{{ recentTaskHint }}</strong>
              <span>最近完成</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  AlbumsOutline,
  CloudDownloadOutline,
  CloudUploadOutline,
  DocumentTextOutline,
  HeartOutline,
  LibraryOutline,
  ListOutline,
  MusicalNotesOutline,
  PauseOutline,
  PeopleOutline,
  PlayCircleOutline,
  PlayOutline,
  RefreshOutline,
  SettingsOutline,
  SwapHorizontalOutline,
  TrashOutline,
} from '@vicons/ionicons5'
import api from '@/api/client'
import { coverUrl, fetchHistory, fetchLibraryStats, listTasks } from '@/api/music'
import { useIsMobile } from '@/composables/useIsMobile'
import { useAuthStore } from '@/stores/auth'
import { usePlayerStore } from '@/stores/player'

const router = useRouter()
const message = useMessage()
const isMobile = useIsMobile()
const auth = useAuthStore()
const player = usePlayerStore()

const loading = ref(false)
const loadingHistory = ref(false)
const loadingLogs = ref(false)
const nowCoverBroken = ref(false)
const brokenCovers = ref({})
const history = ref([])
const logs = ref([])
const recentCompleted = ref(0)

const stats = ref({
  song_count: 0,
  artist_count: 0,
  album_count: 0,
  favorite_count: 0,
  playlist_count: 0,
  total_duration: 0,
  total_size: 0,
  meta_completeness: {},
  sources: [],
  tasks: {},
})

const meta = computed(() => stats.value.meta_completeness || {})
const tasks = computed(() => stats.value.tasks || {})
const activeTaskCount = computed(() => Number(tasks.value.pending || 0) + Number(tasks.value.running || 0))
const recentTaskHint = computed(() => recentCompleted.value || 0)

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了，放点安静的'
  if (h < 11) return '早上好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  if (h < 22) return '晚上好'
  return '夜听时光'
})

const kpiItems = computed(() => [
  {
    key: 'songs',
    label: '歌曲',
    value: stats.value.song_count || 0,
    hint: formatDuration(stats.value.total_duration),
    icon: MusicalNotesOutline,
    color: '#0f766e',
    bg: 'rgba(15,118,110,.12)',
    to: '/library',
  },
  {
    key: 'artists',
    label: '艺术家',
    value: stats.value.artist_count || 0,
    hint: `${stats.value.album_count || 0} 张专辑`,
    icon: PeopleOutline,
    color: '#1d4ed8',
    bg: 'rgba(29,78,216,.12)',
    to: '/library',
  },
  {
    key: 'fav',
    label: '收藏',
    value: stats.value.favorite_count || 0,
    hint: `${stats.value.playlist_count || 0} 个歌单`,
    icon: HeartOutline,
    color: '#be123c',
    bg: 'rgba(190,18,60,.12)',
    to: '/player',
  },
  {
    key: 'tasks',
    label: '任务',
    value: `${tasks.value.running || 0}/${tasks.value.pending || 0}`,
    hint: activeTaskCount.value ? '运行 / 排队' : '当前空闲',
    icon: ListOutline,
    color: '#b45309',
    bg: 'rgba(180,83,9,.12)',
  },
  {
    key: 'size',
    label: '体量',
    value: formatSize(stats.value.total_size || 0),
    hint: '本地曲目合计',
    icon: AlbumsOutline,
    color: '#0f766e',
    bg: 'rgba(15,118,110,.10)',
    to: '/library',
  },
  {
    key: 'sources',
    label: '曲库源',
    value: (stats.value.sources || []).length,
    hint: sourceHealthHint.value,
    icon: LibraryOutline,
    color: '#0369a1',
    bg: 'rgba(3,105,161,.12)',
    to: { path: '/library', query: { manage: '1' } },
  },
])

const metaItems = computed(() => [
  {
    key: 'cover',
    label: '封面',
    pct: pctNum(meta.value.cover_pct),
    count: meta.value.cover_count ?? Math.round((pctNum(meta.value.cover_pct) / 100) * (stats.value.song_count || 0)),
    color: '#18a058',
  },
  {
    key: 'lyrics',
    label: '歌词',
    pct: pctNum(meta.value.lyrics_pct),
    count: meta.value.lyrics_count ?? Math.round((pctNum(meta.value.lyrics_pct) / 100) * (stats.value.song_count || 0)),
    color: '#2080f0',
  },
  {
    key: 'duration',
    label: '时长',
    pct: pctNum(meta.value.duration_pct),
    count: meta.value.duration_count ?? Math.round((pctNum(meta.value.duration_pct) / 100) * (stats.value.song_count || 0)),
    color: '#f0a020',
  },
])

const sourceHealthHint = computed(() => {
  const rows = stats.value.sources || []
  if (!rows.length) return '未配置'
  const ok = rows.filter((s) => s.connection_status === 'ok').length
  if (ok === rows.length) return '全部正常'
  return `${ok}/${rows.length} 正常`
})

const quickActions = [
  { key: 'download', title: '搜索下载', desc: 'QQ 音乐搜歌入库', icon: CloudDownloadOutline, color: '#0f766e', bg: 'rgba(15,118,110,.12)', to: '/download' },
  { key: 'player', title: '打开播放器', desc: '舞台 / 队列 / 歌词', icon: PlayCircleOutline, color: '#15803d', bg: 'rgba(21,128,61,.12)', to: '/player' },
  { key: 'library', title: '管理曲库', desc: '浏览、扫描、整理', icon: LibraryOutline, color: '#1d4ed8', bg: 'rgba(29,78,216,.12)', to: '/library' },
  { key: 'sources', title: '曲库源', desc: '本地 / WebDAV 配置', icon: CloudUploadOutline, color: '#0369a1', bg: 'rgba(3,105,161,.12)', to: { path: '/library', query: { manage: '1' } } },
  { key: 'logs', title: '操作日志', desc: '下载上传删除记录', icon: DocumentTextOutline, color: '#b45309', bg: 'rgba(180,83,9,.12)', to: '/logs' },
  { key: 'settings', title: '系统设置', desc: '路径、格式、刮削源', icon: SettingsOutline, color: '#475569', bg: 'rgba(71,85,105,.12)', to: '/settings' },
]

watch(() => player.cover, () => {
  nowCoverBroken.value = false
})

function go(to) {
  router.push(to)
}

function openNowPlaying() {
  if (isMobile.value && player.current) {
    player.fullPlayerOpen = true
  }
  go('/player')
}

function pctNum(v) {
  const n = Number(v || 0)
  if (n <= 1 && n > 0) return Math.round(n * 100)
  return Math.max(0, Math.min(100, Math.round(n)))
}

function statusLabel(s) {
  return ({ ok: '连通正常', failed: '连通失败', not_configured: '未配置', unknown: '未知' })[s] || s || '未知'
}

function statusClass(s) {
  if (s === 'ok') return 'ok'
  if (s === 'failed') return 'fail'
  return 'muted'
}

function statusTagType(s) {
  return ({ success: 'success', failed: 'error', skipped: 'warning', ok: 'success' })[s] || 'default'
}

function actionLabel(a) {
  return ({ download: '下载', upload: '上传', delete: '删除', convert: '转码', scrape: '刮削', scan: '扫描' })[a] || a || '操作'
}

function actionIcon(a) {
  return ({
    download: CloudDownloadOutline,
    upload: CloudUploadOutline,
    delete: TrashOutline,
    convert: SwapHorizontalOutline,
  })[a] || DocumentTextOutline
}

function coverOf(song) {
  if (!song?.id) return ''
  return coverUrl(song.id, auth.token)
}

function markCoverBroken(id) {
  brokenCovers.value = { ...brokenCovers.value, [id]: true }
}

function formatDuration(sec) {
  const s = Math.max(0, Math.floor(Number(sec) || 0))
  if (!s) return '0 分钟'
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (h) return `${h} 小时 ${m} 分`
  if (m) return `${m} 分钟`
  return `${s} 秒`
}

function formatSize(bytes) {
  const n = Number(bytes) || 0
  if (n <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let v = n
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i += 1
  }
  return `${v >= 10 || i === 0 ? v.toFixed(0) : v.toFixed(1)} ${units[i]}`
}

function formatRelative(value) {
  if (!value) return ''
  const t = new Date(value).getTime()
  if (Number.isNaN(t)) return ''
  const diff = Date.now() - t
  const sec = Math.round(diff / 1000)
  if (sec < 60) return '刚刚'
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min} 分钟前`
  const hour = Math.floor(min / 60)
  if (hour < 24) return `${hour} 小时前`
  const day = Math.floor(hour / 24)
  if (day < 30) return `${day} 天前`
  try {
    return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}

function playHistory(row) {
  const song = row?.song
  if (!song?.id) {
    message.warning('该记录没有可播放歌曲')
    return
  }
  const list = history.value.map((h) => h.song).filter((s) => s?.id)
  if (list.length) player.playList(list, list.findIndex((s) => s.id === song.id))
  else player.play(song)
}

async function loadStats() {
  const res = await fetchLibraryStats()
  stats.value = res.data || stats.value
}

async function loadHistory() {
  loadingHistory.value = true
  try {
    const res = await fetchHistory(12)
    const rows = res.data || res || []
    history.value = Array.isArray(rows) ? rows.slice(0, 8) : []
  } catch (err) {
    history.value = []
  } finally {
    loadingHistory.value = false
  }
}

async function loadLogs() {
  loadingLogs.value = true
  try {
    const res = await api.get('/logs', { params: { limit: 8 } })
    logs.value = res.data || []
  } catch (err) {
    logs.value = []
  } finally {
    loadingLogs.value = false
  }
}

async function loadTaskHint() {
  try {
    const res = await listTasks()
    const rows = res.data || res || []
    recentCompleted.value = (Array.isArray(rows) ? rows : [])
      .filter((t) => t.status === 'completed')
      .slice(0, 20).length
  } catch {
    recentCompleted.value = 0
  }
}

async function reload() {
  loading.value = true
  try {
    await Promise.all([loadStats(), loadHistory(), loadLogs(), loadTaskHint()])
  } catch (err) {
    message.error(err?.response?.data?.detail || err?.message || '加载概览失败')
  } finally {
    loading.value = false
  }
}

onMounted(reload)
</script>

<style scoped>
.dashboard-page {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.hero {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(260px, 0.9fr);
  gap: 14px;
  padding: 18px;
  border: 1px solid var(--border-color, rgba(127,127,127,.18));
  border-radius: 14px;
  background:
    radial-gradient(1200px 240px at 0% 0%, color-mix(in srgb, #18a058 16%, transparent), transparent 60%),
    color-mix(in srgb, var(--card-color, var(--n-card-color)) 94%, #18a058 6%);
  box-shadow: 0 14px 34px rgba(21, 32, 53, .06);
}

.hero-kicker {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .04em;
  color: color-mix(in srgb, #18a058 80%, var(--text-color-3, #8a8f99));
  margin-bottom: 6px;
}

.hero-title {
  margin: 0;
  font-size: 28px;
  line-height: 1.2;
  font-weight: 780;
}

.hero-sub {
  margin: 8px 0 0;
  color: var(--text-color-3, #8a8f99);
  font-size: 13px;
}

.hero-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px solid var(--border-color, rgba(127,127,127,.2));
  background: color-mix(in srgb, var(--card-color, var(--n-card-color)) 88%, transparent);
  color: inherit;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
}

.chip.primary {
  background: #18a058;
  border-color: #18a058;
  color: #fff;
}

.chip.ghost {
  background: transparent;
}

.chip:disabled {
  opacity: .6;
  cursor: default;
}

.hero-now {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  padding: 14px;
  border-radius: 12px;
  border: 1px solid color-mix(in srgb, var(--border-color, rgba(127,127,127,.2)) 80%, transparent);
  background: color-mix(in srgb, var(--card-color, var(--n-card-color)) 82%, transparent);
  cursor: pointer;
  transition: transform .15s ease, box-shadow .15s ease;
}

.hero-now:hover {
  transform: translateY(-1px);
  box-shadow: 0 10px 22px rgba(21, 32, 53, .08);
}

.now-cover,
.recent-cover {
  width: 56px;
  height: 56px;
  border-radius: 10px;
  object-fit: cover;
  flex-shrink: 0;
  background: rgba(127,127,127,.12);
}

.now-cover.placeholder,
.recent-cover.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-color-3, #8a8f99);
}

.now-meta,
.recent-meta {
  min-width: 0;
  flex: 1;
}

.now-label,
.panel-desc,
.kpi-hint,
.kpi-label,
.meta-foot,
.source-sub,
.source-scan,
.activity-sub,
.activity-msg,
.action-desc,
.task-summary-body span {
  color: var(--text-color-3, #8a8f99);
  font-size: 12px;
}

.now-title,
.recent-title,
.action-title,
.activity-title span,
.source-name,
.panel-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.now-title {
  font-size: 15px;
  font-weight: 720;
  margin-top: 2px;
}

.now-artist,
.recent-sub {
  margin-top: 2px;
  font-size: 12px;
  color: var(--text-color-3, #8a8f99);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
}

.kpi-card,
.panel {
  border: 1px solid var(--border-color, rgba(127,127,127,.18));
  border-radius: 12px;
  background: color-mix(in srgb, var(--card-color, var(--n-card-color)) 94%, transparent);
  box-shadow: 0 10px 24px rgba(21, 32, 53, .05);
}

.kpi-card {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 14px;
  cursor: pointer;
  transition: transform .15s ease, box-shadow .15s ease;
  min-height: 96px;
}

.kpi-card:hover {
  transform: translateY(-1px);
  box-shadow: 0 12px 26px rgba(21, 32, 53, .08);
}

.kpi-icon,
.action-icon,
.activity-icon {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.kpi-body {
  min-width: 0;
}

.kpi-value {
  margin-top: 4px;
  font-size: 22px;
  font-weight: 760;
  line-height: 1.15;
}

.kpi-hint {
  margin-top: 4px;
}

.main-grid,
.bottom-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(280px, 0.9fr);
  gap: 14px;
  align-items: start;
}

.side-stack {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}

.panel {
  padding: 14px;
  min-width: 0;
}

.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.panel-title {
  margin: 0;
  font-size: 16px;
  font-weight: 720;
}

.panel-desc {
  margin: 4px 0 0;
}

.recent-list,
.source-list,
.activity-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.recent-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px;
  border-radius: 10px;
  border: 1px solid transparent;
  background: color-mix(in srgb, var(--body-color, transparent) 70%, transparent);
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.recent-item:hover {
  border-color: color-mix(in srgb, #18a058 35%, transparent);
  background: color-mix(in srgb, #18a058 8%, transparent);
}

.recent-cover {
  width: 44px;
  height: 44px;
  border-radius: 8px;
}

.recent-title {
  font-weight: 650;
  font-size: 14px;
}

.recent-play {
  color: var(--text-color-3, #8a8f99);
  flex-shrink: 0;
}

.meta-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.meta-top {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 13px;
  margin-bottom: 6px;
}

.meta-bar {
  height: 8px;
  border-radius: 999px;
  background: rgba(127,127,127,.14);
  overflow: hidden;
}

.meta-fill {
  height: 100%;
  border-radius: inherit;
}

.meta-foot {
  margin-top: 4px;
}

.source-item,
.activity-item {
  padding: 10px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--body-color, transparent) 72%, transparent);
}

.source-top,
.activity-title,
.task-summary-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.source-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.source-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #94a3b8;
  flex-shrink: 0;
}

.source-dot.ok { background: #18a058; }
.source-dot.fail { background: #d03050; }
.source-dot.muted { background: #94a3b8; }

.source-name {
  font-size: 13px;
}

.source-sub,
.source-scan {
  margin-top: 4px;
}

.activity-item {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.activity-icon {
  background: rgba(127,127,127,.12);
  color: #475569;
}

.activity-icon.act-download { background: rgba(15,118,110,.12); color: #0f766e; }
.activity-icon.act-upload { background: rgba(3,105,161,.12); color: #0369a1; }
.activity-icon.act-delete { background: rgba(190,18,60,.12); color: #be123c; }
.activity-icon.act-convert { background: rgba(180,83,9,.12); color: #b45309; }

.activity-body {
  min-width: 0;
  flex: 1;
}

.activity-title {
  font-size: 13px;
  font-weight: 650;
}

.activity-msg {
  margin-top: 3px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.action-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.action-tile {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  width: 100%;
  padding: 12px;
  border-radius: 10px;
  border: 1px solid var(--border-color, rgba(127,127,127,.16));
  background: color-mix(in srgb, var(--body-color, transparent) 70%, transparent);
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: transform .15s ease, border-color .15s ease;
}

.action-tile:hover {
  transform: translateY(-1px);
  border-color: color-mix(in srgb, #18a058 35%, transparent);
}

.action-text {
  min-width: 0;
}

.action-title {
  font-size: 13px;
  font-weight: 700;
}

.action-desc {
  margin-top: 2px;
}

.task-summary {
  margin-top: 12px;
  padding: 12px;
  border-radius: 10px;
  background: color-mix(in srgb, #18a058 8%, transparent);
  border: 1px solid color-mix(in srgb, #18a058 18%, transparent);
}

.task-summary-body {
  margin-top: 10px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.task-summary-body strong {
  display: block;
  font-size: 18px;
  font-weight: 760;
  line-height: 1.1;
}

.task-summary-body span {
  display: block;
  margin-top: 2px;
}

.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@media (max-width: 1200px) {
  .kpi-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .hero,
  .main-grid,
  .bottom-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .dashboard-page {
    gap: 12px;
  }

  .hero {
    padding: 14px;
    border-radius: 12px;
  }

  .hero-title {
    font-size: 24px;
  }

  .kpi-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
  }

  .kpi-card {
    min-height: 88px;
    padding: 12px;
  }

  .kpi-value {
    font-size: 18px;
  }

  .action-grid {
    grid-template-columns: 1fr;
  }

  .chip {
    flex: 1 1 calc(50% - 8px);
    justify-content: center;
  }
}
</style>
