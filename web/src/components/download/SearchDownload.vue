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
  </n-space>
</template>

<script setup>
import { h, ref } from 'vue'
import { NTag, useMessage } from 'naive-ui'
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

async function downloadSelected() {
  const items = results.value.filter((r) => checked.value.includes(rowKey(r)))
  if (!items.length) return
  downloading.value = true
  try {
    let ok = 0
    for (const it of items) {
      const keywordText = `${it.song_name || ''} ${it.singers || ''}`.trim()
      await api.post('/download', {
        keyword: keywordText,
        prefer: prefer.value,
        source: source.value,
      })
      ok += 1
    }
    message.success(`已创建 ${ok} 个下载任务`)
    checked.value = []
  } catch (err) {
    message.error(err.response?.data?.detail || '创建下载任务失败')
  } finally {
    downloading.value = false
  }
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
