<template>
  <div class="player-panel" :class="{ light: !isDark }" :style="panelStyle">
    <div class="ambient" aria-hidden="true"></div>
    <div class="noise" aria-hidden="true"></div>

    <div class="panel-top">
      <div class="view-switch" role="group" :aria-label="stageViewLabel">
        <n-tooltip v-for="option in stageViewOptions" :key="option.value">
          <template #trigger>
            <n-button
              class="view-toggle icon-top-btn"
              :class="{ active: player.stageView === option.value }"
              :type="player.stageView === option.value ? 'primary' : 'default'"
              :secondary="player.stageView === option.value"
              :quaternary="player.stageView !== option.value"
              circle
              size="small"
              :aria-label="option.label"
              @click="player.setStageView(option.value)"
            >
              <n-icon size="18"><component :is="option.icon" /></n-icon>
            </n-button>
          </template>
          {{ option.label }}
        </n-tooltip>
      </div>
      <div class="top-right">
        <div v-if="player.showLyrics" class="font-size-ctrl" @click.stop>
          <n-button quaternary size="tiny" class="font-btn" :disabled="player.lyricFontSize <= 14" @click="player.setLyricFontSize(player.lyricFontSize - 1)">A-</n-button>
          <span class="font-size-label">{{ player.lyricFontSize }}</span>
          <n-button quaternary size="tiny" class="font-btn" :disabled="player.lyricFontSize >= 28" @click="player.setLyricFontSize(player.lyricFontSize + 1)">A+</n-button>
        </div>
        <n-tooltip>
          <template #trigger>
            <n-button class="icon-top-btn" quaternary circle size="small" :disabled="!player.current" aria-label="标签" @click="openTagModal">
              <n-icon size="18"><pricetag-outline /></n-icon>
            </n-button>
          </template>
          标签
        </n-tooltip>
        <n-tooltip>
          <template #trigger>
            <n-button
              class="scrape-btn icon-top-btn"
              quaternary
              circle
              size="small"
              :disabled="!player.current || scraping"
              :loading="scraping"
              :aria-label="scraping ? (scrapeHint || '检索中') : '刮削'"
              @click="openScrapeModal"
            >
              <n-icon v-if="!scraping" size="18"><color-wand-outline /></n-icon>
            </n-button>
          </template>
          {{ scraping ? (scrapeHint || '检索中') : '刮削' }}
        </n-tooltip>
        <n-tooltip>
          <template #trigger>
            <n-button class="queue-btn icon-top-btn" quaternary circle size="small" :aria-label="queueLabel" @click="player.showQueue = !player.showQueue">
              <n-icon size="18"><list-outline /></n-icon>
              <span v-if="player.queue?.length" class="queue-count">{{ player.queue.length }}</span>
            </n-button>
          </template>
          {{ queueLabel }}
        </n-tooltip>
      </div>
    </div>

    <div class="stage-body">
      <!-- cover-only -->
      <div
        v-if="player.stageView === 'cover'"
        key="cover"
        class="cover-stage"
        @click="player.setStageView('blend')"
      >
        <div class="vinyl-frame">
          <div class="vinyl" :class="{ spinning: player.playing }">
            <div class="vinyl-ring"></div>
            <div class="vinyl-ring thin"></div>
            <img
              v-if="player.cover && !coverBroken"
              :src="player.cover"
              class="vinyl-cover"
              alt="cover"
              @error="coverBroken = true"
              @load="onCoverLoad"
            />
            <div v-else class="vinyl-cover placeholder">
              <n-icon size="42"><musical-notes /></n-icon>
            </div>
            <div class="vinyl-hole"></div>
          </div>
        </div>
        <div class="tap-hint">点击切换 · 歌词叠层</div>
      </div>

      <!-- blend: blurred vinyl under lyrics -->
      <div v-else-if="player.stageView === 'blend'" key="blend" class="blend-stage">
        <div class="blend-bg" aria-hidden="true">
          <div class="vinyl-frame dim">
            <div class="vinyl" :class="{ spinning: player.playing }">
              <div class="vinyl-ring"></div>
              <div class="vinyl-ring thin"></div>
              <img
                v-if="player.cover && !coverBroken"
                :src="player.cover"
                class="vinyl-cover"
                alt=""
                @error="coverBroken = true"
              />
              <div v-else class="vinyl-cover placeholder">
                <n-icon size="42"><musical-notes /></n-icon>
              </div>
              <div class="vinyl-hole"></div>
            </div>
          </div>
          <div class="blend-veil"></div>
        </div>
        <div class="blend-lyrics">
          <lyrics-view
            :lines="player.lyrics"
            :active-index="player.lyricIndex"
            :font-size="player.lyricFontSize"
            :immersive="true"
            @seek="onLyricSeek"
          />
        </div>
      </div>

      <!-- lyrics-only -->
      <div v-else key="lyrics" class="lyrics-stage">
        <lyrics-view
          :lines="player.lyrics"
          :active-index="player.lyricIndex"
          :font-size="player.lyricFontSize"
          :immersive="true"
          @seek="onLyricSeek"
        />
      </div>
    </div>

    <div class="meta-block">
      <div class="title-row">
        <div class="title" :title="player.current?.title || '未在播放'">
          {{ player.current?.title || '未在播放' }}
        </div>
        <n-button
          class="fav-btn"
          quaternary
          circle
          size="small"
          :type="player.current?.is_favorite ? 'error' : 'default'"
          :disabled="!player.current"
          @click="toggleFavorite"
        >
          <n-icon size="20">
            <heart v-if="player.current?.is_favorite" />
            <heart-outline v-else />
          </n-icon>
        </n-button>
      </div>
      <div class="artist" :title="player.current?.artist || '选择一首歌曲开始'">
        {{ player.current?.artist || '选择一首歌曲开始' }}
      </div>
      <div v-if="player.current?.album" class="album" :title="player.current.album">
        {{ player.current.album }}
      </div>
    </div>

    <div class="progress">
      <n-slider :value="progress" :step="0.1" :tooltip="false" @update:value="onSeekPercent" />
      <div class="time-row">
        <span>{{ formatTime(player.currentTime) }}</span>
        <span>{{ formatTime(player.duration) }}</span>
      </div>
    </div>

    <div class="controls">
      <n-tooltip>
        <template #trigger>
          <n-button quaternary circle class="ctrl" @click="player.toggleMode()">
            <n-icon size="20">
              <shuffle v-if="player.mode === 'shuffle'" />
              <repeat v-else-if="player.mode === 'loop'" />
              <reload v-else-if="player.mode === 'single'" />
              <list v-else />
            </n-icon>
          </n-button>
        </template>
        {{ player.modeLabel }}
      </n-tooltip>

      <n-button quaternary circle class="ctrl" @click="player.prev()">
        <n-icon size="26"><play-skip-back /></n-icon>
      </n-button>

      <n-button type="primary" circle class="play-btn" @click="player.togglePlay()">
        <n-icon size="28">
          <pause v-if="player.playing" />
          <play v-else />
        </n-icon>
      </n-button>

      <n-button quaternary circle class="ctrl" @click="player.next()">
        <n-icon size="26"><play-skip-forward /></n-icon>
      </n-button>

      <n-button quaternary circle class="ctrl" @click="player.showQueue = !player.showQueue">
        <n-icon size="20"><list-outline /></n-icon>
      </n-button>
    </div>

    <div class="volume-row">
      <n-button quaternary circle size="small" @click="player.toggleMute()">
        <n-icon size="18">
          <volume-mute v-if="player.muted || player.volume === 0" />
          <volume-high v-else />
        </n-icon>
      </n-button>
      <n-slider
        :value="player.muted ? 0 : player.volume * 100"
        :step="1"
        :tooltip="false"
        @update:value="(v) => player.setVolume(v / 100)"
      />
    </div>

    <n-modal v-model:show="tagModalVisible" preset="card" title="歌曲内置标签" style="width: 720px; max-width: 92vw">
      <n-spin :show="tagLoading">
        <div class="tag-grid">
          <div v-for="row in tagRows" :key="row.key" class="tag-row">
            <span class="tag-key">{{ row.label }}</span>
            <span class="tag-val">{{ row.value || '-' }}</span>
          </div>
        </div>
      </n-spin>
    </n-modal>

    <n-modal v-model:show="scrapeModalVisible" preset="card" title="刮削当前歌曲" style="width: 980px; max-width: 96vw">
      <n-space vertical size="medium">
        <n-radio-group v-model:value="scrapeMode" size="small">
          <n-radio-button value="auto">自动评分</n-radio-button>
          <n-radio-button value="manual">手动选择源</n-radio-button>
        </n-radio-group>
        <n-space align="center">
          <n-select v-if="scrapeMode === 'manual'" v-model:value="scrapeSource" :options="scrapeSourceOptions" style="width: 160px" />
          <n-button type="primary" size="small" :loading="scraping" @click="searchScrapeCandidates">检索候选</n-button>
          <n-text depth="3">{{ scrapeQueryText }}</n-text>
        </n-space>
        <n-data-table :columns="candidateColumns" :data="scrapeCandidates" :loading="scraping" :pagination="false" size="small" max-height="420" />
      </n-space>
    </n-modal>

  </div>
</template>

<script setup>
import { computed, h, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import {
  MusicalNotes,
  Heart,
  HeartOutline,
  Shuffle,
  Repeat,
  Reload,
  List,
  ListOutline,
  DiscOutline,
  LayersOutline,
  ReaderOutline,
  PricetagOutline,
  ColorWandOutline,
  PlaySkipBack,
  PlaySkipForward,
  Play,
  Pause,
  VolumeHigh,
  VolumeMute,
} from '@vicons/ionicons5'
import { addFavorite, removeFavorite, applyScrapeCandidate, fetchScrapeCandidates, fetchSongTags } from '@/api/music'
import { usePlayerStore } from '@/stores/player'
import { useThemeStore } from '@/stores/theme'
import { formatTime } from '@/utils/lrc'
import { ambientBackground, extractAccentFromImage } from '@/utils/color'
import LyricsView from '@/components/player/LyricsView.vue'

const player = usePlayerStore()
const themeStore = useThemeStore()
const message = useMessage()
const coverBroken = ref(false)
const accent = ref(null)
const scraping = ref(false)
const scrapeHint = ref('')
const tagModalVisible = ref(false)
const tagLoading = ref(false)
const tagData = ref(null)
const scrapeModalVisible = ref(false)
const scrapeMode = ref('auto')
const scrapeSource = ref('netease')
const scrapeCandidates = ref([])
const scrapeQuery = ref(null)
const scrapeSourceOptions = [
  { label: '网易云', value: 'netease' },
  { label: '咪咕', value: 'migu' },
  { label: 'QQ 音乐', value: 'qq' },
]

const isDark = computed(() => themeStore.isDark)
const stageViewLabel = computed(() => {
  const map = { cover: '封面', blend: '叠层', lyrics: '歌词' }
  return map[player.stageView] || '封面'
})
const stageViewOptions = [
  { value: 'cover', label: '封面', icon: DiscOutline },
  { value: 'blend', label: '叠层', icon: LayersOutline },
  { value: 'lyrics', label: '歌词', icon: ReaderOutline },
]
const queueLabel = computed(() => `队列 ${player.queue?.length || 0}`)

const tagRows = computed(() => {
  const db = tagData.value?.db || {}
  const em = tagData.value?.embedded || {}
  return [
    { key: 'db_title', label: 'DB 标题', value: db.title },
    { key: 'db_artist', label: 'DB 艺术家', value: db.artist },
    { key: 'db_album', label: 'DB 专辑', value: db.album },
    { key: 'db_duration', label: 'DB 时长', value: formatTime(db.duration || 0) },
    { key: 'db_cover', label: 'DB 封面', value: db.cover_path },
    { key: 'tag_title', label: '内嵌标题', value: em.title },
    { key: 'tag_artist', label: '内嵌艺术家', value: em.artist },
    { key: 'tag_album', label: '内嵌专辑', value: em.album },
    { key: 'tag_duration', label: '内嵌时长', value: formatTime(em.duration || 0) },
    { key: 'tag_cover', label: '内嵌封面', value: em.cover_embedded ? `有（${em.cover_size || 0} bytes）` : '无' },
    { key: 'tag_lyrics', label: '内嵌歌词', value: em.lyrics ? `${String(em.lyrics).slice(0, 120)}...` : '' },
    { key: 'path', label: '文件路径', value: tagData.value?.local_path },
  ]
})

const scrapeQueryText = computed(() => {
  const q = scrapeQuery.value
  if (!q) return ''
  return `查询：${q.keyword || ''} / 时长 ${q.duration ? formatTime(q.duration) : '-'}`
})

const candidateColumns = computed(() => [
  { title: '分', key: 'score', width: 64, render: (row) => Number(row.score || 0).toFixed(1) },
  { title: '源', key: 'source', width: 78 },
  { title: '标题', key: 'title', ellipsis: { tooltip: true } },
  { title: '艺术家', key: 'artist', ellipsis: { tooltip: true } },
  { title: '专辑', key: 'album', ellipsis: { tooltip: true } },
  { title: '时长', key: 'duration', width: 76, render: (row) => row.duration ? formatTime(row.duration) : '-' },
  { title: '封面', key: 'cover_url', width: 92, render: (row) => row.has_cover || row.cover_url ? (row.cover_source ? `有/${row.cover_source}` : '有') : '无' },
  { title: '操作', key: 'actions', width: 90, render: (row) => h('button', { class: 'mini-apply-btn', onClick: () => applyCandidate(row) }, '采用') },
])

const progress = computed(() => {
  if (!player.duration) return 0
  return (player.currentTime / player.duration) * 100
})

const panelStyle = computed(() => {
  const bg = ambientBackground(accent.value, { dark: isDark.value })
  const a = accent.value
  return {
    ...bg,
    '--accent': a ? a.css : 'rgb(24, 160, 88)',
    '--accent-soft': a ? a.soft : 'rgba(24, 160, 88, 0.35)',
    '--accent-glow': a ? a.glow : 'rgba(24, 160, 88, 0.45)',
  }
})

watch(
  () => player.cover,
  async (url) => {
    coverBroken.value = false
    accent.value = null
    if (!url) return
    accent.value = await extractAccentFromImage(url)
  },
  { immediate: true },
)

function onCoverLoad() {
  coverBroken.value = false
}

async function openTagModal() {
  if (!player.current?.id) return
  tagModalVisible.value = true
  tagLoading.value = true
  try {
    const res = await fetchSongTags(player.current.id)
    tagData.value = res.data || res || {}
  } catch (err) {
    message.error(err.response?.data?.detail || err.message || '读取标签失败')
  } finally {
    tagLoading.value = false
  }
}

function openScrapeModal() {
  if (!player.current?.id) return
  scrapeModalVisible.value = true
  scrapeCandidates.value = []
  scrapeQuery.value = null
}

async function searchScrapeCandidates() {
  if (!player.current?.id || scraping.value) return
  scraping.value = true
  scrapeHint.value = '检索中'
  try {
    const source = scrapeMode.value === 'auto' ? 'auto' : scrapeSource.value
    const res = await fetchScrapeCandidates(player.current.id, { source, limit: 12 })
    const data = res.data || res || {}
    scrapeQuery.value = data.query || null
    scrapeCandidates.value = data.candidates || []
    if (!scrapeCandidates.value.length) message.warning('没有检索到候选')
  } catch (err) {
    message.error(err.response?.data?.detail || err.message || '检索失败')
  } finally {
    scraping.value = false
    scrapeHint.value = ''
  }
}

async function applyCandidate(row) {
  if (!player.current?.id || !row) return
  scraping.value = true
  scrapeHint.value = '写入中'
  try {
    const res = await applyScrapeCandidate(player.current.id, row, { write_file_tags: true })
    const data = res.data || res || {}
    if (data.song) player.current = { ...player.current, ...data.song }
    await player.loadLyrics(player.current.id)
    try {
      const { coverUrl } = await import('@/api/music')
      const { useAuthStore } = await import('@/stores/auth')
      player.cover = coverUrl(player.current.id, useAuthStore().token || '') + `&_t=${Date.now()}`
    } catch (_) {}
    message.success(data.cover_result?.ok === false ? `已采用，但封面失败：${data.cover_result.error || '未知错误'}` : '已采用并写入')
    scrapeModalVisible.value = false
  } catch (err) {
    message.error(err.response?.data?.detail || err.message || '写入失败')
  } finally {
    scraping.value = false
    scrapeHint.value = ''
  }
}


async function toggleFavorite() {
  const song = player.current
  if (!song) return
  try {
    if (song.is_favorite) {
      await removeFavorite(song.id)
      song.is_favorite = false
      message.success('已取消喜欢')
    } else {
      await addFavorite(song.id)
      song.is_favorite = true
      message.success('已加入我喜欢的')
    }
  } catch (e) {
    message.error(e.response?.data?.detail || '操作失败')
  }
}
</script>

<style scoped>
.player-panel {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  width: 100%;
  box-sizing: border-box;
  color: rgba(255, 255, 255, 0.92);
  overflow: hidden;
  isolation: isolate;
  transition: background 0.45s ease, color 0.25s ease;
  --fg: rgba(255, 255, 255, 0.92);
  --fg-2: rgba(255, 255, 255, 0.72);
  --fg-3: rgba(255, 255, 255, 0.48);
  --fg-4: rgba(255, 255, 255, 0.36);
  --rail: rgba(255, 255, 255, 0.16);
  --rail-soft: rgba(255, 255, 255, 0.12);
  --handle: #fff;
  --play-bg: #fff;
  --play-fg: #111;
  --play-shadow: 0 12px 28px rgba(0, 0, 0, 0.28);
  --vinyl-shadow: drop-shadow(0 18px 40px rgba(0, 0, 0, 0.42));
  --vinyl-bg-a: #1a1a1a;
  --vinyl-bg-b: #0d0d0d;
  --cover-bg: #2a2a2a;
  --blend-veil: linear-gradient(
    90deg,
    rgba(8, 10, 14, 0.04) 0%,
    rgba(8, 10, 14, 0.10) 54%,
    rgba(8, 10, 14, 0.18) 100%
  );
}

.player-panel.light {
  color: rgba(18, 22, 30, 0.92);
  --fg: rgba(18, 22, 30, 0.92);
  --fg-2: rgba(18, 22, 30, 0.68);
  --fg-3: rgba(18, 22, 30, 0.48);
  --fg-4: rgba(18, 22, 30, 0.36);
  --rail: rgba(18, 22, 30, 0.14);
  --rail-soft: rgba(18, 22, 30, 0.10);
  --handle: #fff;
  --play-bg: var(--accent);
  --play-fg: #fff;
  --play-shadow: 0 12px 28px rgba(24, 160, 88, 0.28);
  --vinyl-shadow: drop-shadow(0 14px 28px rgba(20, 30, 50, 0.14));
  --vinyl-bg-a: #e8ecf2;
  --vinyl-bg-b: #d5dbe6;
  --cover-bg: #eef1f6;
  --blend-veil: linear-gradient(
    90deg,
    rgba(255, 255, 255, 0.04) 0%,
    rgba(248, 250, 253, 0.12) 56%,
    rgba(246, 248, 252, 0.24) 100%
  );
  border-left: 1px solid rgba(18, 22, 30, 0.06);
}

.ambient,
.noise {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;
}
.noise {
  opacity: 0.18;
  background-image:
    radial-gradient(circle at 20% 30%, rgba(255, 255, 255, 0.05) 0 1px, transparent 1.5px),
    radial-gradient(circle at 70% 60%, rgba(255, 255, 255, 0.04) 0 1px, transparent 1.5px),
    radial-gradient(circle at 40% 80%, rgba(255, 255, 255, 0.03) 0 1px, transparent 1.5px);
  background-size: 120px 120px, 180px 180px, 90px 90px;
  mix-blend-mode: soft-light;
}
.player-panel.light .noise {
  opacity: 0.08;
  mix-blend-mode: multiply;
  background-image:
    radial-gradient(circle at 20% 30%, rgba(18, 22, 30, 0.04) 0 1px, transparent 1.5px),
    radial-gradient(circle at 70% 60%, rgba(18, 22, 30, 0.03) 0 1px, transparent 1.5px);
}

.panel-top,
.stage-body,
.meta-block,
.progress,
.controls,
.volume-row {
  position: relative;
  z-index: 1;
}

.panel-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 14px 0;
  flex: 0 0 auto;
  gap: 8px;
}
.view-switch,
.top-right {
  display: flex;
  align-items: center;
  gap: 6px;
}
.view-switch {
  padding: 2px;
  border-radius: 999px;
  background: rgba(127, 127, 127, 0.10);
}
.view-toggle,
.queue-btn,
.font-btn,
.icon-top-btn {
  color: var(--fg-2) !important;
}
.view-toggle.active {
  color: var(--accent) !important;
  background: rgba(100, 108, 255, 0.16) !important;
  box-shadow: inset 0 0 0 1px rgba(100, 108, 255, 0.22);
}
.icon-top-btn {
  position: relative;
}
.queue-count {
  position: absolute;
  right: -2px;
  bottom: -1px;
  min-width: 14px;
  height: 14px;
  padding: 0 3px;
  border-radius: 999px;
  background: var(--accent);
  color: #fff;
  font-size: 9px;
  line-height: 14px;
  font-weight: 700;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.28);
  box-sizing: border-box;
}
.font-size-ctrl {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 0 4px;
  border-radius: 999px;
  background: rgba(127, 127, 127, 0.12);
}
.font-size-label {
  min-width: 22px;
  text-align: center;
  font-size: 12px;
  color: var(--fg-3);
  font-variant-numeric: tabular-nums;
}
.font-btn {
  font-weight: 700;
  letter-spacing: 0.02em;
}

.stage-body {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  position: relative;
}

/* ---------- vinyl geometry ---------- */
.cover-stage {
  flex: 1;
  min-height: 0;
  position: relative;
  overflow: hidden;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 8px 14px;
  box-sizing: border-box;
}
.vinyl-frame {
  width: min(92%, 360px);
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  filter: var(--vinyl-shadow);
}
@supports (width: 1cqh) {
  .stage-body {
    container-type: size;
  }
  .cover-stage .vinyl-frame {
    width: min(94cqw, 88cqh, 380px);
  }
  .blend-stage .vinyl-frame {
    width: min(78cqw, 72cqh, 420px);
  }
}
.vinyl {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  position: relative;
  background:
    radial-gradient(circle at 35% 30%, rgba(255, 255, 255, 0.08), transparent 40%),
    repeating-radial-gradient(circle at center, var(--vinyl-bg-a) 0 2px, var(--vinyl-bg-b) 2px 4px);
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.05),
    inset 0 0 40px rgba(0, 0, 0, 0.45);
}
.player-panel.light .vinyl {
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.7),
    inset 0 0 30px rgba(255, 255, 255, 0.35),
    0 1px 0 rgba(255, 255, 255, 0.6);
}
.vinyl.spinning {
  animation: spin 18s linear infinite;
}
.vinyl-ring {
  position: absolute;
  inset: 7%;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.05);
  box-shadow: inset 0 0 0 14px rgba(255, 255, 255, 0.015);
  pointer-events: none;
}
.player-panel.light .vinyl-ring {
  border-color: rgba(18, 22, 30, 0.05);
  box-shadow: inset 0 0 0 14px rgba(255, 255, 255, 0.25);
}
.vinyl-ring.thin {
  inset: 16%;
  border-color: rgba(255, 255, 255, 0.04);
  box-shadow: none;
}
.player-panel.light .vinyl-ring.thin {
  border-color: rgba(18, 22, 30, 0.05);
}
.vinyl-cover {
  position: absolute;
  inset: 16.666%;
  width: 66.666%;
  height: 66.666%;
  margin: auto;
  border-radius: 50%;
  object-fit: cover;
  background: var(--cover-bg);
  box-shadow:
    0 0 0 3px rgba(0, 0, 0, 0.38),
    0 12px 30px rgba(0, 0, 0, 0.34);
}
.player-panel.light .vinyl-cover {
  box-shadow:
    0 0 0 2px rgba(255, 255, 255, 0.85),
    0 8px 18px rgba(20, 30, 50, 0.12);
}
.vinyl-cover.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--fg-3);
  left: 16.666%;
  right: 16.666%;
  top: 16.666%;
  bottom: 16.666%;
  width: auto;
  height: auto;
}
.vinyl-hole {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 6.5%;
  height: 6.5%;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  background: radial-gradient(circle at 35% 35%, #3a3a3a, #0a0a0a 70%);
  box-shadow: 0 0 0 2px rgba(0, 0, 0, 0.5);
  z-index: 2;
}
.player-panel.light .vinyl-hole {
  background: radial-gradient(circle at 35% 35%, #cfd5df, #8b93a3 70%);
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.7);
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* ---------- blend stage ---------- */
.blend-stage {
  flex: 1;
  min-height: 0;
  position: relative;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.blend-bg {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  padding: clamp(4px, 2cqh, 16px) clamp(0px, 1.5cqw, 12px) 0 0;
  pointer-events: none;
  z-index: 0;
  box-sizing: border-box;
}
.blend-stage .vinyl-frame {
  filter: saturate(1.14) brightness(0.92);
  opacity: 0.88;
  transform: translateX(14%) scale(1.08);
}
.player-panel.light .blend-stage .vinyl-frame {
  filter: saturate(1.04) brightness(1.04);
  opacity: 0.58;
}
.blend-veil {
  position: absolute;
  inset: 0;
  background: var(--blend-veil);
}
.blend-lyrics {
  position: relative;
  z-index: 1;
  flex: 1;
  min-height: 0;
  width: min(68%, 520px);
  display: flex;
  flex-direction: column;
  padding: clamp(8px, 2.6cqh, 22px) 0 0 clamp(8px, 3.5cqw, 28px);
  box-sizing: border-box;
}
.blend-lyrics :deep(.lyrics) {
  flex: 1;
  min-height: 0;
  padding-left: 0;
  padding-right: clamp(10px, 2cqw, 22px);
  background: transparent;
  scrollbar-width: none;
  -ms-overflow-style: none;
}
.blend-lyrics :deep(.lyrics::-webkit-scrollbar) {
  display: none;
}
/* stronger text legibility over blurred vinyl */
.blend-lyrics :deep(.line) {
  text-shadow: 0 1px 10px rgba(0, 0, 0, 0.35);
}
.player-panel.light .blend-lyrics :deep(.line) {
  text-shadow: 0 1px 8px rgba(255, 255, 255, 0.65);
}
.blend-lyrics :deep(.line.active) {
  text-shadow: 0 0 18px rgba(255, 255, 255, 0.28), 0 2px 12px rgba(0, 0, 0, 0.35);
}
.player-panel.light .blend-lyrics :deep(.line.active) {
  text-shadow: 0 1px 10px rgba(255, 255, 255, 0.8);
}

.lyrics-stage {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 4px 0 0;
}
.lyrics-stage :deep(.lyrics) {
  flex: 1;
  min-height: 0;
}

.tap-hint {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 10px;
  text-align: center;
  font-size: 11px;
  color: var(--fg-4);
  letter-spacing: 0.02em;
  pointer-events: none;
}

.meta-block {
  flex: 0 0 auto;
  padding: 4px 22px 0;
  min-width: 0;
}
.title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.title {
  flex: 1;
  min-width: 0;
  font-size: 24px;
  font-weight: 750;
  line-height: 1.25;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  letter-spacing: 0.01em;
  color: var(--fg);
}
.fav-btn {
  color: var(--fg-2) !important;
  flex-shrink: 0;
}
.artist {
  margin-top: 8px;
  font-size: 14px;
  color: var(--fg-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.album {
  margin-top: 4px;
  font-size: 12px;
  color: var(--fg-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.progress {
  flex: 0 0 auto;
  padding: 14px 22px 0;
}
.progress :deep(.n-slider) {
  --n-rail-height: 3px;
  --n-rail-color: var(--rail);
  --n-rail-color-hover: var(--rail);
  --n-fill-color: var(--accent);
  --n-fill-color-hover: var(--accent);
  --n-handle-color: var(--handle);
  --n-handle-size: 12px;
}
.time-row {
  display: flex;
  justify-content: space-between;
  margin-top: 6px;
  font-size: 12px;
  color: var(--fg-3);
  font-variant-numeric: tabular-nums;
}

.controls {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 10px 12px 0;
}
.ctrl {
  color: var(--fg) !important;
}
.play-btn {
  width: 58px;
  height: 58px;
  background: var(--play-bg) !important;
  color: var(--play-fg) !important;
  box-shadow: var(--play-shadow);
  border: none !important;
}
.play-btn :deep(.n-icon) {
  color: var(--play-fg);
}

.volume-row {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 22px 16px;
}
.volume-row :deep(.n-button) {
  color: var(--fg-2) !important;
}
.volume-row :deep(.n-slider) {
  flex: 1;
  --n-rail-height: 3px;
  --n-rail-color: var(--rail-soft);
  --n-fill-color: rgba(255, 255, 255, 0.72);
  --n-fill-color-hover: #fff;
  --n-handle-color: var(--handle);
  --n-handle-size: 10px;
}
.player-panel.light .volume-row :deep(.n-slider) {
  --n-fill-color: var(--accent);
  --n-fill-color-hover: var(--accent);
}

@media (max-width: 1100px) {
  .title { font-size: 20px; }
  .cover-stage .vinyl-frame {
    width: min(92%, 320px);
  }
  .blend-lyrics {
    width: min(72%, 500px);
  }
}

@media (max-width: 720px) {
  .blend-bg {
    justify-content: center;
    opacity: 0.72;
  }
  .blend-stage .vinyl-frame {
    transform: translateX(18%) scale(1.02);
  }
  .blend-lyrics {
    width: 82%;
  }
}

.tag-grid { display: grid; gap: 8px; }
.tag-row { display: grid; grid-template-columns: 110px minmax(0, 1fr); gap: 10px; align-items: start; }
.tag-key { color: var(--fg-3); font-size: 12px; }
.tag-val { color: var(--fg); font-size: 12px; word-break: break-all; white-space: pre-wrap; }
:deep(.mini-apply-btn) { border: 1px solid rgba(24,160,88,.45); color: rgb(24,160,88); background: transparent; border-radius: 6px; padding: 2px 8px; cursor: pointer; }
:deep(.mini-apply-btn:hover) { background: rgba(24,160,88,.12); }

</style>
