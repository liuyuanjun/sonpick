<template>
  <n-space vertical size="large" style="width: 100%" class="playlist-import" :class="{ mobile: isMobile }">
    <n-alert type="info" :bordered="false">
      粘贴歌单链接（支持 QQ 音乐 / 网易云 / 咪咕 / 酷狗 / 酷我 / 千千），解析后勾选曲目下载。曲目按平台 song_id 锁定，下载时自动验证可用格式。
    </n-alert>
    <div class="url-bar">
      <n-input
        v-model:value="url"
        placeholder="例如：https://music.163.com/#/playlist?id=3039971654"
        class="url-input"
        @keydown.enter="doParse"
      />
      <n-button type="primary" :loading="parsing" @click="doParse">解析歌单</n-button>
    </div>

    <template v-if="playlist">
      <div class="playlist-head">
        <span class="playlist-name">{{ playlist.name }}</span>
        <n-tag size="small" :bordered="false">{{ playlist.source_label }}</n-tag>
        <n-text depth="3">共 {{ playlist.track_count }} 首，已选 {{ selectedKeys.length }} 首</n-text>
      </div>

      <sp-table
        v-if="!isMobile"
        :columns="columns"
        :data="playlist.tracks"
        :row-key="rowKey"
        :checked-row-keys="selectedKeys"
        :scroll-y="480"
        size="small"
        @update:checked-row-keys="onCheck"
      />
      <div v-else class="mobile-track-list">
        <div class="mobile-track-actions">
          <n-button size="tiny" tertiary @click="selectAll">全选</n-button>
          <n-button size="tiny" tertiary @click="selectedKeys = []">清空</n-button>
        </div>
        <div v-for="(t, i) in playlist.tracks" :key="rowKey(t)" class="track-card">
          <n-checkbox :checked="selectedKeys.includes(rowKey(t))" @update:checked="(v) => toggleTrack(t, v)" />
          <div class="track-meta">
            <div class="track-title">{{ i + 1 }}. {{ t.song_name || '未知歌曲' }}</div>
            <div class="track-sub">{{ t.singers || '未知歌手' }} · {{ t.album || '未知专辑' }}</div>
          </div>
          <span class="track-duration">{{ formatDuration(t) }}</span>
        </div>
      </div>

      <div class="import-toolbar">
        <n-select v-model:value="prefer" :options="formatOptions" class="format-select" />
        <n-select v-model:value="dupAction" :options="dupOptions" class="dup-select" />
        <n-button
          type="primary"
          class="start-btn"
          :disabled="!selectedKeys.length"
          :loading="loading"
          @click="start"
        >
          下载所选（{{ selectedKeys.length }} 首）
        </n-button>
      </div>
    </template>
  </n-space>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useMessage } from 'naive-ui'
import api from '@/api/client'
import { useIsMobile } from '@/composables/useIsMobile'
import { DUPLICATE_ACTION_OPTIONS, FORMAT_PREFER_OPTIONS } from '@/utils/downloadOptions'
import { formatClock } from '@/utils/format'

const message = useMessage()
const isMobile = useIsMobile()
const url = ref('')
const parsing = ref(false)
const playlist = ref(null)
const selectedKeys = ref([])
const prefer = ref('any')
const dupAction = ref('skip')
const loading = ref(false)

// 选项清单的统一来源在 utils/downloadOptions.js
const formatOptions = FORMAT_PREFER_OPTIONS
const dupOptions = DUPLICATE_ACTION_OPTIONS

// 默认格式跟随系统设置（设置页 prefer_format），用户可临时改
onMounted(async () => {
  try {
    const { data } = await api.get('/settings')
    if (data?.prefer_format) prefer.value = data.prefer_format
  } catch (_) {
    /* 设置拉取失败时用页面默认值 */
  }
})

function rowKey(row) {
  return `${row.source_index}`
}

function formatDuration(t) {
  return t.duration || (t.duration_s ? formatClock(t.duration_s) : '-')
}

const columns = [
  { type: 'selection' },
  { title: '#', key: 'source_index', width: 56, render: (row) => row.source_index + 1 },
  { title: '歌名', key: 'song_name', ellipsis: { tooltip: true } },
  { title: '歌手', key: 'singers', ellipsis: { tooltip: true } },
  { title: '专辑', key: 'album', ellipsis: { tooltip: true } },
  { title: '时长', key: 'duration', width: 80, render: (row) => formatDuration(row) },
]

async function doParse() {
  if (!url.value.trim()) {
    message.warning('请先粘贴歌单链接')
    return
  }
  parsing.value = true
  playlist.value = null
  selectedKeys.value = []
  try {
    const { data } = await api.post('/download/playlist/parse', { url: url.value.trim() })
    // 曲目在源内的原始序号（展示与 rowKey 用）
    data.tracks = (data.tracks || []).map((t, i) => ({ ...t, source_index: i }))
    playlist.value = data
    selectedKeys.value = data.tracks.map((t) => rowKey(t))
    if (!data.tracks.length) message.info('歌单里没有可识别的曲目')
  } catch (err) {
    message.error(err.response?.data?.detail || '歌单解析失败')
  } finally {
    parsing.value = false
  }
}

function onCheck(keys) {
  selectedKeys.value = keys
}

function toggleTrack(t, checked) {
  const key = rowKey(t)
  selectedKeys.value = checked
    ? [...selectedKeys.value, key]
    : selectedKeys.value.filter((k) => k !== key)
}

function selectAll() {
  selectedKeys.value = (playlist.value?.tracks || []).map((t) => rowKey(t))
}

async function start() {
  const pl = playlist.value
  if (!pl || !selectedKeys.value.length) return
  const picked = pl.tracks.filter((t) => selectedKeys.value.includes(rowKey(t)))
  loading.value = true
  try {
    await api.post('/download/batch', {
      items: picked.map((t) => ({
        keyword: `${t.song_name || ''} ${t.singers || ''}`.trim(),
        source: pl.source,
        song_id: t.song_id,
      })),
      prefer: prefer.value,
      source: pl.source,
      duplicate_action: dupAction.value,
    })
    message.success(`已创建批量下载任务（${picked.length} 首），进度见任务中心`)
  } catch (err) {
    message.error(err.response?.data?.detail || '创建下载任务失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.url-bar {
  display: flex;
  gap: 10px;
}
.url-input {
  flex: 1;
}
.playlist-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.playlist-name {
  font-weight: 600;
  font-size: var(--sp-fs-body);
}
.import-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.format-select {
  width: 140px;
}
.dup-select {
  width: 160px;
}
.mobile-track-actions {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}
.track-card {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--sp-ui-border);
  border-radius: var(--sp-radius-md);
  padding: 10px 12px;
  margin-bottom: 8px;
  background: color-mix(in srgb, var(--sp-ui-card) 92%, transparent);
}
.track-meta {
  flex: 1;
  min-width: 0;
}
.track-title {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.track-sub {
  font-size: var(--sp-fs-caption);
  opacity: 0.75;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.track-duration {
  font-size: var(--sp-fs-caption);
  opacity: 0.65;
}
@media (max-width: 768px) {
  .url-bar {
    flex-direction: column;
  }
  .import-toolbar {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }
  .format-select,
  .dup-select,
  .start-btn {
    width: 100%;
  }
  .start-btn {
    grid-column: 1 / -1;
  }
}
</style>
