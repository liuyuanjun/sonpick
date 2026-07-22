<template>
  <n-space vertical size="large" style="width: 100%" class="search-download" :class="{ mobile: isMobile }">
    <div class="toolbar">
      <n-input
        v-model:value="keyword"
        placeholder="输入歌名或歌手"
        class="keyword-input"
        @keydown.enter="doSearch(1)"
      />
      <n-select v-model:value="source" :options="sourceOptions" class="source-select" />
      <n-select v-model:value="prefer" :options="formatOptions" class="format-select" />
      <div class="toolbar-actions">
        <n-button type="primary" :loading="searching" class="action-btn" @click="doSearch(1)">搜索</n-button>
        <n-button
          type="success"
          :disabled="!checked.length"
          :loading="downloading"
          class="action-btn"
          @click="downloadSelected"
        >
          下载选中 ({{ checked.length }})
        </n-button>
      </div>
    </div>

    <n-data-table
      v-if="!isMobile"
      :columns="columns"
      :data="results"
      :row-key="rowKey"
      :loading="searching"
      :checked-row-keys="checked"
      @update:checked-row-keys="checked = $event"
    />

    <div v-else class="mobile-result-list">
      <n-spin :show="searching">
        <n-empty v-if="!results.length && !searching" description="暂无搜索结果" />
        <n-space v-else vertical size="small">
          <div
            v-for="row in results"
            :key="rowKey(row)"
            class="result-card"
            :class="{ selected: checked.includes(rowKey(row)) }"
            @click="toggleChecked(row)"
          >
            <div class="result-main">
              <n-checkbox
                :checked="checked.includes(rowKey(row))"
                @click.stop
                @update:checked="() => toggleChecked(row)"
              />
              <div class="result-meta">
                <div class="result-title">{{ row.song_name || '未知歌曲' }}</div>
                <div class="result-sub">{{ row.singers || '未知歌手' }} · {{ row.album || '未知专辑' }}</div>
                <div class="result-tags">
                  <n-tag size="small" type="info">{{ (row.ext || '-').toUpperCase() }}</n-tag>
                  <n-tag size="small">{{ row.file_size || row.filesize || '-' }}</n-tag>
                  <n-tag size="small" :bordered="false">{{ row.source || '-' }}</n-tag>
                  <n-tag
                    v-if="row.library_match"
                    size="small"
                    :type="row.library_match.status === 'exists' ? 'warning' : 'default'"
                  >
                    {{ matchLabel(row.library_match) }}
                  </n-tag>
                  <n-button size="tiny" tertiary class="row-download" @click.stop="downloadOne(row)">
                    下载
                  </n-button>
                </div>
              </div>
            </div>
          </div>
        </n-space>
      </n-spin>
    </div>

    <n-space class="pager" :justify="isMobile ? 'center' : 'end'" align="center" :wrap="true">
      <n-text depth="3">共 {{ total }} 条（每源约 10 条），当前第 {{ page }} 页</n-text>
      <n-pagination
        v-model:page="page"
        :page-size="pageSize"
        :item-count="total"
        :simple="isMobile"
        @update:page="doSearch"
      />
    </n-space>

    <n-modal
      v-model:show="dupDialogVisible"
      preset="card"
      :title="dupRow?.library_match?.status === 'exists' ? '曲库已存在' : '疑似已存在'"
      style="width: min(520px, 94vw)"
      :mask-closable="false"
    >
      <n-space vertical size="medium" v-if="dupRow?.library_match">
        <n-text depth="3">
          曲库中已收录
          <b>{{ dupRow.library_match.artist || '未知歌手' }} - {{ dupRow.library_match.title || '未知歌曲' }}</b>
          <template v-if="dupRow.library_match.album">（{{ dupRow.library_match.album }}）</template>
          ，包含以下版本：
        </n-text>
        <ul class="version-list">
          <li v-for="v in dupRow.library_match.versions" :key="v.song_file_id">
            {{ versionText(v) }}
            <span v-if="v.location !== 'local'" class="version-note">（远端版本暂不支持替换）</span>
            <span v-else-if="!v.replaceable" class="version-note">（文件不可访问，无法替换）</span>
          </li>
        </ul>
        <n-radio-group v-model:value="dupAction" class="dup-actions">
          <n-space vertical>
            <n-radio value="keep_both">保留两者，下载为新版本</n-radio>
            <n-radio value="replace" :disabled="!replaceableVersions.length">
              下载完成后替换所选版本
            </n-radio>
          </n-space>
        </n-radio-group>
        <n-select
          v-if="dupAction === 'replace'"
          v-model:value="dupReplaceId"
          :options="replaceOptions"
          placeholder="选择要替换的本地版本"
        />
      </n-space>
      <template #footer>
        <n-space justify="end">
          <n-button @click="resolveDupDialog(null)">取消</n-button>
          <n-button type="primary" @click="confirmDupDialog">确认下载</n-button>
        </n-space>
      </template>
    </n-modal>
  </n-space>
</template>

<script setup>
import { computed, h, ref } from 'vue'
import { NButton, NTag, NTooltip, useMessage } from 'naive-ui'
import api from '@/api/client'
import { searchMusic } from '@/api/music'
import { useIsMobile } from '@/composables/useIsMobile'

const message = useMessage()
const isMobile = useIsMobile()
const keyword = ref('')
const prefer = ref('any')
const source = ref('QQMusicClient')
const searching = ref(false)
const downloading = ref(false)
const results = ref([])
const checked = ref([])
const page = ref(1)
const pageSize = 20
const total = ref(0)

const formatOptions = [
  { label: '任意', value: 'any' },
  { label: 'FLAC', value: 'flac' },
  { label: 'MP3', value: 'mp3' },
  { label: 'M4A', value: 'm4a' },
]

const sourceOptions = [
  { label: 'QQ 音乐', value: 'QQMusicClient' },
  { label: '网易云音乐', value: 'NeteaseMusicClient' },
  { label: '咪咕音乐', value: 'MiguMusicClient' },
  { label: '全部来源', value: 'all' },
]

function formatSize(bytes) {
  const n = Number(bytes)
  if (!n || n <= 0) return '-'
  if (n >= 1024 * 1024 * 1024) return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`
  if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  return `${(n / 1024).toFixed(0)} KB`
}

function matchLabel(match) {
  return match?.status === 'exists' ? '曲库已存在' : '疑似已存在'
}

function versionText(v) {
  const parts = [v.location === 'local' ? '本地' : '远端']
  if (v.format) parts.push(v.format.toUpperCase())
  if (v.size_bytes) parts.push(formatSize(v.size_bytes))
  return parts.join(' · ')
}

const columns = [
  { type: 'selection' },
  { title: '歌名', key: 'song_name', ellipsis: { tooltip: true } },
  { title: '歌手', key: 'singers', ellipsis: { tooltip: true } },
  { title: '专辑', key: 'album', ellipsis: { tooltip: true } },
  {
    title: '格式',
    key: 'ext',
    width: 90,
    render(row) {
      return h(NTag, { size: 'small', type: 'info' }, { default: () => (row.ext || '-').toUpperCase() })
    },
  },
  {
    title: '大小',
    key: 'file_size',
    width: 100,
    render(row) {
      return row.file_size || row.filesize || '-'
    },
  },
  { title: '来源', key: 'source', width: 100 },
  {
    title: '曲库',
    key: 'library_match',
    width: 120,
    render(row) {
      const m = row.library_match
      if (!m) return '-'
      const tag = h(
        NTag,
        { size: 'small', type: m.status === 'exists' ? 'warning' : 'default' },
        { default: () => matchLabel(m) },
      )
      const lines = (m.versions || []).map((v) => h('div', { key: v.song_file_id }, versionText(v)))
      if (!lines.length) return tag
      return h(NTooltip, { trigger: 'hover' }, { trigger: () => tag, default: () => lines })
    },
  },
  {
    title: '操作',
    key: 'actions',
    width: 90,
    render(row) {
      return h(
        NButton,
        { size: 'tiny', tertiary: true, onClick: () => downloadOne(row) },
        { default: () => '下载' },
      )
    },
  },
]

function rowKey(row) {
  return `${row.song_name}|${row.singers}|${row.ext}|${row.album}`
}

function toggleChecked(row) {
  const key = rowKey(row)
  if (checked.value.includes(key)) {
    checked.value = checked.value.filter((k) => k !== key)
  } else {
    checked.value = [...checked.value, key]
  }
}

async function doSearch(p = page.value) {
  if (!keyword.value.trim()) {
    message.warning('请输入关键词')
    return
  }
  page.value = p
  searching.value = true
  checked.value = []
  try {
    const res = await searchMusic(keyword.value.trim(), page.value, pageSize, source.value)
    const d = res.data || {}
    results.value = d.items || []
    total.value = d.total || 0
    if (!results.value.length) message.info('没有搜索结果')
  } catch (err) {
    message.error(err.response?.data?.detail || '搜索失败')
  } finally {
    searching.value = false
  }
}

// 曲库重复决策对话框
const dupDialogVisible = ref(false)
const dupRow = ref(null)
const dupAction = ref('keep_both')
const dupReplaceId = ref(null)
let dupResolver = null

const replaceableVersions = computed(
  () => (dupRow.value?.library_match?.versions || []).filter((v) => v.replaceable),
)
const replaceOptions = computed(() =>
  replaceableVersions.value.map((v) => ({ label: versionText(v), value: v.song_file_id })),
)

function requestDupDecision(row) {
  const match = row.library_match
  if (!match) return Promise.resolve({ action: null })
  dupRow.value = row
  dupAction.value = 'keep_both'
  dupReplaceId.value = replaceableVersions.value[0]?.song_file_id ?? null
  dupDialogVisible.value = true
  return new Promise((resolve) => {
    dupResolver = resolve
  })
}

function resolveDupDialog(result) {
  dupDialogVisible.value = false
  if (dupResolver) {
    dupResolver(result)
    dupResolver = null
  }
}

function confirmDupDialog() {
  if (dupAction.value === 'replace') {
    if (!dupReplaceId.value) {
      message.warning('请选择要替换的本地版本')
      return
    }
    resolveDupDialog({ action: 'replace', songFileId: dupReplaceId.value })
    return
  }
  resolveDupDialog({ action: 'keep_both' })
}

async function createDownloadTask(it, decision) {
  const keywordText = `${it.song_name || ''} ${it.singers || ''}`.trim()
  const body = {
    keyword: keywordText,
    prefer: prefer.value,
    source: source.value,
  }
  const match = it.library_match
  if (decision?.action === 'replace' && match) {
    body.duplicate_action = 'replace'
    body.replace_song_file_id = decision.songFileId
    body.matched_song_id = match.song_id
  } else if (decision?.action === 'keep_both' && match) {
    body.duplicate_action = 'keep_both'
    body.matched_song_id = match.song_id
  }
  await api.post('/download', body)
}

async function downloadItems(items) {
  downloading.value = true
  try {
    let ok = 0
    let cancelled = 0
    for (const it of items) {
      const decision = await requestDupDecision(it)
      if (decision === null) {
        cancelled += 1
        continue
      }
      await createDownloadTask(it, decision)
      ok += 1
    }
    if (ok) message.success(`已创建 ${ok} 个下载任务`)
    if (cancelled) message.info(`已取消 ${cancelled} 首`)
    checked.value = []
  } catch (err) {
    message.error(err.response?.data?.detail || '创建下载任务失败')
  } finally {
    downloading.value = false
  }
}

function downloadOne(row) {
  downloadItems([row])
}

async function downloadSelected() {
  const items = results.value.filter((r) => checked.value.includes(rowKey(r)))
  if (!items.length) return
  await downloadItems(items)
}
</script>

<style scoped>
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.keyword-input {
  width: 320px;
}
.source-select {
  width: 150px;
}
.format-select {
  width: 140px;
}
.toolbar-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.result-card {
  border: 1px solid var(--n-border-color);
  border-radius: 12px;
  padding: 12px;
  background: color-mix(in srgb, var(--n-card-color) 92%, transparent);
}
.result-card.selected {
  border-color: color-mix(in srgb, var(--n-primary-color) 55%, var(--n-border-color));
  background: color-mix(in srgb, var(--n-primary-color) 8%, var(--n-card-color));
}
.result-main {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}
.result-meta {
  min-width: 0;
  flex: 1;
}
.result-title {
  font-weight: 600;
  line-height: 1.35;
  word-break: break-word;
}
.result-sub {
  margin-top: 4px;
  color: var(--n-text-color-3);
  font-size: 12px;
  line-height: 1.4;
  word-break: break-word;
}
.result-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
  align-items: center;
}
.row-download {
  margin-left: auto;
}
.version-list {
  margin: 0;
  padding-left: 1.2em;
  font-size: 13px;
  line-height: 1.8;
}
.version-note {
  color: var(--n-text-color-3);
  font-size: 12px;
}
@media (max-width: 768px) {
  .toolbar {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }
  .keyword-input,
  .source-select,
  .format-select {
    width: 100%;
  }
  .keyword-input {
    grid-column: 1 / -1;
  }
  .toolbar-actions {
    grid-column: 1 / -1;
  }
  .action-btn {
    flex: 1;
  }
  .pager {
    width: 100%;
  }
  .pager :deep(.n-pagination) {
    justify-content: center;
  }
}
</style>
