<template>
  <n-space vertical size="large" style="width: 100%" class="search-download" :class="{ mobile: isMobile }">
    <div class="toolbar">
      <n-input
        v-model:value="keyword"
        placeholder="输入歌名或歌手"
        class="keyword-input"
        @keydown.enter="doSearch(1)"
      />
      <n-select
        v-model:value="sources"
        :options="sourceOptions"
        multiple
        :max-tag-count="2"
        class="source-select"
        placeholder="选择来源"
        @update:value="ensureSourceNonEmpty"
      />
      <div class="toolbar-actions">
        <n-button type="primary" :loading="searching" class="action-btn" @click="doSearch(1)">搜索</n-button>
      </div>
    </div>

    <div v-if="searching" class="search-loading">
      <n-spin size="small" />
      <n-text depth="2">正在搜索…</n-text>
    </div>

    <n-data-table
      v-else-if="!isMobile"
      :columns="columns"
      :data="results"
      :row-key="rowKey"
    />

    <div v-else class="mobile-result-list">
      <n-empty v-if="!results.length" description="暂无搜索结果" />
      <n-space v-else vertical size="small">
        <div v-for="row in results" :key="rowKey(row)" class="result-card">
          <div class="result-meta">
            <div class="result-title">{{ row.song_name || '未知歌曲' }}</div>
            <div class="result-sub">{{ row.singers || '未知歌手' }} · {{ row.album || '未知专辑' }}</div>
            <div class="result-tags">
              <n-tag
                v-for="f in row.formats || []"
                :key="f.label || f.ext"
                size="small"
                :type="f.quality === 'lossless' ? 'success' : 'info'"
              >
                {{ f.label || formatLabel(f.ext, '-') }}
              </n-tag>
              <n-tag size="small" :bordered="false">{{ row.source || '-' }}</n-tag>
              <n-tag
                v-if="row.library_match"
                size="small"
                :type="row.library_match.status === 'exists' ? 'warning' : 'default'"
              >
                {{ matchLabel(row.library_match) }}
              </n-tag>
              <n-button size="tiny" tertiary class="row-download" @click.stop="openDownload(row)">
                下载
              </n-button>
            </div>
          </div>
        </div>
      </n-space>
    </div>

    <n-space v-if="!searching && results.length" class="pager" :justify="isMobile ? 'center' : 'end'" align="center" :wrap="true">
      <n-text depth="3">共 {{ total }} 条，当前第 {{ page }} 页</n-text>
      <n-pagination
        v-model:page="page"
        :page-size="pageSize"
        :item-count="total"
        :simple="isMobile"
        @update:page="doSearch"
      />
    </n-space>

    <!-- 下载确认：先验证可下格式，再确认入队（所见即所得） -->
    <n-modal
      v-model:show="downloadDialogVisible"
      preset="card"
      :title="`下载 - ${downloadRow?.song_name || ''}`"
      style="width: min(520px, 94vw)"
      :mask-closable="false"
    >
      <n-space vertical size="medium">
        <n-text depth="3">
          {{ downloadRow?.singers || '未知歌手' }}
          <template v-if="downloadRow?.album"> · {{ downloadRow.album }}</template>
          <template v-if="downloadRow?.duration"> · {{ downloadRow.duration }}</template>
        </n-text>

        <div v-if="resolving" class="resolve-loading">
          <n-spin size="small" />
          <n-text depth="2">正在验证可下载格式…</n-text>
        </div>

        <template v-else>
          <n-alert v-if="!resolveFormats.length" type="info" :bordered="false">
            未能在线验证到可下格式，可直接下载（下载时将自动尝试全部可用格式）
          </n-alert>
          <template v-else>
            <n-text depth="3">选择要下载的格式（可多选，每个格式各建一个下载任务）：</n-text>
            <n-checkbox-group v-model:value="selectedTiers" class="format-checks" @update:value="onTierChange">
              <n-space vertical>
                <n-checkbox v-for="f in resolveFormats" :key="f.tier" :value="f.tier">
                  {{ f.label }} · {{ formatLabel(f.ext, '-') }}
                  <span v-if="f.file_size" class="format-size">{{ f.file_size }}</span>
                  <n-tag v-if="f.via === 'third_party'" size="tiny" type="warning" :bordered="false" class="format-via">第三方解析</n-tag>
                </n-checkbox>
              </n-space>
            </n-checkbox-group>
          </template>

          <!-- 曲库重复决策（仅命中曲库时显示） -->
          <template v-if="downloadRow?.library_match">
            <n-text depth="3">
              曲库已收录
              <b>{{ downloadRow.library_match.artist || '未知歌手' }} - {{ downloadRow.library_match.title || '未知歌曲' }}</b>
              ，包含以下版本：
            </n-text>
            <ul class="version-list">
              <li v-for="v in downloadRow.library_match.versions" :key="v.song_file_id">
                {{ versionText(v) }}
                <span v-if="v.location !== 'local'" class="version-note">（远端版本暂不支持替换）</span>
                <span v-else-if="!v.replaceable" class="version-note">（文件不可访问，无法替换）</span>
              </li>
            </ul>
            <n-radio-group :value="dupAction" class="dup-actions" @update:value="onDupActionChange">
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
          </template>
        </template>
      </n-space>
      <template #footer>
        <n-space justify="end">
          <n-button @click="downloadDialogVisible = false">取消</n-button>
          <n-button
            type="primary"
            :disabled="resolving || (!!resolveFormats.length && !selectedTiers.length)"
            :loading="submitting"
            @click="confirmDownload"
          >
            {{ resolveFormats.length ? `确认下载${selectedTiers.length > 1 ? `（${selectedTiers.length} 个任务）` : ''}` : '直接下载' }}
          </n-button>
        </n-space>
      </template>
    </n-modal>
  </n-space>
</template>

<script setup>
import { computed, h, ref } from 'vue'
import { NButton, NTag, NTooltip, useMessage } from 'naive-ui'
import api from '@/api/client'
import { resolveMusicFormats, searchMusic } from '@/api/music'
import { useIsMobile } from '@/composables/useIsMobile'
import { formatFileSize } from '@/utils/format'
import { formatLabel } from '@/utils/media'

const message = useMessage()
const isMobile = useIsMobile()
const keyword = ref('')
const sources = ref(['QQMusicClient', 'NeteaseMusicClient', 'MiguMusicClient'])
const searching = ref(false)
const results = ref([])
const page = ref(1)
const pageSize = 20
const total = ref(0)
// 最近一次成功搜索的关键词：resolve 时用于后端定位该曲的搜索上下文
let lastQuery = ''

const sourceOptions = [
  { label: 'QQ 音乐', value: 'QQMusicClient' },
  { label: '网易云音乐', value: 'NeteaseMusicClient' },
  { label: '咪咕音乐', value: 'MiguMusicClient' },
]

// 多选来源不允许清空：全部取消时自动回填全部来源
function ensureSourceNonEmpty(val) {
  if (!val || !val.length) {
    sources.value = sourceOptions.map((o) => o.value)
  }
}

// 体积与格式标签的实现都在 utils/format.js / utils/media.js
function formatSize(bytes) {
  return formatFileSize(bytes, { fallback: '-' })
}

function matchLabel(match) {
  return match?.status === 'exists' ? '曲库已存在' : '疑似已存在'
}

function versionText(v) {
  const parts = [v.location === 'local' ? '本地' : '远端']
  if (v.format) parts.push(formatLabel(v.format))
  if (v.size_bytes) parts.push(formatSize(v.size_bytes))
  return parts.join(' · ')
}

function formatBadges(row) {
  const formats = row.formats || []
  if (!formats.length) return '-'
  return formats.map((f) =>
    h(
      NTag,
      { key: f.label || f.ext, size: 'small', type: f.quality === 'lossless' ? 'success' : 'info', style: 'margin-right:4px' },
      { default: () => f.label || formatLabel(f.ext, '-') },
    ),
  )
}

const columns = [
  { title: '歌名', key: 'song_name', ellipsis: { tooltip: true } },
  { title: '歌手', key: 'singers', ellipsis: { tooltip: true } },
  { title: '专辑', key: 'album', ellipsis: { tooltip: true } },
  {
    title: '可得格式',
    key: 'formats',
    width: 180,
    render(row) {
      return formatBadges(row)
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
        { size: 'tiny', tertiary: true, onClick: () => openDownload(row) },
        { default: () => '下载' },
      )
    },
  },
]

function rowKey(row) {
  return `${row.source}|${row.song_id || ''}|${row.song_name}|${row.singers}`
}

async function doSearch(p = page.value) {
  if (!keyword.value.trim()) {
    message.warning('请输入关键词')
    return
  }
  page.value = p
  searching.value = true
  results.value = []
  total.value = 0
  try {
    const res = await searchMusic(keyword.value.trim(), page.value, pageSize, sources.value.join(','))
    lastQuery = keyword.value.trim()
    results.value = res.data.items || []
    total.value = res.data.total || 0
    if (!results.value.length) message.info('没有搜索结果')
  } catch (err) {
    message.error(err.response?.data?.detail || '搜索失败')
  } finally {
    searching.value = false
  }
}

// ---- 下载确认弹窗：先验证格式，再确认入队 ----
const downloadDialogVisible = ref(false)
const downloadRow = ref(null)
const resolving = ref(false)
const resolveFormats = ref([])
const selectedTiers = ref([])
const submitting = ref(false)
const dupAction = ref('keep_both')
const dupReplaceId = ref(null)

const replaceableVersions = computed(
  () => (downloadRow.value?.library_match?.versions || []).filter((v) => v.replaceable),
)
const replaceOptions = computed(() =>
  replaceableVersions.value.map((v) => ({ label: versionText(v), value: v.song_file_id })),
)

async function openDownload(row) {
  if (!row.song_id) {
    message.error('该结果缺少歌曲 ID，无法下载')
    return
  }
  downloadRow.value = row
  resolveFormats.value = []
  selectedTiers.value = []
  dupAction.value = 'keep_both'
  dupReplaceId.value = (row.library_match?.versions || []).find((v) => v.replaceable)?.song_file_id ?? null
  downloadDialogVisible.value = true
  resolving.value = true
  try {
    const res = await resolveMusicFormats({
      q: lastQuery || keyword.value.trim(),
      source: row.source,
      song_id: row.song_id,
    })
    resolveFormats.value = res.data.formats || []
    selectedTiers.value = res.data.default_tier ? [res.data.default_tier] : []
  } catch (err) {
    // 验证失败不拦截下载：留空格式列表，用户仍可「直接下载」按原链路尝试
    resolveFormats.value = []
    selectedTiers.value = []
    message.warning(err.response?.data?.detail || '格式验证失败，可直接下载尝试')
  } finally {
    resolving.value = false
  }
}

// 「替换已有版本」只能面向一个目标文件，多格式同时替换同一文件没有意义 → 该模式下只保留最后勾选的格式
function onTierChange(val) {
  if (dupAction.value === 'replace' && val.length > 1) {
    selectedTiers.value = [val[val.length - 1]]
  }
}

function onDupActionChange(val) {
  dupAction.value = val
  if (val === 'replace' && selectedTiers.value.length > 1) {
    selectedTiers.value = selectedTiers.value.slice(0, 1)
  }
}

async function confirmDownload() {
  const row = downloadRow.value
  if (!row) return
  if (resolveFormats.value.length && !selectedTiers.value.length) {
    message.warning('请选择要下载的格式')
    return
  }
  if (row.library_match && dupAction.value === 'replace' && !dupReplaceId.value) {
    message.warning('请选择要替换的本地版本')
    return
  }
  // 有验证格式 → 每个格式一个任务；无验证格式 → 单个任务不指定格式，worker 按原链路自动尝试
  const tiers = resolveFormats.value.length ? selectedTiers.value : [null]
  const base = {
    keyword: `${row.song_name || ''} ${row.singers || ''}`.trim(),
    source: row.source,
    song_id: row.song_id,
  }
  if (row.library_match) {
    base.duplicate_action = dupAction.value
    base.matched_song_id = row.library_match.song_id
    if (dupAction.value === 'replace') base.replace_song_file_id = dupReplaceId.value
  }
  submitting.value = true
  let created = 0
  try {
    for (const tier of tiers) {
      await api.post('/download', tier ? { ...base, format: tier } : base)
      created += 1
    }
    downloadDialogVisible.value = false
    message.success(created > 1 ? `已创建 ${created} 个下载任务` : '已创建下载任务')
  } catch (err) {
    message.error(err.response?.data?.detail || '创建下载任务失败')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
}
.toolbar-actions {
  display: flex;
  gap: 10px;
  margin-left: auto;
}
.search-loading,
.resolve-loading {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 4px;
}
.result-card {
  border: 1px solid var(--sp-ui-border);
  border-radius: 10px;
  padding: 12px 14px;
  background: color-mix(in srgb, var(--sp-ui-card) 92%, transparent);
}
.result-title {
  font-weight: 600;
}
.result-sub {
  margin-top: 2px;
  font-size: 12.5px;
  opacity: 0.75;
}
.result-tags {
  margin-top: 8px;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  align-items: center;
}
.row-download {
  margin-left: auto;
}
.version-list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  line-height: 1.9;
}
.version-note {
  opacity: 0.6;
  font-size: 12px;
}
.format-size {
  opacity: 0.65;
  margin-left: 4px;
}
.format-via {
  margin-left: 4px;
}

@media (max-width: 768px) {
  .toolbar {
    flex-direction: column;
    align-items: stretch;
  }
  .keyword-input,
  .source-select {
    width: 100%;
  }
  .toolbar-actions {
    margin-left: 0;
  }
  .toolbar-actions .action-btn {
    flex: 1;
  }
}
</style>
