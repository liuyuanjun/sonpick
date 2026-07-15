<template>
  <n-space vertical size="large" style="width: 100%">
    <n-alert type="info" :bordered="false">
      每行一首，推荐格式：歌名 - 歌手。也可只写歌名。
    </n-alert>
    <n-input
      v-model:value="text"
      type="textarea"
      :rows="12"
      placeholder="例如：&#10;晴天 - 周杰伦&#10;海阔天空 - Beyond"
    />
    <n-space>
      <n-select v-model:value="prefer" :options="formatOptions" style="width: 140px" />
      <n-button type="primary" :loading="loading" @click="start">开始批量下载</n-button>
    </n-space>
  </n-space>
</template>

<script setup>
import { ref } from 'vue'
import { useMessage } from 'naive-ui'
import api from '@/api/client'

const message = useMessage()
const text = ref('')
const prefer = ref('any')
const loading = ref(false)

const formatOptions = [
  { label: '任意', value: 'any' },
  { label: 'FLAC', value: 'flac' },
  { label: 'MP3', value: 'mp3' },
  { label: 'M4A', value: 'm4a' },
]

async function start() {
  if (!text.value.trim()) {
    message.warning('请先粘贴歌单')
    return
  }
  loading.value = true
  try {
    await api.post('/download/batch', {
      content: text.value,
      prefer: prefer.value,
    })
    message.success('已创建批量下载任务')
  } catch (err) {
    message.error(err.response?.data?.detail || '导入下载失败')
  } finally {
    loading.value = false
  }
}
</script>
