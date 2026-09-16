<template>
  <n-modal
    :show="show"
    preset="card"
    title="歌曲信息"
    class="song-info-modal"
    style="width: 780px; max-width: 96vw"
    @update:show="emit('update:show', $event)"
  >
    <div v-if="song" class="info-body">
      <div class="info-head">
        <div class="cover-wrap">
          <img v-if="coverSrc && !coverBroken" :src="coverSrc" alt="" @error="coverBroken = true" />
          <div v-else class="cover-placeholder">
            <n-icon :size="42"><musical-notes /></n-icon>
          </div>
        </div>

        <div class="info-meta">
          <div class="info-title">{{ song.title || '未知歌曲' }}</div>
          <div class="info-sub">{{ artistLine }}</div>

          <div class="chip-row">
            <n-tag v-if="preferred" size="small" :type="isLossless ? 'success' : 'default'">
              {{ formatLabel(preferred.format) }}
            </n-tag>
            <n-tag v-if="preferred" size="small" :type="preferred.location === 'local' ? 'default' : 'info'">
              {{ preferred.location === 'local' ? '本地' : 'WebDAV' }}
            </n-tag>
            <n-tag v-if="song.lyrics_instrumental" size="small" type="info">纯音乐</n-tag>
            <n-tag v-if="!song.has_playable_file" size="small" type="warning">无可用文件</n-tag>
          </div>

          <dl class="kv-grid">
            <div class="kv"><dt>时长</dt><dd>{{ durationText }}</dd></div>
            <div class="kv"><dt>年份</dt><dd>{{ song.year || '—' }}</dd></div>
            <div class="kv"><dt>风格</dt><dd>{{ song.genre || '—' }}</dd></div>
            <div class="kv"><dt>播放次数</dt><dd>{{ song.play_count ?? 0 }}</dd></div>
            <div class="kv"><dt>可用性</dt><dd>{{ availabilityText }}</dd></div>
            <div class="kv"><dt>来源平台</dt><dd>{{ song.source || '—' }}</dd></div>
          </dl>
        </div>
      </div>

      <section class="info-section">
        <div class="section-title">
          文件版本
          <span class="section-count">{{ versions.length }}</span>
          <span v-if="versions.length > 1" class="section-hint">列表列显示的是「首选」（无损优先，与实际播放选择同一规则）</span>
        </div>
        <div v-if="versions.length" class="version-list">
          <div
            v-for="v in versions"
            :key="v.id"
            class="version-row"
            :class="{ 'is-preferred': preferred && v.id === preferred.id }"
          >
            <n-tag size="small" :type="isLosslessFormat(v.format) ? 'success' : 'default'">
              {{ formatLabel(v.format) }}
            </n-tag>
            <span class="v-text">{{ formatFileSize(v.file_size) }}</span>
            <span class="v-text">{{ versionLocationLabel(v) }}</span>
            <span class="v-text v-source">{{ sourceName(v) }}</span>
            <n-tag size="small" :type="availabilityTagType(v.availability_status)">{{ availabilityLabel(v.availability_status) }}</n-tag>
            <span v-if="preferred && v.id === preferred.id" class="v-badge">首选</span>
          </div>
          <div v-for="v in versionsWithError" :key="`e${v.id}`" class="version-error">
            {{ sourceName(v) }} · {{ formatLabel(v.format) }}：{{ v.last_error }}
          </div>
        </div>
        <n-empty v-else size="small" description="暂无文件版本记录" />
      </section>

      <section class="info-section">
        <div class="section-title">歌词</div>
        <dl class="kv-grid">
          <div class="kv"><dt>类型</dt><dd>{{ lyricsTypeText }}</dd></div>
          <div class="kv"><dt>来源</dt><dd>{{ song.lyrics_provider || '—' }}</dd></div>
          <div class="kv"><dt>匹配度</dt><dd>{{ song.lyrics_score != null ? song.lyrics_score : '—' }}</dd></div>
          <div class="kv"><dt>抓取时间</dt><dd>{{ fetchedAtText }}</dd></div>
        </dl>
      </section>
    </div>
    <n-spin v-else :show="true" />
  </n-modal>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { NIcon } from 'naive-ui'
import { MusicalNotes } from '@vicons/ionicons5'
import { coverUrl, fetchSources } from '@/api/music'
import { useAuthStore } from '@/stores/auth'
import { formatClock, formatFileSize } from '@/utils/format'
import {
  availabilityLabel,
  availabilityTagType,
  formatLabel,
  isLosslessFormat,
  versionLocationLabel,
} from '@/utils/media'

// 歌曲信息弹窗：数据全部取自列表行（SongOut），不发额外详情请求。
// 但「来源名称」只能由 media_sources 映射得到，故打开时拉一次并缓存。
const props = defineProps({
  show: { type: Boolean, default: false },
  song: { type: Object, default: null },
})
const emit = defineEmits(['update:show'])

const auth = useAuthStore()
const coverBroken = ref(false)
const sourceNames = ref({})
let sourcesLoaded = false

const versions = computed(() => (Array.isArray(props.song?.versions) ? props.song.versions : []))
const preferred = computed(() => props.song?.preferred_version || null)
const versionsWithError = computed(() => versions.value.filter((v) => v.last_error))

const coverSrc = computed(() => (props.song?.cover_path ? coverUrl(props.song.id, auth.token) : ''))
const isLossless = computed(() => isLosslessFormat(preferred.value?.format))

const artistLine = computed(() => {
  const song = props.song
  if (!song) return ''
  return [song.artist, song.album].filter(Boolean).join(' · ') || '未知艺术家'
})

const durationText = computed(() => (props.song?.duration ? formatClock(props.song.duration) : '—'))

const availabilityText = computed(() => {
  if (!props.song) return '—'
  if (!props.song.has_playable_file) return '无可用文件'
  const parts = []
  if (props.song.status === 'remote') parts.push('仅远端')
  else if (props.song.status === 'both') parts.push('本地 + 远端')
  else if (props.song.status === 'uploaded') parts.push('已上传')
  else parts.push('本地')
  return parts.join('')
})

const lyricsTypeText = computed(() => {
  const song = props.song
  if (!song) return '—'
  if (song.lyrics_instrumental || song.lyrics_type === 'instrumental') return '纯音乐标记'
  if (song.lyrics_type === 'synced') return '同步歌词'
  if (song.lyrics_type === 'plain') return '纯文本'
  if (song.lyrics_type === 'empty') return '无歌词'
  return '未获取'
})

const fetchedAtText = computed(() => {
  const raw = props.song?.lyrics_fetched_at
  if (!raw) return '—'
  const date = new Date(raw)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString()
})

/** 来源名优先用 media_sources 映射，取不到时回落到位置标签（本地 / WebDAV） */
function sourceName(v) {
  const id = v.library_source_id ?? v.source_id
  return sourceNames.value[id] || versionLocationLabel(v)
}

async function loadSources() {
  if (sourcesLoaded) return
  sourcesLoaded = true
  try {
    const res = await fetchSources()
    const map = {}
    for (const source of res.data || []) map[source.id] = source.name
    sourceNames.value = map
  } catch {
    sourcesLoaded = false
  }
}

watch(
  () => props.show,
  (open) => {
    if (open) {
      coverBroken.value = false
      loadSources()
    }
  },
)
</script>

<style scoped>
.info-body {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.info-head {
  display: flex;
  gap: 18px;
  min-width: 0;
}
.cover-wrap {
  flex: 0 0 168px;
  width: 168px;
  height: 168px;
  border-radius: 12px;
  overflow: hidden;
  background: var(--sp-ui-hover);
  display: flex;
  align-items: center;
  justify-content: center;
}
.cover-wrap img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.cover-placeholder {
  color: var(--sp-ui-text-3);
}
.info-meta {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.info-title {
  font-size: 18px;
  font-weight: 500;
  line-height: 1.3;
  color: var(--sp-ui-text-1);
  word-break: break-word;
}
.info-sub {
  font-size: 13px;
  color: var(--sp-ui-text-2);
  word-break: break-word;
}
.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.kv-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 6px 16px;
  margin: 4px 0 0;
}
.kv {
  display: flex;
  gap: 8px;
  min-width: 0;
  font-size: 12px;
  line-height: 1.6;
}
.kv dt {
  flex: 0 0 56px;
  color: var(--sp-ui-text-3);
}
.kv dd {
  flex: 1 1 auto;
  min-width: 0;
  margin: 0;
  color: var(--sp-ui-text-2);
  word-break: break-word;
}
.info-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
  border-top: 1px solid var(--sp-ui-divider);
  padding-top: 14px;
}
.section-title {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 13px;
  font-weight: 500;
  color: var(--sp-ui-text-1);
}
.section-count {
  font-size: 12px;
  font-weight: 400;
  color: var(--sp-ui-text-3);
}
.section-hint {
  font-size: 12px;
  font-weight: 400;
  color: var(--sp-ui-text-3);
}
.version-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.version-row {
  display: grid;
  grid-template-columns: 76px 84px 72px minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--sp-ui-hover);
  font-size: 12px;
  color: var(--sp-ui-text-2);
}
.version-row.is-preferred {
  background: color-mix(in srgb, var(--sp-ui-primary) 10%, transparent);
}
.v-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.v-source {
  color: var(--sp-ui-text-3);
}
.v-badge {
  font-size: 11px;
  color: var(--sp-ui-primary);
  white-space: nowrap;
}
.version-error {
  font-size: 12px;
  line-height: 1.5;
  color: var(--sp-ui-error);
  padding: 0 10px;
  word-break: break-word;
}

@media (max-width: 768px) {
  .info-head {
    flex-direction: column;
    align-items: center;
  }
  .cover-wrap {
    flex: 0 0 auto;
    width: 140px;
    height: 140px;
  }
  .info-meta {
    width: 100%;
  }
  .version-row {
    grid-template-columns: 68px 78px minmax(0, 1fr) auto;
    row-gap: 4px;
  }
  .v-source,
  .v-badge {
    display: none;
  }
}
</style>
