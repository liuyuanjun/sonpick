<template>
  <div class="player-panel" :class="{ light: !isDark }" :style="panelStyle">
    <div class="ambient" aria-hidden="true"></div>
    <div class="noise" aria-hidden="true"></div>

    <div class="panel-top">
      <div class="top-left">
        <n-tooltip v-if="player.fullPlayerOpen">
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
        <div class="view-switch" role="group" aria-label="皮肤">
          <n-tooltip v-for="skin in player.availableSkins" :key="skin.id">
            <template #trigger>
              <n-button
                class="view-toggle icon-top-btn"
                :class="{ active: player.playerSkin === skin.id }"
                :type="player.playerSkin === skin.id ? 'primary' : 'default'"
                :secondary="player.playerSkin === skin.id"
                :quaternary="player.playerSkin !== skin.id"
                circle
                size="small"
                :aria-label="skin.label"
                @click="player.setPlayerSkin(skin.id)"
              >
                <n-icon size="18"><component :is="skinIcons[skin.id]" /></n-icon>
              </n-button>
            </template>
            {{ skin.label }}
          </n-tooltip>
        </div>
      </div>
      <div class="top-right">
        <div v-if="player.showLyrics" class="font-size-ctrl" @click.stop>
          <n-button quaternary size="tiny" class="font-btn" :disabled="player.lyricFontSize <= 14" @click="player.setLyricFontSize(player.lyricFontSize - 1)">A-</n-button>
          <span class="font-size-label">{{ player.lyricFontSize }}</span>
          <n-button quaternary size="tiny" class="font-btn" :disabled="player.lyricFontSize >= 28" @click="player.setLyricFontSize(player.lyricFontSize + 1)">A+</n-button>
        </div>
        <n-dropdown trigger="click" placement="bottom-end" :options="moreMenuOptions" @select="onMoreSelect">
          <n-button class="icon-top-btn" quaternary circle size="small" aria-label="更多歌曲操作" :disabled="!player.current">
            <n-icon size="18"><ellipsis-horizontal /></n-icon>
          </n-button>
        </n-dropdown>
      </div>
    </div>

    <player-skin />

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
            <div>
              <strong>歌曲文件</strong>
              <n-text depth="3">保存时会写入全部可用本地版本；WebDAV 版本仅展示。</n-text>
            </div>
            <n-button size="small" :disabled="!canOrganizeCurrent" :loading="organizeLoading" @click="openOrganize">
              {{ canOrganizeCurrent ? '整理到标准路径' : '整理(需完整专辑/标题)' }}
            </n-button>
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

    <n-modal v-model:show="organizeVisible" preset="card" title="整理到标准路径" style="width: 760px; max-width: 96vw">
      <n-spin :show="organizeLoading && !organizeResult">
        <n-space vertical size="medium">
          <n-alert v-if="organizeError" type="error" :show-icon="false">
            {{ organizeError }}
          </n-alert>
          <n-space v-if="organizeError" justify="end">
            <n-button @click="organizeVisible = false">关闭</n-button>
            <n-button type="primary" :loading="organizeLoading" @click="openOrganize">重试</n-button>
          </n-space>
          <template v-else-if="organizePreview && !organizeResult">
            <n-alert v-if="organizePreview.blocked_count" type="warning" :show-icon="false">
              有 {{ organizePreview.blocked_count }} 个文件的目标路径被其它歌曲占用，将跳过（不会覆盖他人文件）。
            </n-alert>
            <div v-for="(move, mi) in (organizePreview.moves || [])" :key="mi" class="organize-move">
              <n-tag size="small" :type="move.blocked ? 'error' : (move.status === 'missing' || move.status === 'no_source' ? 'default' : (move.changed ? 'warning' : 'success'))">
                {{ move.blocked ? '跳过(被占用)' : (move.status === 'missing' ? '文件缺失' : move.status === 'no_source' ? '无本地源' : (move.changed ? '移动' : '已就位')) }}
              </n-tag>
              <div class="organize-move-body">
                <div class="organize-move-path" :title="move.from_path">
                  {{ move.from_path }}
                  <template v-if="move.changed && !move.blocked"> → <strong class="organize-move-to">{{ move.to_path }}</strong></template>
                </div>
                <div class="organize-move-meta">{{ move.format }} · {{ formatFileSize(move.file_size) }}<template v-if="move.bitrate"> · {{ move.bitrate }}kbps</template></div>
              </div>
            </div>
            <n-empty
              v-if="!(organizePreview.moves || []).length"
              size="small"
              :description="(organizePreview.excluded || []).length ? '没有可整理的本地版本' : '没有本地版本记录'"
            />
            <div v-if="(organizePreview.excluded || []).length" class="organize-excluded">
              <n-text depth="3">
                以下 {{ organizePreview.excluded.length }} 个版本命中扫描排除规则（回收站 / 隐藏目录），不参与整理与冲突判断：
              </n-text>
              <div v-for="(item, ei) in organizePreview.excluded" :key="'e' + ei" class="organize-excluded-item">
                <n-tag size="small" type="default">已排除</n-tag>
                <span class="organize-move-path" :title="item.from_path">{{ item.from_path }}</span>
              </div>
            </div>
            <n-divider v-if="(organizePreview.conflicts || []).length">路径冲突（请选择保留哪一个）</n-divider>
            <div v-for="(conflict, ci) in (organizePreview.conflicts || [])" :key="'c' + ci" class="organize-conflict">
              <n-radio-group v-model:value="organizeChoices[ci]" size="small">
                <n-space vertical>
                  <n-radio v-for="cand in conflict.candidates" :key="cand.song_file_id" :value="cand.song_file_id">
                    保留：{{ cand.from_path }}（{{ cand.format }} · {{ formatFileSize(cand.file_size) }}<template v-if="cand.bitrate"> · {{ cand.bitrate }}kbps</template>）
                  </n-radio>
                </n-space>
              </n-radio-group>
            </div>
            <n-space justify="end">
              <n-button @click="organizeVisible = false">取消</n-button>
              <n-button
                type="primary"
                :loading="organizeLoading"
                :disabled="!(organizePreview.moves || []).length"
                @click="applyOrganize"
              >
                确认整理
              </n-button>
            </n-space>
          </template>
          <template v-else-if="organizeResult">
            <n-alert type="success" :show-icon="false">
              移动 {{ organizeResult.moved }}，删除重复 {{ organizeResult.deleted }}，保留 {{ organizeResult.kept }}<template v-if="organizeResult.skipped">，跳过 {{ organizeResult.skipped }}</template>。
            </n-alert>
            <n-space justify="end">
              <n-button type="primary" @click="organizeVisible = false">完成</n-button>
            </n-space>
          </template>
          <n-empty v-else description="正在生成整理计划…" />
        </n-space>
      </n-spin>
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
import { NIcon, NTag, useDialog, useMessage } from 'naive-ui'
import {
  AlbumsOutline,
  ChevronDown,
  ColorWandOutline,
  DiscOutline,
  DocumentTextOutline,
  EllipsisHorizontal,
  ImageOutline,
  MusicalNotes,
  PricetagOutline,
  ReaderOutline,
} from '@vicons/ionicons5'
import {
  applyLyricsCandidate,
  clearLyrics,
  applyScrapeCandidate,
  fetchLyricsCandidateDetails,
  fetchScrapeCandidateDetails,
  fetchScrapeCandidates,
  fetchSongTags,
  searchLyricsCandidates,
  coverUrl,
  previewOrganizeSong,
  applyOrganizeSong,
} from '@/api/music'
import api from '@/api/client'
import { usePlayerStore } from '@/stores/player'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import { useIsMobile } from '@/composables/useIsMobile'
import { formatClock, formatDateTime, formatFileSize } from '@/utils/format'
import { ambientBackground, extractAccentFromImage } from '@/utils/color'
import { normalizeSongFiles, normalizedScrapeValue, shouldSelectScrapeField } from '@/utils/scrapeApply'
import PlayerSkin from '@/components/player/PlayerSkin.vue'
import { fetchSongFiles } from '@/api/music'

const player = usePlayerStore()
const themeStore = useThemeStore()
const message = useMessage()
const dialog = useDialog()
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

const organizeVisible = ref(false)
const organizeLoading = ref(false)
const organizePreview = ref(null)
const organizeChoices = ref([])
const organizeResult = ref(null)
const organizeError = ref('')

const canOrganizeCurrent = computed(() => {
  const s = scrapeTargetSong.value
  if (!s) return false
  const titleOk = !!(s.title && String(s.title).trim() && !/unknown|未知/i.test(s.title))
  const albumOk = !!(s.album && String(s.album).trim() && !/unknown|未知/i.test(s.album))
  const hasLocal = (scrapeSongFiles.value || []).some((f) => f.location === 'local' || f.writable)
  return titleOk && albumOk && hasLocal
})
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
  const duration = query.duration ? formatClock(query.duration) : '未知时长'
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
  return formatDateTime(value, { withYear: true, fallback: '' })
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
const skinIcons = {
  card: AlbumsOutline,
  vinyl: DiscOutline,
  lyrics: ReaderOutline,
  art: ImageOutline,
}
const moreMenuOptions = [
  { label: '标签', key: 'tag', icon: () => h(NIcon, null, { default: () => h(PricetagOutline) }) },
  { label: '刮削信息', key: 'scrape', icon: () => h(NIcon, null, { default: () => h(ColorWandOutline) }) },
  { label: '获取歌词', key: 'lyrics', icon: () => h(NIcon, null, { default: () => h(DocumentTextOutline) }) },
]
function onMoreSelect(key) {
  if (key === 'tag') openTagModal()
  else if (key === 'scrape') openScrapeModal()
  else if (key === 'lyrics') openLyricsModal()
}

const tagRows = computed(() => {
  const db = tagData.value?.db || {}
  const em = tagData.value?.embedded || {}
  return [
    { key: 'db_title', label: 'DB 标题', value: db.title },
    { key: 'db_artist', label: 'DB 艺术家', value: db.artist },
    { key: 'db_album', label: 'DB 专辑', value: db.album },
    { key: 'db_year', label: 'DB 年份', value: db.year },
    { key: 'db_genre', label: 'DB 风格', value: db.genre },
    { key: 'db_duration', label: 'DB 时长', value: formatClock(db.duration || 0) },
    { key: 'db_cover', label: 'DB 封面', value: db.cover_path },
    { key: 'tag_title', label: '内嵌标题', value: em.title },
    { key: 'tag_artist', label: '内嵌艺术家', value: em.artist },
    { key: 'tag_album', label: '内嵌专辑', value: em.album },
    { key: 'tag_year', label: '内嵌年份', value: em.year },
    { key: 'tag_genre', label: '内嵌风格', value: em.genre },
    { key: 'tag_duration', label: '内嵌时长', value: formatClock(em.duration || 0) },
    { key: 'tag_cover', label: '内嵌封面', value: em.cover_embedded ? `有（${em.cover_size || 0} bytes）` : '无' },
    { key: 'tag_lyrics', label: '内嵌歌词', value: em.lyrics ? `${String(em.lyrics).slice(0, 120)}...` : '' },
    { key: 'file_version', label: '文件版本', value: tagData.value?.file_version_id ? `#${tagData.value.file_version_id}` : '无可用本地版本' },
  ]
})

const scrapeQueryText = computed(() => {
  const q = scrapeQuery.value
  if (!q) return ''
  return `查询：${q.keyword || ''} / 时长 ${q.duration ? formatClock(q.duration) : '-'}`
})

const candidateColumns = computed(() => [
  { title: '分', key: 'score', width: 64, render: (row) => Number(row.score || 0).toFixed(1) },
  { title: '源', key: 'source', width: 78 },
  { title: '标题', key: 'title', ellipsis: { tooltip: true } },
  { title: '艺术家', key: 'artist', ellipsis: { tooltip: true } },
  { title: '专辑', key: 'album', ellipsis: { tooltip: true } },
  { title: '时长', key: 'duration', width: 76, render: (row) => row.duration ? formatClock(row.duration) : '-' },
  { title: '封面', key: 'cover_url', width: 92, render: (row) => row.has_cover || row.cover_url ? (row.cover_source ? `有/${row.cover_source}` : '有') : '无' },
  { title: '操作', key: 'actions', width: 90, render: (row) => h('button', { class: 'mini-apply-btn', onClick: () => openApplyCandidate(row) }, '采用') },
])

const panelStyle = computed(() => {
  const bg = ambientBackground(accent.value, { dark: isDark.value })
  const a = accent.value
  return {
    ...bg,
    '--accent': a ? a.css : 'var(--sp-ui-primary)',
    '--accent-soft': a ? a.soft : 'color-mix(in srgb, var(--sp-ui-primary) 35%, transparent)',
    '--accent-glow': a ? a.glow : 'color-mix(in srgb, var(--sp-ui-primary) 45%, transparent)',
    // 播放键填充 = 封面主题色，图标用主题色上的可读色：
    // 「正在播放」这一整块（播放键 / 进度 / 音量）只有一种颜色语言 = 主题色。
    '--play-bg': a ? a.css : 'var(--sp-ui-primary)',
    '--play-fg': a ? a.on || '#FFFFFF' : 'var(--sp-ui-on-primary)',
  }
})

watch(
  () => player.cover,
  async (url) => {
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

async function openLyricsModal() {
  const session = ++lyricsModalSession
  const song = player.current
  if (!song?.id) return
  lyricsTargetSong.value = { ...song }
  lyricsKeyword.value = `${song.title || ''} ${song.artist || ''}`.trim()
  lyricsQuery.value = null
  lyricsCurrent.value = {}
  lyricsSongFiles.value = song.versions || []
  // 同步刮削弹窗：拉取后端权威文件列表，避免 versions 缺失时「暂无歌曲文件记录」。
  fetchSongFiles(song.id)
    .then((res) => {
      const files = res?.data?.song_files || []
      if (files.length) lyricsSongFiles.value = files
    })
    .catch(() => {})
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
  // 先用内存 versions 即时展示（若有）；再拉取后端权威文件列表（与播放共用 SongFileResolver），
  // 避免歌曲来自未填充 versions 的上下文（如歌单）时显示「暂无歌曲文件记录」。
  scrapeSongFiles.value = normalizeSongFiles(song.versions || []).map((item) => ({ ...item }))
  scrapeQuery.value = null
  scrapeKeyword.value = `${song.title || song.song_name || ''} ${song.artist || song.singers || ''}`.trim()
  fetchSongFiles(song.id)
    .then((res) => {
      const files = res?.data?.song_files || []
      if (files.length) scrapeSongFiles.value = files
    })
    .catch(() => {})
}

async function openOrganize() {
  const song = scrapeTargetSong.value
  if (!song?.id) return
  organizeVisible.value = true
  organizeLoading.value = true
  organizeResult.value = null
  organizeError.value = ''
  organizePreview.value = null
  try {
    const res = await previewOrganizeSong(song.id)
    const data = res?.data || res || {}
    organizePreview.value = data
    // 默认保留码率更高（其次体积更大）的版本
    organizeChoices.value = (data.conflicts || []).map((c) =>
      c.candidates.reduce((best, x) => {
        const sx = (x.bitrate || 0) * 1000000 + (x.file_size || 0)
        const sb = (best.bitrate || 0) * 1000000 + (best.file_size || 0)
        return sx >= sb ? x : best
      }).song_file_id,
    )
  } catch (err) {
    // 弹窗保持打开并显示原因，避免"点开一片空白"
    organizeError.value = err.response?.data?.detail || err.message || '预览整理失败'
    message.error(organizeError.value)
  } finally {
    organizeLoading.value = false
  }
}

async function applyOrganize() {
  const song = scrapeTargetSong.value
  if (!song?.id) return
  organizeLoading.value = true
  organizeError.value = ''
  try {
    const res = await applyOrganizeSong(song.id, { choices: organizeChoices.value })
    const data = res?.data || res || {}
    organizeResult.value = data
    message.success(`整理完成：移动 ${data.moved || 0}，删除重复 ${data.deleted || 0}，保留 ${data.kept || 0}`)
    // 刷新文件列表
    fetchSongFiles(song.id)
      .then((r) => {
        const files = r?.data?.song_files || []
        if (files.length) scrapeSongFiles.value = files
      })
      .catch(() => {})
  } catch (err) {
    organizeError.value = err.response?.data?.detail || err.message || '整理失败'
    message.error(organizeError.value)
  } finally {
    organizeLoading.value = false
  }
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
  /* 播放键的填充/前景由 panelStyle 按封面主题色注入（见 script）；
     这里只给无强调色时的兜底（品牌主色 + on-primary） */
  --play-bg: var(--sp-ui-primary);
  --play-fg: var(--sp-ui-on-primary);
  --vinyl-shadow: drop-shadow(0 18px 40px rgba(0, 0, 0, 0.42));
  --vinyl-bg-a: #1a1a1a;
  --vinyl-bg-b: #0d0d0d;
  --bg: rgba(10, 11, 15, 0.92);
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
  --vinyl-shadow: drop-shadow(0 14px 28px rgba(20, 30, 50, 0.14));
  --vinyl-bg-a: #e8ecf2;
  --vinyl-bg-b: #d5dbe6;
  --bg: rgba(255, 255, 255, 0.94);
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


.tag-grid { display: grid; gap: 8px; }
.tag-row { display: grid; grid-template-columns: 110px minmax(0, 1fr); gap: 10px; align-items: start; }
.tag-key { color: var(--fg-3); font-size: 12px; }
.tag-val { color: var(--fg); font-size: 12px; word-break: break-all; white-space: pre-wrap; }
:deep(.mini-apply-btn) { border: 1px solid color-mix(in srgb, var(--sp-ui-primary) 45%, transparent); color: var(--sp-ui-primary); background: transparent; border-radius: 6px; padding: 2px 8px; cursor: pointer; }
:deep(.mini-apply-btn:hover) { background: color-mix(in srgb, var(--sp-ui-primary) 12%, transparent); }
.lyrics-workbench { display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(420px, .95fr); gap: 14px; min-height: 360px; }
.lyrics-compare { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; min-width: 0; }
.lyrics-compare-pane { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.lyrics-fetched-at { font-size: 12px; }
.lyrics-candidates { min-width: 0; }
.lyrics-preview { min-width: 0; border: 1px solid rgba(128,128,128,.22); border-radius: 10px; padding: 12px; background: rgba(127,127,127,.06); }
.lyrics-preview-header { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 10px; }
.lyrics-preview-text { height: 380px; margin: 0; overflow: auto; white-space: pre-wrap; word-break: break-word; font: inherit; font-size: 13px; line-height: 1.8; color: var(--fg); }
:deep(.lyrics-row-selected td) { background: color-mix(in srgb, var(--sp-ui-primary) 14%, transparent) !important; }
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
.song-file-summary span { color: var(--sp-ui-text-3); }
.song-file-path { overflow: hidden; color: var(--sp-ui-text-3); font-size: 12px; line-height: 1.45; text-overflow: ellipsis; white-space: nowrap; }

/* 整理到标准路径：弹窗内容 teleport 到 body，颜色统一走 --sp-ui-*（AGENTS §5.5） */
.organize-move, .organize-excluded-item { display: flex; gap: 8px; align-items: flex-start; padding: 8px 10px; border-radius: 8px; background: var(--sp-ui-hover); }
.organize-move { flex-direction: row; }
.organize-move-body { flex: 1 1 auto; display: grid; gap: 2px; min-width: 0; }
.organize-move-path { overflow: hidden; min-width: 0; color: var(--sp-ui-text-2); font-size: 12px; line-height: 1.5; text-overflow: ellipsis; white-space: nowrap; }
.organize-move-to { color: var(--sp-ui-primary); font-weight: 500; }
.organize-move-meta { color: var(--sp-ui-text-3); font-size: 11px; }
.organize-excluded { display: grid; gap: 6px; }
.organize-excluded-item { padding: 6px 10px; }
.organize-conflict { padding: 8px 10px; border-radius: 8px; background: var(--sp-ui-hover); }
@media (max-width: 720px) {
  .lyrics-workbench { grid-template-columns: 1fr; }
  .lyrics-compare { grid-template-columns: 1fr; }
  .lyrics-preview-text { height: 280px; }
  .lyrics-actions { position: sticky; bottom: 0; z-index: 3; padding: 10px 0; background: var(--bg); }
  .song-files-heading { align-items: flex-start; flex-direction: column; gap: 4px; }
  .song-file-path { white-space: normal; word-break: break-all; }
  .organize-move-path { white-space: normal; word-break: break-all; }
  .song-files-list { max-height: 260px; }
  .scrape-compare-row { grid-template-columns: minmax(0, 1fr) 48px; }
  .scrape-field-heading, .scrape-value-block { grid-column: 1; }
  .scrape-cover-preview img, .scrape-cover-placeholder { width: 80px; height: 80px; flex-basis: 80px; }
  .scrape-compare-row :deep(.n-switch) { grid-column: 2; grid-row: 1; }
}

</style>
