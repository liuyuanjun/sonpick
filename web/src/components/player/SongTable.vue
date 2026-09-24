<template>
  <div ref="rootEl" class="song-table" :class="{ 'above-player': miniPlayerVisible }">
    <div class="toolbar">
      <n-space>
        <n-button type="primary" :disabled="!songs.length" @click="playPage">
          <template #icon><n-icon><play /></n-icon></template>
          播放本页（{{ songs.length }} 首）
        </n-button>
        <n-button v-if="serverPaginated" secondary :disabled="!total" :loading="playingAll" @click="emit('play-all-results')">
          <template #icon><n-icon><shuffle-outline /></n-icon></template>
          {{ hasActiveFilter ? '随机播放当前结果' : '随机播放全部' }}（{{ total }} 首）
        </n-button>
        <n-button quaternary :disabled="!songs.length" @click="enqueueAll">
          <template #icon><n-icon><add /></n-icon></template>
          加入队列
        </n-button>
      </n-space>
      <n-input
        v-if="showSearch"
        v-model:value="searchKeyword"
        clearable
        placeholder="筛选歌曲"
        class="search-input"
      />
    </div>

    <div v-if="visibleSongs.length" class="song-list" role="list">
      <div class="song-list-head">
        <span class="col-idx">#</span>
        <span class="col-main">歌曲 / 专辑</span>
        <span class="col-format">格式</span>
        <span class="col-size">大小</span>
        <span class="col-time">时长</span>
        <span class="col-actions"></span>
      </div>
      <div
        v-for="(row, i) in visibleSongs"
        :key="row.id"
        class="song-row"
        :class="{ 'is-playing': isCurrent(row) }"
        role="listitem"
        @click="onRowTap(row)"
        @dblclick="playAt(row)"
      >
        <span class="col-idx">
          <!-- 当前播放行：序号换成频谱动效，播放中跳动 / 暂停时定格 -->
          <span v-if="isCurrent(row)" class="eq" :class="{ paused: !player.playing }" aria-hidden="true">
            <i></i><i></i><i></i>
          </span>
          <template v-else>{{ i + 1 }}</template>
        </span>
        <div class="col-main song-cell">
          <div class="mini-cover-wrap">
            <img
              v-if="row.cover_path"
              class="mini-cover"
              :src="coverUrl(row.id, auth.token)"
              alt=""
              loading="lazy"
              @error="onCoverError($event)"
            />
            <div v-else class="mini-cover placeholder">
              <n-icon :size="16"><musical-notes /></n-icon>
            </div>
          </div>
          <div class="song-meta">
            <div class="song-title" :title="row.title || '未知歌曲'">{{ row.title || '未知歌曲' }}</div>
            <div class="song-sub" :title="subLine(row)">
              <span>{{ row.artist || '未知艺术家' }}</span>
              <template v-if="row.album">
                <span class="dot">·</span>
                <span>{{ row.album }}</span>
              </template>
            </div>
          </div>
        </div>
        <span class="col-format">
          <n-tooltip v-if="row.preferred_version" trigger="hover" :delay="300">
            <template #trigger>
              <span class="format-cell">
                <span class="format-name">{{ formatLabel(row.preferred_version.format) }}</span>
                <span v-if="row.preferred_version.version_count > 1" class="format-more">
                  +{{ row.preferred_version.version_count - 1 }}
                </span>
              </span>
            </template>
            <div class="version-tip">
              <div v-for="v in row.versions || []" :key="v.id" class="version-tip-row">
                {{ formatLabel(v.format) }} · {{ formatFileSize(v.file_size) }} ·
                {{ versionLocation(v) }}
                <template v-if="v.availability_status === 'unavailable'">（失效）</template>
              </div>
            </div>
          </n-tooltip>
          <span v-else class="col-muted" title="没有可用文件版本">—</span>
        </span>
        <span class="col-size">
          {{ row.preferred_version ? formatFileSize(row.preferred_version.file_size) : '—' }}
        </span>
        <span class="col-time">{{ formatClock(row.duration || 0) }}</span>
        <div class="col-actions">
          <n-button v-if="!isMobile" quaternary circle size="tiny" class="hover-only" @click.stop="playAt(row)">
            <n-icon :size="16"><play /></n-icon>
          </n-button>
          <n-button
            quaternary
            circle
            :size="isMobile ? 'small' : 'tiny'"
            :type="row.is_favorite ? 'error' : 'default'"
            class="hover-only"
            :class="{ 'is-fav': row.is_favorite }"
            @click.stop="toggleFav(row)"
          >
            <n-icon :size="16">
              <heart v-if="row.is_favorite" />
              <heart-outline v-else />
            </n-icon>
          </n-button>
          <n-button
            quaternary
            circle
            :size="isMobile ? 'small' : 'tiny'"
            class="hover-only"
            @click.stop="onAddOrRemove(row)"
          >
            <n-icon :size="16"><add /></n-icon>
          </n-button>
          <n-button
            quaternary
            circle
            :size="isMobile ? 'small' : 'tiny'"
            class="hover-only"
            aria-label="查看歌曲信息"
            @click.stop="openInfo(row)"
          >
            <n-icon :size="16"><information-circle-outline /></n-icon>
          </n-button>
        </div>
      </div>
    </div>
    <n-empty v-else description="暂无歌曲" class="song-table-empty" />
    <!-- 只有一页时不浮条：一行静态总数即可，避免空的分页控件占视觉 -->
    <div v-if="serverPaginated && totalPages <= 1" class="total-line">
      <n-text depth="3">共 {{ total }} 首</n-text>
    </div>
    <div v-else-if="serverPaginated" class="pagination-bar" :class="[`tier-${paginationTier}`, { 'with-total': showTotalText }]">
      <n-text depth="3" class="total-text">共 {{ total }} 首</n-text>
      <div v-if="paginationTier === 'simple'" class="simple-pager">
        <n-button quaternary circle size="small" :disabled="page <= 1" aria-label="上一页" @click="changePage(page - 1)">
          <n-icon :size="16"><chevron-back /></n-icon>
        </n-button>
        <span class="page-indicator">{{ page }} / {{ totalPages }}</span>
        <n-button quaternary circle size="small" :disabled="page >= totalPages" aria-label="下一页" @click="changePage(page + 1)">
          <n-icon :size="16"><chevron-forward /></n-icon>
        </n-button>
      </div>
      <n-pagination
        v-else
        :page="page"
        :page-size="pageSize"
        :item-count="total"
        :page-slot="pageSlot"
        @update:page="changePage"
      />
    </div>

    <song-info-modal v-model:show="infoVisible" :song="infoSong" />
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useMessage } from 'naive-ui'
import {
  Play,
  Heart,
  HeartOutline,
  Add,
  MusicalNotes,
  ChevronBack,
  ChevronForward,
  ShuffleOutline,
  InformationCircleOutline,
} from '@vicons/ionicons5'
import { usePlayerStore } from '@/stores/player'
import { addFavorite, removeFavorite, coverUrl } from '@/api/music'
import { useAuthStore } from '@/stores/auth'
import { useIsMobile } from '@/composables/useIsMobile'
import { formatClock, formatFileSize } from '@/utils/format'
import { formatLabel, versionLocationLabel } from '@/utils/media'
import SongInfoModal from '@/components/player/SongInfoModal.vue'

const props = defineProps({
  songs: { type: Array, default: () => [] },
  showSearch: { type: Boolean, default: true },
  playlistId: { type: Number, default: null },
  serverPaginated: { type: Boolean, default: false },
  total: { type: Number, default: 0 },
  page: { type: Number, default: 1 },
  pageSize: { type: Number, default: 100 },
  searchValue: { type: String, default: '' },
  playingAll: { type: Boolean, default: false },
})

const emit = defineEmits(['changed', 'add-to-playlist', 'remove-from-playlist', 'search', 'page-change', 'play-all-results'])

const player = usePlayerStore()
const auth = useAuthStore()
const message = useMessage()
const keyword = ref('')
const isMobile = useIsMobile()

const searchKeyword = computed({
  get: () => props.serverPaginated ? props.searchValue : keyword.value,
  set: (value) => {
    if (props.serverPaginated) emit('search', value)
    else keyword.value = value
  },
})

const hasActiveFilter = computed(() => Boolean(props.searchValue.trim()))

// 分页渐进降级：按容器自身宽度分档（桌面三栏布局下列宽与视口无关，不能用媒体查询）
// 容器 ≥550px（full）：总数 + 9 页码 28px —— 中间列限宽 600px 下，视口 ≥1408px 即触达
// 容器 430~550px（compact）：隐藏总数 + 7 页码 24px
// 容器 <430px（simple）：‹ 页/总 › 极简翻页 —— 约视口 <1200px 触达
const rootEl = ref(null)
const containerWidth = ref(1200)
let resizeObserver = null

onMounted(() => {
  if (typeof ResizeObserver === 'undefined' || !rootEl.value) return
  resizeObserver = new ResizeObserver((entries) => {
    containerWidth.value = entries[0]?.contentRect?.width || 1200
  })
  resizeObserver.observe(rootEl.value)
})
onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
})

const paginationTier = computed(() => {
  const w = containerWidth.value
  if (w < 430) return 'simple'
  if (w < 550) return 'compact'
  return 'full'
})
const showTotalText = computed(() => paginationTier.value === 'full')
const pageSlot = computed(() => (paginationTier.value === 'full' ? 9 : 7))
const totalPages = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)))

// 当前播放行高亮（列表唯一的播放态指示）
const isCurrent = (row) => player.current?.id === row.id
// 底部悬浮胶囊显示时，吸附分页栏要抬高到胶囊之上
const miniPlayerVisible = computed(() => player.showPlayer && !!player.current)

// 翻页后回到列表顶部：吸附分页栏意味着翻页时用户多半在列表中段，
// 不滚回去会落在下一页的中间位置。scrollIntoView 对嵌套滚动容器同样生效。
function changePage(page) {
  emit('page-change', page)
  rootEl.value?.scrollIntoView({ block: 'start' })
}

// 移动端没有双击概念，单击行即播放
function onRowTap(row) {
  if (isMobile.value) playAt(row)
}

const visibleSongs = computed(() => {
  if (props.serverPaginated) return props.songs
  const k = keyword.value.trim().toLowerCase()
  if (!k) return props.songs
  return props.songs.filter((s) => {
    const blob = `${s.title || ''} ${s.artist || ''} ${s.album || ''}`.toLowerCase()
    return blob.includes(k)
  })
})

function subLine(row) {
  return [row.artist, row.album].filter(Boolean).join(' · ')
}

// 「信息」弹窗：整表共用一个实例，避免每行各挂一个 modal
const infoVisible = ref(false)
const infoSong = ref(null)

function openInfo(row) {
  infoSong.value = row
  infoVisible.value = true
}

function versionLocation(v) {
  return versionLocationLabel(v)
}

function playAt(row) {
  const list = visibleSongs.value
  const idx = list.findIndex((s) => s.id === row.id)
  player.playList(list, idx >= 0 ? idx : 0)
}

function playPage() {
  if (!props.songs.length) return
  player.playList(props.songs, 0)
}

function enqueueAll() {
  player.enqueue(visibleSongs.value)
  message.success('已加入播放队列')
}

async function toggleFav(row) {
  try {
    if (row.is_favorite) {
      await removeFavorite(row.id)
      row.is_favorite = false
      message.success('已取消喜欢')
    } else {
      await addFavorite(row.id)
      row.is_favorite = true
      message.success('已加入我喜欢的')
    }
    emit('changed')
  } catch (e) {
    message.error(e.response?.data?.detail || '操作失败')
  }
}

function onAddOrRemove(row) {
  if (props.playlistId) emit('remove-from-playlist', row)
  else emit('add-to-playlist', row)
}

function onCoverError(e) {
  const img = e?.target
  if (img) {
    img.style.display = 'none'
    const wrap = img.parentElement
    if (wrap && !wrap.querySelector('.placeholder')) {
      const ph = document.createElement('div')
      ph.className = 'mini-cover placeholder'
      ph.innerHTML = '♪'
      wrap.appendChild(ph)
    }
  }
}
</script>

<style scoped>
.song-table {
  padding-bottom: 8px;
  min-width: 0;
  max-width: 100%;
}
/* 宽屏限宽居中：消除中间 1fr 列被无限拉伸产生的大段空白（Spotify/Apple Music 同款处理） */
@media (min-width: 1300px) {
  .song-table {
    max-width: 1200px;
    margin: 0 auto;
  }
}
.song-table-empty {
  min-height: 240px;
  justify-content: center;
  padding: 36px 0;
}
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  gap: 12px;
  flex-wrap: wrap;
}
.search-input {
  width: min(260px, 100%);
}
.total-line {
  margin-top: 14px;
  padding: 0 6px;
  font-size: var(--sp-fs-caption);
}
.pagination-bar {
  position: sticky;
  bottom: 12px;
  z-index: 4;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
  padding: 10px 12px;
  font-size: var(--sp-fs-caption);
  border: 1px solid rgba(127, 127, 127, 0.16);
  border-radius: var(--sp-radius-xl);
  background: color-mix(in srgb, var(--sp-ui-card) 92%, transparent);
  box-shadow:
    0 1px 3px rgba(0, 0, 0, 0.06),
    0 8px 24px rgba(0, 0, 0, 0.10);
  backdrop-filter: blur(14px);
}
/*
  悬浮播放胶囊出现时：吸附分页栏抬高到胶囊之上避免遮挡，
  并从全宽条收成紧凑居中胶囊——与播放胶囊构成一个悬浮簇，
  避免两条全宽浮条上下堆叠的笨重感。
*/
.song-table.above-player .pagination-bar {
  bottom: calc(var(--gp-reserve) + 4px);
  width: fit-content;
  margin-left: auto;
  margin-right: auto;
  padding: 6px 14px;
  border-radius: var(--sp-radius-pill);
  transition: bottom 0.2s ease;
}
.pagination-bar :deep(.n-pagination) {
  justify-content: flex-end;
  font-size: var(--sp-fs-caption);
  --n-font-size: var(--sp-fs-caption);
  --n-item-border-radius: var(--sp-radius-sm);
}

/* 分页渐进降级（tier/with-total 由 ResizeObserver 按容器宽度计算，见 script） */
.pagination-bar:not(.with-total) .total-text {
  display: none;
}
.pagination-bar.tier-compact :deep(.n-pagination) {
  flex: 1 1 auto;
  min-width: 0;
  justify-content: flex-end;
  /* Naive 主题变量以内联样式挂在组件根上，需 !important 覆盖 */
  --n-item-size: 24px !important;
  --n-item-padding: 0 2px !important;
  --n-item-margin: 0 0 0 4px !important;
}
.pagination-bar.tier-compact:not(.with-total) :deep(.n-pagination) {
  justify-content: center;
}
.simple-pager {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}
.page-indicator {
  font-size: var(--sp-fs-caption);
  color: var(--sp-ui-text-2);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  min-width: 44px;
  text-align: center;
}

.song-list {
  width: 100%;
  min-width: 0;
  border-top: 1px solid rgba(127, 127, 127, 0.12);
}
.song-list-head,
.song-row {
  display: grid;
  /* 序号 | 主信息(限宽) | 格式 | 大小 | 时长 | 操作 */
  grid-template-columns: 52px minmax(0, 1fr) 66px 78px 56px 108px;
  gap: 8px;
  align-items: center;
  min-width: 0;
}
.song-list-head {
  /* 吸附列头：长列表滚动时保住列语义（依赖 LayoutView 的 sticky 穿透修复） */
  position: sticky;
  top: 0;
  z-index: 3;
  padding: 8px 6px;
  font-size: var(--sp-fs-caption);
  color: var(--sp-ui-text-3);
  background: var(--sp-ui-body);
  border-bottom: 1px solid rgba(127, 127, 127, 0.12);
}
.song-row {
  padding: 8px 6px;
  border-radius: var(--sp-radius-md);
  cursor: pointer;
  transition: background 0.12s ease;
  /* 细分隔线帮助 100 行长列表横向扫视对齐 */
  border-bottom: 1px solid rgba(127, 127, 127, 0.07);
}
.song-row:last-child {
  border-bottom: none;
}
.song-row:hover {
  background: color-mix(in srgb, var(--sp-ui-primary) 7%, transparent);
}
.song-row:active {
  background: color-mix(in srgb, var(--sp-ui-primary) 10%, transparent);
}
/* 当前播放行：主色浅底 + 标题主色 */
.song-row.is-playing {
  background: color-mix(in srgb, var(--sp-ui-primary) 8%, transparent);
}
.song-row.is-playing:hover {
  background: color-mix(in srgb, var(--sp-ui-primary) 12%, transparent);
}
.song-row.is-playing .song-title {
  color: var(--sp-ui-primary);
}

/* 频谱动效：播放中跳动，暂停定格为等高度 */
.eq {
  display: inline-flex;
  align-items: flex-end;
  gap: 2px;
  height: 14px;
}
.eq i {
  width: 3px;
  height: 5px;
  border-radius: 1px;
  background: var(--sp-ui-primary);
  animation: eq-bounce 0.9s ease-in-out infinite;
}
.eq i:nth-child(2) {
  animation-delay: 0.25s;
}
.eq i:nth-child(3) {
  animation-delay: 0.5s;
}
.eq.paused i {
  animation-play-state: paused;
}
@keyframes eq-bounce {
  0%,
  100% {
    height: 4px;
  }
  50% {
    height: 14px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .eq i {
    animation: none;
    height: 9px;
  }
}

.col-idx {
  text-align: center;
  font-variant-numeric: tabular-nums;
  font-size: var(--sp-fs-caption);
  color: var(--sp-ui-text-3);
  white-space: nowrap;
  line-height: 1;
}
.col-time {
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-size: var(--sp-fs-caption);
  color: var(--sp-ui-text-3);
  white-space: nowrap;
}
.col-format {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  min-width: 0;
  font-size: var(--sp-fs-caption);
  white-space: nowrap;
  overflow: hidden;
}
.col-size {
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-size: var(--sp-fs-caption);
  color: var(--sp-ui-text-3);
  white-space: nowrap;
}
.col-muted {
  color: var(--sp-ui-text-3);
}
.format-cell {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  cursor: default;
}
.format-name {
  color: var(--sp-ui-text-2);
  letter-spacing: 0.02em;
}
/* 多版本角标：提示「还有别的版本」，明细在 tooltip 与信息弹窗里。
   中性灰底，避免整列绿色徽标连成色带分散注意力 */
.format-more {
  font-size: var(--sp-fs-micro);
  line-height: 1;
  padding: 1px 3px;
  border-radius: var(--sp-radius-xs);
  color: var(--sp-ui-text-3);
  background: rgba(127, 127, 127, 0.14);
}
.version-tip {
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: var(--sp-fs-caption);
  line-height: 1.5;
  max-width: 280px;
}
.version-tip-row {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.col-actions {
  display: inline-flex;
  justify-content: flex-end;
  align-items: center;
  gap: 2px;
  white-space: nowrap;
}
/* 行内操作 hover 才浮现（喜欢已激活的常显），降低整列图标的视觉噪音；opacity 切换不占位变化 */
.col-actions .hover-only {
  opacity: 0;
  transition: opacity 0.12s ease;
}
.song-row:hover .hover-only,
.song-row:focus-within .hover-only,
.col-actions .hover-only.is-fav {
  opacity: 1;
}

.song-cell {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
}

/* 强制封面缩略图，不受原图像素尺寸影响 */
.mini-cover-wrap {
  width: 40px;
  height: 40px;
  min-width: 40px;
  min-height: 40px;
  max-width: 40px;
  max-height: 40px;
  flex: 0 0 40px;
  border-radius: var(--sp-radius-sm);
  overflow: hidden;
  background: rgba(127, 127, 127, 0.12);
  position: relative;
}
.mini-cover {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  max-width: 100%;
  max-height: 100%;
  object-fit: cover;
  object-position: center;
  display: block;
  border: 0;
}
.mini-cover.placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--sp-ui-text-3);
  font-size: var(--sp-fs-body);
}

.song-meta {
  min-width: 0;
  flex: 1 1 auto;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.song-title {
  font-weight: 600;
  font-size: var(--sp-fs-small);
  line-height: 1.35;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--sp-ui-text-1);
}
.song-sub {
  font-size: var(--sp-fs-caption);
  line-height: 1.3;
  color: var(--sp-ui-text-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.dot {
  margin: 0 4px;
  opacity: 0.55;
}

@media (max-width: 768px) {
  .search-input {
    width: 100%;
  }
  .pagination-bar {
    /* 移动端底部有 52px 固定 Tab 栏 + 安全区，吸附偏移必须让开 */
    bottom: calc(52px + env(safe-area-inset-bottom, 0px) + 8px);
    padding: 8px 10px;
    gap: 8px;
  }
  .song-table.above-player .pagination-bar {
    /* --gp-reserve 已内含 Tab 栏与安全区高度 */
    bottom: calc(var(--gp-reserve) + 4px);
  }
  .pagination-bar :deep(.n-text) {
    display: none;
  }
  .pagination-bar :deep(.n-pagination) {
    justify-content: center;
    width: 100%;
  }
  .song-list-head {
    display: none;
  }
  .song-row {
    grid-template-columns: minmax(0, 1fr) 44px auto;
    padding: 7px 4px;
  }
  .col-idx {
    display: none;
  }
  /* 移动端隐藏格式/大小列：网格只有 3 列，多出的单元格会换行；
     明细改由「信息」按钮的弹窗承载 */
  .col-format,
  .col-size {
    display: none;
  }
  .col-actions {
    gap: 6px;
  }
  /* 触屏无 hover，行内操作常显 */
  .col-actions .hover-only {
    opacity: 1;
  }
}
</style>
