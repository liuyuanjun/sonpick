<template>
  <n-space vertical size="large" style="width: 100%">
    <n-card title="搜索歌曲">
      <n-space>
        <n-input v-model:value="keyword" placeholder="输入歌名或歌手" style="width: 320px" @keydown.enter="search" />
        <n-select v-model:value="prefer" :options="formatOptions" style="width: 140px" />
        <n-button type="primary" :loading="searching" @click="search">搜索</n-button>
      </n-space>
    </n-card>

    <n-card title="搜索结果" v-if="results.length">
      <n-data-table
        :columns="columns"
        :data="results"
        :row-key="rowKey"
        v-model:checked-row-keys="checkedKeys"
        @update:checked-row-keys="handleCheck"
      />
      <n-space style="margin-top: 16px">
        <n-button type="primary" :loading="submitting" :disabled="!checkedKeys.length" @click="downloadSelected">
          下载选中 ({{ checkedKeys.length }})
        </n-button>
      </n-space>
    </n-card>
  </n-space>
</template>

<script setup>
import { ref } from 'vue'
import { useMessage } from 'naive-ui'
import api from '@/api/client'

const keyword = ref('')
const prefer = ref('any')
const searching = ref(false)
const submitting = ref(false)
const results = ref([])
const checkedKeys = ref([])
const message = useMessage()

const formatOptions = [
  { label: '任意格式', value: 'any' },
  { label: 'FLAC 优先', value: 'flac' },
  { label: 'MP3/M4A 优先', value: 'mp3' },
]

const columns = [
  { type: 'selection' },
  { title: '歌名', key: 'song_name' },
  { title: '歌手', key: 'singers' },
  { title: '专辑', key: 'album' },
  { title: '格式', key: 'ext' },
  { title: '大小', key: 'file_size' },
  { title: '时长', key: 'duration' },
]

function rowKey(row) {
  return row.song_name + '|' + row.singers + '|' + row.ext
}

async function search() {
  if (!keyword.value.trim()) return
  searching.value = true
  try {
    const res = await api.get('/search', { params: { q: keyword.value } })
    results.value = res.data
    checkedKeys.value = []
  } catch (err) {
    message.error(err.response?.data?.detail || '搜索失败')
  } finally {
    searching.value = false
  }
}

async function downloadSelected() {
  const selected = results.value.filter(r => checkedKeys.value.includes(rowKey(r)))
  if (!selected.length) return
  submitting.value = true
  try {
    for (const item of selected) {
      await api.post('/download', {
        keyword: `${item.song_name} - ${item.singers || ''}`.trim(),
        prefer: prefer.value,
      })
    }
    message.success('已加入下载队列')
    checkedKeys.value = []
  } catch (err) {
    message.error(err.response?.data?.detail || '下载失败')
  } finally {
    submitting.value = false
  }
}

function handleCheck(keys) {
  checkedKeys.value = keys
}
</script>
