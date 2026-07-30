<template>
  <div class="player-panel" :class="{ light: !isDark }" :style="panelStyle">
    <div class="ambient" aria-hidden="true"></div>
    <div class="noise" aria-hidden="true"></div>

    <div class="panel-top">
      <div class="top-left">
        <n-tooltip v-if="isMobile">
          <template #trigger>
            <n-button
              class="icon-top-btn"
              quaternary
              circle
              size="small"
              aria-label="收起播放器"
              @click="player.fullPlayerOpen = false"
            >
              <n-icon size="20"><chevron-down /></n-icon>
            </n-button>
          </template>
          收起
        </n-tooltip>
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
              :aria-label="scraping ? (scrapeHint || '检索中') : '刮削信息'"
              @click="openScrapeModal"
            >
              <n-icon v-if="!scraping" size="18"><color-wand-outline /></n-icon>
            </n-button>
          </template>
          {{ scraping ? (scrapeHint || '检索中') : '刮削信息' }}
        </n-tooltip>
        <n-tooltip>
          <template #trigger>
            <n-button
              class="icon-top-btn"
              quaternary
              circle
              size="small"
              :disabled="!player.current || lyricsLoading"
              :loading="lyricsLoading"
              :aria-label="lyricsLoading ? (lyricsHint || '检索歌词中') : '获取歌词'"
              @click="openLyricsModal"
            >
              <n-icon v-if="!lyricsLoading" size="18"><document-text-outline /></n-icon>
            </n-button>
          </template>
          {{ lyricsLoading ? (lyricsHint || '检索歌词中') : '获取歌词' }}
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
            :empty-title="player.lyricsMeta.instrumental ? '纯音乐' : '暂无歌词'"
            :empty-description="player.lyricsMeta.instrumental ? '该歌曲已标记为纯音乐' : '可点击上方获取歌词'"
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
          :empty-title="player.lyricsMeta.instrumental ? '纯音乐' : '暂无歌词'"
          :empty-description="player.lyricsMeta.instrumental ? '该歌曲已标记为纯音乐' : '可点击上方获取歌词'"
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
      <n-slider
        :value="progress"
        :step="0.1"
        :tooltip="false"
        :disabled="!player.duration"
        @update:value="onSeekPercent"
      />
      <div class="time-row">
        <span>{{ formatTime(player.currentTime) }}</span>
        <span>{{ formatTime(player.duration) }}</span>
      </div>
    </div>

    <div class="controls">
      <n-tooltip>
        <template #trigger>
          <n-button quaternary circle class="ctrl" :type="player.losslessPreferred ? 'primary' : 'default'" @click="player.toggleLosslessPreferred()">{{ player.losslessPreferred ? 'FLAC' : 'MP3' }}</n-button>
        </template>
        {{ player.losslessPreferred ? '无损优先：优先 FLAC' : 'MP3 优先：缺失时自动回退' }}
      </n-tooltip>
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

    <n-modal v-model:show="scrapeModalVisible" preset="card" title="刮削当前歌曲信息" style="width: 980px; max-width: 96vw">
      <n-space vertical size="medium">
        <section class="song-files-section">
          <div class="song-files-heading">
            <strong>歌曲文件</strong>
            <n-text depth="3">保存时会写入全部可用本地版本；WebDAV 版本仅展示。</n-text>
          </div>
          <div v-if="scrapeDisplayFiles.length" class="song-files-list">
            <div v-for="file in scrapeDisplayFiles" :key="file.id" class="song-file-item">
              <div class="song-file-summary">
                <n-tag size="small" :type="file.writable ? 'success' : 'default'">{{ file.displayFormat }}</n-tag>
                <strong>{{ file.displaySource }}</strong>
                <span>{{ file.displaySize }}</span>
                <n-tag size="small" :type="file.writable ? 'success' : 'warning'">{{ file.displayStatus }}</n-tag>
              </div>
              <div class="song-file-path" :title="file.displayPath">{{ file.displayPath }}</div>
            </div>
          </div>
          <n-empty v-else size="small" description="暂无歌曲文件记录" />
        </section>
        <n-form label-placement="top" size="small">
          <n-form-item label="检索关键词">
            <n-input v-model:value="scrapeKeyword" placeholder="可手动修改歌名、歌手后再检索" clearable />
          </n-form-item>
        </n-form>
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

    <n-modal v-model:show="lyricsModalVisible" preset="card" title="获取当前歌曲歌词" style="width: 1080px; max-width: 96vw">
      <n-space vertical size="medium">
        <n-alert v-if="lyricsStatusError" :type="lyricsStatusError.type" :show-icon="false">
          {{ lyricsStatusError.message }}
        </n-alert>
        <n-alert v-if="lyricsQuery && !lyricsQuery.complete_signature" type="warning" :show-icon="false">
          当前歌曲缺少专辑或时长，无法进行 LRCLIB 精确匹配，将自动使用宽松搜索，请重点核对版本和时长。
        </n-alert>
        <section class="song-files-section">
          <div class="song-files-heading">
            <strong>歌曲文件</strong>
            <n-text depth="3">歌词会写入全部可用本地版本；WebDAV 版本仅展示。</n-text>
          </div>
          <div v-if="lyricsDisplayFiles.length" class="song-files-list">
            <div v-for="file in lyricsDisplayFiles" :key="file.id" class="song-file-item">
              <div class="song-file-summary">
                <n-tag size="small" :type="file.writable ? 'success' : 'default'">{{ file.displayFormat }}</n-tag>
                <strong>{{ file.displaySource }}</strong>
                <span>{{ file.displaySize }}</span>
                <n-tag size="small" :type="file.writable ? 'success' : 'warning'">{{ file.displayStatus }}</n-tag>
              </div>
              <div class="song-file-path" :title="file.displayPath">{{ file.displayPath }}</div>
            </div>
          </div>
          <n-empty v-else size="small" description="暂无歌曲文件记录" />
        </section>
        <n-form label-placement="top" size="small">
          <n-grid cols="1 m:2" responsive="screen" :x-gap="12">
            <n-gi><n-form-item label="目标歌曲"><n-input :value="lyricsTargetLabel" readonly /></n-form-item></n-gi>
            <n-gi><n-form-item label="检索关键词"><n-input v-model:value="lyricsKeyword" placeholder="歌曲名、艺术家或专辑" clearable /></n-form-item></n-gi>
          </n-grid>
        </n-form>
        <n-space align="center" wrap>
          <n-radio-group v-model:value="lyricsMode" size="small">
            <n-radio-button value="auto">自动选择歌词源</n-radio-button>
            <n-radio-button value="manual">指定歌词源</n-radio-button>
          </n-radio-group>
          <n-select v-if="lyricsMode === 'manual'" v-model:value="lyricsSource" :options="lyricsSourceOptions" style="width: 180px" />
          <n-button type="primary" :loading="lyricsLoading" @click="searchLyrics">检索歌词</n-button>
          <n-text depth="3">{{ lyricsHint || lyricsQueryText }}</n-text>
        </n-space>
        <div class="lyrics-workbench">
          <n-data-table
            class="lyrics-candidates"
            :columns="lyricsCandidateColumns"
            :data="lyricsCandidates"
            :loading="lyricsLoading"
            :pagination="false"
            size="small"
            max-height="440"
            :row-props="lyricsRowProps"
          />
          <div class="lyrics-preview lyrics-compare">
            <section class="lyrics-compare-pane">
              <div class="lyrics-preview-header">
                <strong>当前歌词</strong>
                <n-space size="small">
                  <n-tag v-if="lyricsCurrent.source" size="small">{{ lyricsSourceLabel(lyricsCurrent.source) }}</n-tag>
                  <n-tag v-if="lyricsCurrent.lyrics_type" size="small">{{ lyricsTypeLabel(lyricsCurrent) }}</n-tag>
                </n-space>
              </div>
              <n-text v-if="lyricsCurrent.fetched_at" depth="3" class="lyrics-fetched-at">获取于 {{ formatFetchedAt(lyricsCurrent.fetched_at) }}</n-text>
              <pre class="lyrics-preview-text">{{ lyricsCurrentText }}</pre>
            </section>
            <section class="lyrics-compare-pane">
              <div class="lyrics-preview-header">
                <strong>候选歌词</strong>
                <n-space v-if="lyricsPreviewCandidate" size="small">
                  <n-tag size="small" type="info">{{ lyricsSourceLabel(lyricsPreviewCandidate.source) }}</n-tag>
                  <n-tag size="small" :type="lyricsPreviewCandidate.lyrics_type === 'synced' ? 'success' : 'default'">{{ lyricsTypeLabel(lyricsPreviewCandidate) }}</n-tag>
                </n-space>
              </div>
              <n-alert v-if="lyricsPreviewCandidate && (lyricsCurrent.has_lyrics || lyricsCurrent.instrumental)" type="warning" :show-icon="false" size="small">保存后将覆盖当前歌词，请核对版本与时长。</n-alert>
              <pre class="lyrics-preview-text">{{ lyricsCandidateText }}</pre>
            </section>
          </div>
        </div>
        <n-space justify="space-between" align="center" wrap class="lyrics-actions">
          <n-space align="center" wrap>
            <n-checkbox v-model:checked="lyricsWriteFileTags">同时写入音频内嵌歌词</n-checkbox>
            <n-button
              type="error"
              secondary
              :disabled="!lyricsCurrent.has_lyrics && !lyricsCurrent.instrumental"
              @click="confirmClearLyrics"
            >清空当前歌词</n-button>
          </n-space>
          <n-space>
            <n-button @click="lyricsModalVisible = false">取消</n-button>
            <n-button type="primary" :disabled="!lyricsPreviewCandidate" :loading="lyricsLoading" @click="applyLyrics">保存所选歌词</n-button>
          </n-space>
        </n-space>
      </n-space>
    </n-modal>

    <n-modal v-model:show="scrapeApplyModalVisible" preset="card" title="选择要应用的更改" style="width: 920px; max-width: 96vw">
      <n-space vertical size="medium">
        <n-alert type="info" :show-icon="false">
          普通字段在新值非空且有变化时默认开启；封面仅在当前无封面且候选有封面时默认开启。提交后只修改已开启的项目。
        </n-alert>
        <div class="scrape-compare-list">
          <div v-for="field in scrapeApplyRows" :key="field.key" class="scrape-compare-row">
            <div class="scrape-field-heading">
              <strong>{{ field.label }}</strong>
              <n-tag v-if="field.empty" size="small" type="warning">新值为空</n-tag>
              <n-tag v-else-if="field.changed" size="small" type="success">有变化</n-tag>
              <n-tag v-else size="small">一致</n-tag>
            </div>
            <div class="scrape-value-block" :class="{ 'scrape-cover-block': field.key === 'cover' }">
              <span class="scrape-value-label">当前</span>
              <template v-if="field.key === 'cover'">
                <div class="scrape-cover-preview">
                  <img
                    v-if="scrapeCoverAvailable('current')"
                    :src="scrapeCoverImageUrl('current')"
                    alt="当前封面"
                    @load="onScrapeCoverLoad('current', $event)"
                    @error="onScrapeCoverError('current')"
                  >
                  <div v-else class="scrape-cover-placeholder">无封面</div>
                  <span>{{ scrapeCoverMeta('current') }}</span>
                </div>
              </template>
              <div v-else class="scrape-value-text">{{ scrapeValuePreview(field.currentValue, field) }}</div>
            </div>
            <div class="scrape-value-block" :class="{ 'scrape-cover-block': field.key === 'cover' }">
              <span class="scrape-value-label">新值</span>
              <template v-if="field.key === 'cover'">
                <div class="scrape-cover-preview">
                  <img
                    v-if="scrapeCoverAvailable('candidate')"
                    :src="scrapeCoverImageUrl('candidate')"
                    alt="候选封面"
                    @load="onScrapeCoverLoad('candidate', $event)"
                    @error="onScrapeCoverError('candidate')"
                  >
                  <div v-else class="scrape-cover-placeholder">无封面</div>
                  <span>{{ scrapeCoverMeta('candidate') }}</span>
                </div>
              </template>
              <template v-else>
                <n-input
                  v-if="scrapeFieldSelected(field.key)"
                  v-model:value="scrapeApplyOverrides[field.key]"
                  :placeholder="scrapeValuePreview(field.rawNewValue, field)"
                  size="small"
                  type="textarea"
                  :autosize="{ minRows: 1, maxRows: 4 }"
                />
                <div v-else class="scrape-value-text" :class="{ empty: field.empty }">
                  {{ scrapeValuePreview(field.newValue, field) }}
                </div>
              </template>
            </div>
            <n-switch
              :value="scrapeFieldSelected(field.key)"
              @update:value="(enabled) => setScrapeFieldSelected(field.key, enabled)"
            />
          </div>
        </div>
        <n-space justify="end">
          <n-button @click="scrapeApplyModalVisible = false">取消</n-button>
          <n-button type="primary" :loading="scraping" @click="applyCandidate">应用所选更改</n-button>
        </n-space>
      </n-space>
    </n-modal>

  </div>
</template>

<script setup>
import { computed, h, onMounted, ref, watch } from 'vue'
import { NTag, useDialog, useMessage } from 'naive-ui'
import {
  MusicalNotes,
  Heart,
  HeartOutline,
  ChevronDown,
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
  DocumentTextOutline,
  PlaySkipBack,
  PlaySkipForward,
  Play,
  Pause,
  VolumeHigh,
  VolumeMute,
} from '@vicons/ionicons5'
import {
  addFavorite,
  removeFavorite,
  applyLyricsCandidate,
  clearLyrics,
  applyScrapeCandidate,
  fetchLyricsCandidateDetails,
  fetchScrapeCandidateDetails,
  fetchScrapeCandidates,
  fetchSongTags,
  searchLyricsCandidates,
  coverUrl,
} from '@/api/music'
import api from '@/api/client'
import { usePlayerStore } from '@/stores/player'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import { useIsMobile } from '@/composables/useIsMobile'
import { formatTime } from '@/utils/lrc'
import { ambientBackground, extractAccentFromImage } from '@/utils/color'
import { normalizeSongFiles, normalizedScrapeValue, shouldSelectScrapeField } from '@/utils/scrapeApply'
import LyricsView from '@/components/player/LyricsView.vue'

const player = usePlayerStore()
const themeStore = useThemeStore()
const message = useMessage()
const dialog = useDialog()
const isMobile = useIsMobile()
const coverBroken = ref(false)
const accent = ref(null)
const scraping = ref(false)
const scrapeHint = ref('')
const tagModalVisible = ref(false)
const tagLoading = ref(false)
const tagData = ref(null)
const scrapeModalVisible = ref(false)
const scrapeTargetSong = ref(null)
const scrapeMode = ref('auto')
const scrapeSource = ref('netease')
const scrapeKeyword = ref('')
const scrapeCandidates = ref([])
const scrapeQuery = ref(null)
const scrapeCurrentValues = ref({})
const scrapeSongFiles = ref([])
const scrapeApplyModalVisible = ref(false)
const scrapeApplyCandidate = ref(null)
const scrapeApplyFields = ref([])
const scrapeApplyOverrides = ref({})
const scrapeCurrentCoverUrl = ref('')
const scrapeCoverInfo = ref({ current: null, candidate: null })
const scrapeSourceOptions = ref([])
const lyricsLoading = ref(false)
const lyricsHint = ref('')
const lyricsModalVisible = ref(false)
const lyricsTargetSong = ref(null)
const lyricsMode = ref('auto')
const lyricsSource = ref('lrclib')
const lyricsKeyword = ref('')
const lyricsSourceOptions = ref([])
const lyricsQuery = ref(null)
const lyricsCurrent = ref({})
const lyricsSongFiles = ref([])
const lyricsStatusError = ref(null)
const lyricsCandidates = ref([])
const lyricsSelectedCandidate = ref(null)
const lyricsPreviewCandidate = ref(null)
const lyricsWriteFileTags = ref(true)
let lyricsModalSession = 0

const SCRAPE_FIELD_DEFINITIONS = [
  { key: 'title', label: '标题' },
  { key: 'artist', label: '艺术家' },
  { key: 'album', label: '专辑' },
  { key: 'year', label: '年份' },
  { key: 'cover', label: '封面' },
  { key: 'genre', label: '风格' },
]

function normalizedCompareValue(value) {
  return normalizedScrapeValue(value)
}

function candidateFieldValue(candidate, key) {
  if (key === 'cover') return candidate?.cover_url || ''
  return candidate?.[key] ?? ''
}

function formatFileSize(bytes) {
  const value = Number(bytes)
  if (!Number.isFinite(value) || value < 0) return '大小未知'
  if (value < 1024) return `${value} B`
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 ** 2).toFixed(2)} MB`
}

function scrapeCoverImageUrl(kind) {
  if (kind === 'candidate') return candidateFieldValue(scrapeApplyCandidate.value, 'cover')
  return scrapeCurrentCoverUrl.value
}

function scrapeCoverMeta(kind) {
  const info = scrapeCoverInfo.value[kind]
  const dimensions = info?.width && info?.height ? `${info.width} × ${info.height}` : '尺寸未知'
  if (kind === 'current') return `${dimensions} · ${formatFileSize(scrapeCurrentValues.value?.cover_size)}`
  return dimensions
}

function onScrapeCoverLoad(kind, event) {
  const image = event.target
  scrapeCoverInfo.value = {
    ...scrapeCoverInfo.value,
    [kind]: { width: image.naturalWidth, height: image.naturalHeight, failed: false },
  }
}

function onScrapeCoverError(kind) {
  scrapeCoverInfo.value = {
    ...scrapeCoverInfo.value,
    [kind]: { failed: true },
  }
}

function scrapeCoverAvailable(kind) {
  if (scrapeCoverInfo.value[kind]?.failed) return false
  return Boolean(scrapeCoverImageUrl(kind))
}

function resetScrapeApplyOverrides(candidate) {
  const overrides = {}
  for (const field of SCRAPE_FIELD_DEFINITIONS) {
    if (field.key === 'cover') continue
    overrides[field.key] = candidateFieldValue(candidate, field.key)
  }
  scrapeApplyOverrides.value = overrides
}

const scrapeApplyRows = computed(() => SCRAPE_FIELD_DEFINITIONS.map((field) => {
  const currentValue = scrapeCurrentValues.value?.[field.key] ?? ''
  const rawNewValue = candidateFieldValue(scrapeApplyCandidate.value, field.key)
  const overrideValue = scrapeApplyOverrides.value[field.key]
  const newValue = field.key === 'cover' ? rawNewValue : (overrideValue !== undefined ? overrideValue : rawNewValue)
  return {
    ...field,
    currentValue,
    newValue,
    rawNewValue,
    empty: normalizedCompareValue(newValue) === '',
    changed: normalizedCompareValue(currentValue) !== normalizedCompareValue(newValue),
  }
}))

function scrapeFieldSelected(key) {
  return scrapeApplyFields.value.includes(key)
}

function setScrapeFieldSelected(key, enabled) {
  const selected = new Set(scrapeApplyFields.value)
  if (enabled) selected.add(key)
  else selected.delete(key)
  scrapeApplyFields.value = [...selected]
}

function scrapeValuePreview(value, field) {
  if (field.key === 'cover') return value ? '有封面' : '无封面'
  if (value == null || String(value).trim() === '') return '空'
  const text = String(value)
  if (field.multiline && text.length > 180) return `${text.slice(0, 180)}…`
  return text
}

const scrapeDisplayFiles = computed(() => normalizeSongFiles(scrapeSongFiles.value))
const lyricsDisplayFiles = computed(() => normalizeSongFiles(lyricsSongFiles.value))

const lyricsTargetLabel = computed(() => {
  const song = lyricsTargetSong.value || {}
  return `${song.artist || ''} - ${song.title || ''}`.replace(/^\s*-\s*|\s*-\s*$/g, '')
})

const lyricsQueryText = computed(() => {
  const query = lyricsQuery.value
  if (!query) return ''
  const duration = query.duration ? formatTime(query.duration) : '未知时长'
  return `${query.artist_name || '未知艺术家'} · ${query.album_name || '未知专辑'} · ${duration}`
})

const lyricsCurrentText = computed(() => {
  if (lyricsCurrent.value?.instrumental) return '该歌曲已标记为纯音乐。'
  return lyricsCurrent.value?.text || '当前歌曲暂无歌词。'
})

const lyricsCandidateText = computed(() => {
  const candidate = lyricsPreviewCandidate.value
  if (!candidate) return '请从左侧选择一个歌词候选。'
  if (candidate.instrumental) return '该候选标记为纯音乐。'
  return candidate.synced_lyrics || candidate.plain_lyrics || '该候选暂无歌词正文。'
})

function formatFetchedAt(value) {
  if (!value) return ''
  try { return new Date(value).toLocaleString('zh-CN') } catch { return value }
}

function lyricsSourceLabel(source) {
  return lyricsSourceOptions.value.find(item => item.value === source)?.label || source || '未知来源'
}

function lyricsTypeLabel(candidate) {
  if (candidate?.instrumental) return '纯音乐'
  if (candidate?.synced_lyrics || candidate?.lyrics_type === 'synced') return '同步歌词'
  return candidate?.plain_lyrics || candidate?.lyrics_type === 'plain' ? '纯文本' : '空歌词'
}

function lyricsScoreType(score) {
  const value = Number(score || 0)
  if (value >= 90) return 'success'
  if (value >= 70) return 'info'
  return 'warning'
}

const lyricsCandidateColumns = computed(() => [
  { title: '匹配', key: 'score', width: 72, render: row => h(NTag, { size: 'small', type: lyricsScoreType(row.score) }, { default: () => Number(row.score || 0).toFixed(0) }) },
  { title: '来源', key: 'source', width: 90, render: row => lyricsSourceLabel(row.source) },
  { title: '标题', key: 'track_name', ellipsis: { tooltip: true } },
  { title: '艺术家', key: 'artist_name', ellipsis: { tooltip: true } },
  { title: '专辑', key: 'album_name', ellipsis: { tooltip: true } },
  { title: '时长差', key: 'duration_delta', width: 76, render: row => row.match_detail?.duration_delta == null ? '-' : `${row.match_detail.duration_delta}s` },
  { title: '类型', key: 'lyrics_type', width: 92, render: row => lyricsTypeLabel(row) },
])

function lyricsRowProps(row) {
  return {
    class: lyricsSelectedCandidate.value?.source === row.source && lyricsSelectedCandidate.value?.source_id === row.source_id ? 'lyrics-row-selected' : '',
    onClick: () => selectLyricsCandidate(row),
  }
}

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
    { key: 'db_year', label: 'DB 年份', value: db.year },
    { key: 'db_genre', label: 'DB 风格', value: db.genre },
    { key: 'db_duration', label: 'DB 时长', value: formatTime(db.duration || 0) },
    { key: 'db_cover', label: 'DB 封面', value: db.cover_path },
    { key: 'tag_title', label: '内嵌标题', value: em.title },
    { key: 'tag_artist', label: '内嵌艺术家', value: em.artist },
    { key: 'tag_album', label: '内嵌专辑', value: em.album },
    { key: 'tag_year', label: '内嵌年份', value: em.year },
    { key: 'tag_genre', label: '内嵌风格', value: em.genre },
    { key: 'tag_duration', label: '内嵌时长', value: formatTime(em.duration || 0) },
    { key: 'tag_cover', label: '内嵌封面', value: em.cover_embedded ? `有（${em.cover_size || 0} bytes）` : '无' },
    { key: 'tag_lyrics', label: '内嵌歌词', value: em.lyrics ? `${String(em.lyrics).slice(0, 120)}...` : '' },
    { key: 'file_version', label: '文件版本', value: tagData.value?.file_version_id ? `#${tagData.value.file_version_id}` : '无可用本地版本' },
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
  { title: '操作', key: 'actions', width: 90, render: (row) => h('button', { class: 'mini-apply-btn', onClick: () => openApplyCandidate(row) }, '采用') },
])

const progress = computed(() => {
  if (!player.duration) return 0
  return (player.currentTime / player.duration) * 100
})

function requestSeek(time) {
  const target = Number(time)
  if (!Number.isFinite(target) || target < 0) return
  window.dispatchEvent(new CustomEvent('sonpick-seek', { detail: target }))
}

function onSeekPercent(value) {
  const duration = Number(player.duration)
  const percent = Math.min(100, Math.max(0, Number(value) || 0))
  if (!Number.isFinite(duration) || duration <= 0) return
  requestSeek((percent / 100) * duration)
}

function onLyricSeek(time) {
  requestSeek(time)
}

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

async function loadSourceOptions() {
  try {
    const { data } = await api.get('/settings')
    scrapeSourceOptions.value = (data.scrape_sources || [])
      .filter(source => source.enabled && source.id !== 'acoustid')
      .map(source => ({ label: source.name, value: source.id }))
    lyricsSourceOptions.value = (data.lyrics_sources || [])
      .filter(source => source.enabled)
      .map(source => ({ label: source.name, value: source.id }))
    if (!scrapeSourceOptions.value.some(option => option.value === scrapeSource.value)) {
      scrapeSource.value = scrapeSourceOptions.value[0]?.value || ''
    }
    if (!lyricsSourceOptions.value.some(option => option.value === lyricsSource.value)) {
      lyricsSource.value = lyricsSourceOptions.value[0]?.value || ''
    }
  } catch (_) {
    scrapeSourceOptions.value = []
    lyricsSourceOptions.value = []
  }
}

onMounted(loadSourceOptions)

function onCoverLoad() {
  coverBroken.value = false
}

async function openLyricsModal() {
  const session = ++lyricsModalSession
  const song = player.current
  if (!song?.id) return
  lyricsTargetSong.value = { ...song }
  lyricsKeyword.value = `${song.title || ''} ${song.artist || ''}`.trim()
  lyricsQuery.value = null
  lyricsCurrent.value = {}
  lyricsSongFiles.value = song.versions || []
  lyricsStatusError.value = null
  lyricsCandidates.value = []
  lyricsSelectedCandidate.value = null
  lyricsPreviewCandidate.value = null
  lyricsModalVisible.value = true
  await searchLyrics(session)
}

async function searchLyrics(session = lyricsModalSession) {
  const targetSongId = lyricsTargetSong.value?.id
  if (!targetSongId || lyricsLoading.value) return
  lyricsLoading.value = true
  lyricsStatusError.value = null
  lyricsHint.value = lyricsMode.value === 'auto' ? '正在精确匹配，未命中时自动宽松搜索' : '正在检索指定歌词源'
  try {
    const source = lyricsMode.value === 'auto' ? 'auto' : (lyricsSourceOptions.value.some(option => option.value === lyricsSource.value) ? lyricsSource.value : 'auto')
    const res = await searchLyricsCandidates(targetSongId, { source, keyword: lyricsKeyword.value.trim(), limit: 20 })
    const data = res.data || res || {}
    if (session !== lyricsModalSession || lyricsTargetSong.value?.id !== targetSongId) return
    lyricsQuery.value = data.query || null
    lyricsCurrent.value = data.current || {}
    lyricsSongFiles.value = data.song_files || []
    lyricsCandidates.value = data.candidates || []
    lyricsSelectedCandidate.value = null
    lyricsPreviewCandidate.value = null
    if (!lyricsCandidates.value.length) {
      const sourceErrors = data.errors || []
      const errors = sourceErrors.map(item => `${lyricsSourceLabel(item.source)}：${item.message}`).join('；')
      const rateLimit = sourceErrors.find(item => item.code === 'rate_limited')
      lyricsStatusError.value = {
        type: rateLimit ? 'warning' : (errors ? 'error' : 'info'),
        message: rateLimit ? `触发来源限流，等待 ${rateLimit.retry_after || 0} 秒后可重试` : (errors || '没有检索到歌词候选'),
      }
    }
  } catch (err) {
    const detail = err.response?.data?.detail
    lyricsStatusError.value = { type: detail?.code === 'rate_limited' ? 'warning' : 'error', message: detail?.message || detail || err.message || '歌词检索失败' }
  } finally {
    lyricsLoading.value = false
    lyricsHint.value = ''
  }
}

async function selectLyricsCandidate(row) {
  const targetSongId = lyricsTargetSong.value?.id
  if (!targetSongId || !row || lyricsLoading.value) return
  const session = lyricsModalSession
  lyricsSelectedCandidate.value = row
  lyricsLoading.value = true
  lyricsStatusError.value = null
  lyricsHint.value = '正在加载歌词详情'
  try {
    const res = await fetchLyricsCandidateDetails(targetSongId, row)
    if (session !== lyricsModalSession || lyricsTargetSong.value?.id !== targetSongId) return
    const data = res.data || res || {}
    lyricsPreviewCandidate.value = data.candidate || row
    lyricsSongFiles.value = data.song_files || lyricsSongFiles.value
  } catch (err) {
    message.error(err.response?.data?.detail || err.message || '歌词详情加载失败')
  } finally {
    lyricsLoading.value = false
    lyricsHint.value = ''
  }
}

async function clearTargetLyrics(targetSongId) {
  if (!targetSongId || lyricsLoading.value) return
  lyricsLoading.value = true
  lyricsHint.value = '正在清空歌词'
  try {
    const res = await clearLyrics(targetSongId, { clear_file_tags: true })
    const data = res.data || res || {}
    lyricsCurrent.value = {}
    lyricsPreviewCandidate.value = null
    if (player.current?.id === targetSongId) await player.loadLyrics(targetSongId)
    const written = (data.versions || []).filter(item => item.status === 'written').length
    const failed = (data.versions || []).filter(item => item.status === 'failed').length
    const unsupported = (data.versions || []).filter(item => item.status === 'unsupported').length
    if (failed) message.warning(`已清空 ${written} 个本地版本，${failed} 个版本失败`)
    else if (unsupported) message.success(`已清空侧车歌词；${unsupported} 个版本不支持内嵌，已跳过标签`)
    else message.success(`已清空 ${written} 个本地版本的歌词`)
  } catch (err) {
    const detail = err.response?.data?.detail
    message.error(detail?.message || detail || err.message || '清空歌词失败')
  } finally {
    lyricsLoading.value = false
    lyricsHint.value = ''
  }
}

function confirmClearLyrics() {
  const target = lyricsTargetSong.value ? { ...lyricsTargetSong.value } : null
  if (!target?.id) return
  dialog.warning({
    title: '清空歌词',
    content: `确定清空「${lyricsTargetLabel.value}」的侧车歌词和内嵌歌词吗？此操作不可恢复。`,
    positiveText: '确认清空',
    negativeText: '取消',
    onPositiveClick: () => clearTargetLyrics(target.id),
  })
}

async function applyLyrics() {
  const targetSongId = lyricsTargetSong.value?.id
  const candidate = lyricsPreviewCandidate.value
  if (!targetSongId || !candidate || lyricsLoading.value) return
  const hasContent = candidate.instrumental || candidate.synced_lyrics || candidate.plain_lyrics
  if (!hasContent) {
    message.warning('空歌词不会覆盖当前歌词')
    return
  }
  lyricsLoading.value = true
  lyricsHint.value = lyricsWriteFileTags.value ? '正在写入歌词侧车和音频标签' : '正在写入歌词侧车'
  try {
    const res = await applyLyricsCandidate(targetSongId, candidate, { write_file_tags: lyricsWriteFileTags.value })
    const data = res.data || res || {}
    if (player.current?.id === targetSongId) await player.loadLyrics(targetSongId)
    const written = (data.versions || []).filter(item => item.status === 'written').length
    const failed = (data.versions || []).filter(item => item.status === 'failed').length
    const unsupported = (data.versions || []).filter(item => item.status === 'unsupported').length
    if (failed) message.warning(`歌词已写入 ${written} 个本地版本，${failed} 个版本失败`)
    else if (unsupported) {
      message.success(
        candidate.instrumental
          ? `已标记纯音乐（侧车）；${unsupported} 个版本不支持内嵌`
          : `歌词已保存到侧车；${unsupported} 个版本不支持内嵌标签`,
      )
    } else {
      message.success(candidate.instrumental ? `已在 ${written} 个本地版本标记为纯音乐` : `歌词已保存到 ${written} 个本地版本`)
    }
    lyricsModalVisible.value = false
  } catch (err) {
    message.error(err.response?.data?.detail || err.message || '歌词写入失败')
  } finally {
    lyricsLoading.value = false
    lyricsHint.value = ''
  }
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
  const song = player.current
  if (!song?.id) return
  scrapeTargetSong.value = { ...song }
  scrapeModalVisible.value = true
  scrapeCandidates.value = []
  scrapeSongFiles.value = normalizeSongFiles(song.versions || []).map((item) => ({ ...item }))
  scrapeQuery.value = null
  scrapeKeyword.value = `${song.title || song.song_name || ''} ${song.artist || song.singers || ''}`.trim()
}

async function searchScrapeCandidates() {
  const targetSongId = scrapeTargetSong.value?.id
  if (!targetSongId || scraping.value) return
  if (!scrapeKeyword.value.trim()) {
    message.warning('请输入检索关键词')
    return
  }
  scraping.value = true
  scrapeHint.value = '检索中'
  try {
    const source = scrapeMode.value === 'auto' ? 'auto' : scrapeSource.value
    const res = await fetchScrapeCandidates(targetSongId, { source, keyword: scrapeKeyword.value.trim(), limit: 12 })
    const data = res.data || res || {}
    scrapeQuery.value = data.query || null
    scrapeCurrentValues.value = data.current || {}
    scrapeSongFiles.value = data.song_files || []
    scrapeCandidates.value = data.candidates || []
    if (!scrapeCandidates.value.length) message.warning('没有检索到候选')
  } catch (err) {
    message.error(err.response?.data?.detail || err.message || '检索失败')
  } finally {
    scraping.value = false
    scrapeHint.value = ''
  }
}

async function openApplyCandidate(row) {
  const targetSongId = scrapeTargetSong.value?.id
  if (!targetSongId || !row || scraping.value) return
  scraping.value = true
  scrapeHint.value = '加载详情'
  try {
    const res = await fetchScrapeCandidateDetails(targetSongId, row)
    const data = res.data || res || {}
    scrapeCurrentValues.value = data.current || scrapeCurrentValues.value || {}
    scrapeSongFiles.value = data.song_files || scrapeSongFiles.value
    scrapeApplyCandidate.value = data.candidate || row
    resetScrapeApplyOverrides(scrapeApplyCandidate.value)
    scrapeCoverInfo.value = { current: null, candidate: null }
    scrapeCurrentCoverUrl.value = scrapeCurrentValues.value?.cover_exists
      ? coverUrl(targetSongId, useAuthStore().token || '') + `&_t=${Date.now()}`
      : ''
    scrapeApplyFields.value = SCRAPE_FIELD_DEFINITIONS
      .filter((field) => shouldSelectScrapeField({
        key: field.key,
        newValue: candidateFieldValue(scrapeApplyCandidate.value, field.key),
        currentValue: scrapeCurrentValues.value?.[field.key],
        currentCoverExists: Boolean(scrapeCurrentValues.value?.cover_exists),
      }))
      .map((field) => field.key)
    scrapeApplyModalVisible.value = true
  } catch (err) {
    message.error(err.response?.data?.detail || err.message || '加载候选详情失败')
  } finally {
    scraping.value = false
    scrapeHint.value = ''
  }
}

async function applyCandidate() {
  const row = scrapeApplyCandidate.value
  const targetSongId = scrapeTargetSong.value?.id
  if (!targetSongId || !row) return
  if (!scrapeApplyFields.value.length) {
    message.warning('请至少选择一项要应用的更改')
    return
  }
  scraping.value = true
  scrapeHint.value = '写入中'
  try {
    // 用用户手动修改后的值替换候选
    const candidateToApply = { ...row }
    for (const field of SCRAPE_FIELD_DEFINITIONS) {
      if (field.key === 'cover') continue
      if (scrapeApplyFields.value.includes(field.key)) {
        const override = scrapeApplyOverrides.value[field.key]
        if (override !== undefined) {
          candidateToApply[field.key] = override
        }
      }
    }

    // 若封面已预览且候选来自 CAA/可能容器不通，把图片字节也提交，后端优先使用
    let coverImageBase64 = null
    let coverImageMime = null
    if (scrapeApplyFields.value.includes('cover') && scrapeCoverAvailable('candidate')) {
      const url = scrapeCoverImageUrl('candidate')
      if (url) {
        try {
          const fetched = await fetch(url)
          if (fetched.ok) {
            const blob = await fetched.blob()
            coverImageMime = blob.type || null
            coverImageBase64 = await new Promise((resolve, reject) => {
              const reader = new FileReader()
              reader.onloadend = () => resolve(reader.result)
              reader.onerror = reject
              reader.readAsDataURL(blob)
            })
          }
        } catch (_) {
          coverImageBase64 = null
        }
      }
    }

    const res = await applyScrapeCandidate(targetSongId, candidateToApply, {
      selected_fields: scrapeApplyFields.value,
      write_file_tags: true,
      cover_image_base64: coverImageBase64,
      cover_image_mime: coverImageMime,
    })
    const data = res.data || res || {}
    if (player.current?.id === targetSongId) {
      if (data.song) player.current = { ...player.current, ...data.song }
      if (scrapeApplyFields.value.includes('cover')) {
        try {
          const { coverUrl } = await import('@/api/music')
          const { useAuthStore } = await import('@/stores/auth')
          player.cover = data.song?.cover_path
            ? coverUrl(targetSongId, useAuthStore().token || '') + `&_t=${Date.now()}`
            : ''
        } catch (_) {}
      }
    }
    const fr = data.file_result || {}
    const failed = fr.failed || 0
    const unsupported = fr.unsupported || 0
    const written = fr.written || 0
    const errorSummary = data.error_summary || fr.error_summary || ''
    const versionErrors = (fr.versions || [])
      .filter((item) => item.status === 'failed' || item.error || item.cover_error)
      .map((item) => {
        const label = item.format || item.path || `#${item.song_file_id || '?'}`
        return `${label}: ${item.error || item.cover_error || item.reason || '失败'}`
      })
    const detail = errorSummary || versionErrors.slice(0, 3).join('；')
    if (failed) {
      message.warning(
        detail
          ? `元信息已保存；${written} 个版本成功，${failed} 个失败。${detail}`
          : `元信息已保存；已写入 ${written} 个版本，${failed} 个版本失败`,
        { duration: 8000, closable: true },
      )
      if (versionErrors.length) console.warn('[scrape apply] version errors', fr.versions, data)
    } else if (!data.ok && detail) {
      message.warning(`元信息部分保存：${detail}`, { duration: 8000, closable: true })
      console.warn('[scrape apply] partial/l0 failure', data)
    } else if (unsupported) {
      message.success(`元信息已保存；${written} 个版本已写标签，${unsupported} 个版本不支持内嵌（仅侧车/L0）`)
    } else {
      message.success(`已采用并写入 ${written} 个本地版本`)
    }
    scrapeApplyModalVisible.value = false
    scrapeApplyCandidate.value = null
    scrapeApplyFields.value = []
    scrapeModalVisible.value = false
    scrapeTargetSong.value = null
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
.top-left,
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
    width: min(110cqw, 110cqh, 580px);
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

/* 移动端全屏浮层形态 */
@media (max-width: 768px) {
  .volume-row {
    display: none;
  }
  .title {
    font-size: 19px;
  }
  .meta-block {
    padding: 4px 18px 0;
  }
  .progress {
    padding: 12px 18px 0;
  }
  .controls {
    padding-bottom: calc(14px + env(safe-area-inset-bottom, 0px));
  }
  .tap-hint {
    display: none;
  }
}

.tag-grid { display: grid; gap: 8px; }
.tag-row { display: grid; grid-template-columns: 110px minmax(0, 1fr); gap: 10px; align-items: start; }
.tag-key { color: var(--fg-3); font-size: 12px; }
.tag-val { color: var(--fg); font-size: 12px; word-break: break-all; white-space: pre-wrap; }
:deep(.mini-apply-btn) { border: 1px solid rgba(24,160,88,.45); color: rgb(24,160,88); background: transparent; border-radius: 6px; padding: 2px 8px; cursor: pointer; }
:deep(.mini-apply-btn:hover) { background: rgba(24,160,88,.12); }
.lyrics-workbench { display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(420px, .95fr); gap: 14px; min-height: 360px; }
.lyrics-compare { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; min-width: 0; }
.lyrics-compare-pane { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.lyrics-fetched-at { font-size: 12px; }
.lyrics-candidates { min-width: 0; }
.lyrics-preview { min-width: 0; border: 1px solid rgba(128,128,128,.22); border-radius: 10px; padding: 12px; background: rgba(127,127,127,.06); }
.lyrics-preview-header { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 10px; }
.lyrics-preview-text { height: 380px; margin: 0; overflow: auto; white-space: pre-wrap; word-break: break-word; font: inherit; font-size: 13px; line-height: 1.8; color: var(--fg); }
:deep(.lyrics-row-selected td) { background: rgba(24,160,88,.14) !important; }
:deep(.lyrics-candidates .n-data-table-tr) { cursor: pointer; }
.scrape-compare-list { display: grid; gap: 10px; max-height: 62vh; overflow: auto; padding-right: 4px; }
.scrape-compare-row { display: grid; grid-template-columns: 110px minmax(0, 1fr) minmax(0, 1fr) 48px; gap: 12px; align-items: center; padding: 12px; border: 1px solid rgba(128,128,128,.22); border-radius: 10px; }
.scrape-field-heading { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; }
.scrape-value-block { min-width: 0; }
.scrape-value-label { display: block; margin-bottom: 4px; color: var(--fg-3); font-size: 11px; }
.scrape-value-text { max-height: 90px; overflow: auto; color: var(--fg); font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }
.scrape-value-text.empty { color: var(--fg-4); font-style: italic; }
.scrape-cover-preview { display: flex; align-items: center; gap: 10px; min-width: 0; color: var(--fg-3); font-size: 12px; }
.scrape-cover-preview img, .scrape-cover-placeholder { width: 96px; height: 96px; flex: 0 0 96px; border-radius: 8px; border: 1px solid rgba(128,128,128,.24); background: rgba(128,128,128,.1); }
.scrape-cover-preview img { display: block; object-fit: cover; }
.scrape-cover-placeholder { display: grid; place-items: center; color: var(--fg-4); }
.scrape-cover-preview span { line-height: 1.5; word-break: break-word; }
.song-files-section { display: grid; gap: 8px; padding: 12px; border: 1px solid rgba(128,128,128,.22); border-radius: 10px; }
.song-files-heading { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.song-files-list { display: grid; gap: 8px; max-height: 220px; overflow-y: auto; }
.song-file-item { display: grid; gap: 6px; padding: 9px 10px; border-radius: 8px; background: rgba(128,128,128,.08); }
.song-file-summary { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; min-width: 0; font-size: 12px; }
.song-file-summary span { color: var(--fg-3); }
.song-file-path { overflow: hidden; color: var(--fg-3); font-size: 12px; line-height: 1.45; text-overflow: ellipsis; white-space: nowrap; }
@media (max-width: 720px) {
  .lyrics-workbench { grid-template-columns: 1fr; }
  .lyrics-compare { grid-template-columns: 1fr; }
  .lyrics-preview-text { height: 280px; }
  .lyrics-actions { position: sticky; bottom: 0; z-index: 3; padding: 10px 0; background: var(--bg); }
  .song-files-heading { align-items: flex-start; flex-direction: column; gap: 4px; }
  .song-file-path { white-space: normal; word-break: break-all; }
  .song-files-list { max-height: 260px; }
  .scrape-compare-row { grid-template-columns: minmax(0, 1fr) 48px; }
  .scrape-field-heading, .scrape-value-block { grid-column: 1; }
  .scrape-cover-preview img, .scrape-cover-placeholder { width: 80px; height: 80px; flex-basis: 80px; }
  .scrape-compare-row :deep(.n-switch) { grid-column: 2; grid-row: 1; }
}

</style>
