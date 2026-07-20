<template>
  <n-space vertical size="large" style="width: 100%">
    <n-space>
      <n-input
        v-model:value="keyword"
        placeholder="输入歌名或歌手"
        style="width: 320px"
        @keydown.enter="doSearch(1)"
      />
      <n-select v-model:value="source" :options="sourceOptions" style="width: 150px" />
      <n-select v-model:value="prefer" :options="formatOptions" style="width: 140px" />
      <n-button type="primary" :loading="searching" @click="doSearch(1)">搜索</n-button>
      <n-button
        type="success"
        :disabled="!checked.length"
        :loading="downloading"
        @click="downloadSelected"
      >
        下载选中 ({{ checked.length }})
      </n-button>
    </n-space>

    <n-data-table
      :columns="columns"
      :data="results"
      :row-key="rowKey"
      :loading="searching"
      :checked-row-keys="checked"
      @update:checked-row-keys="checked = $event"
    />

    <n-space justify="end" align="center">
      <n-text depth="3">共 {{ total }} 条（每源约 10 条），当前第 {{ page }} 页</n-text>
      <n-pagination
        v-model:page="page"
        :page-size="pageSize"
        :item-count="total"
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

const message = useMessage()
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
