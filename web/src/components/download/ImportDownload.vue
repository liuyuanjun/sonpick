<template>
  <n-space vertical size="large" style="width: 100%" class="import-download" :class="{ mobile: isMobile }">
    <n-alert type="info" :bordered="false">
      每行一首，推荐格式：歌名 - 歌手。也可只写歌名。
    </n-alert>
    <n-input
      v-model:value="text"
      type="textarea"
      :rows="isMobile ? 10 : 12"
      placeholder="例如：&#10;晴天 - 周杰伦&#10;海阔天空 - Beyond"
    />
    <div class="import-toolbar">
      <n-select v-model:value="source" :options="sourceOptions" class="source-select" />
      <n-select v-model:value="prefer" :options="formatOptions" class="format-select" />
      <n-button type="primary" class="start-btn" :loading="loading" @click="start">开始批量下载</n-button>
    </div>
  </n-space>
</template>

<script setup>
import { ref } from 'vue'
import { useMessage } from 'naive-ui'
import api from '@/api/client'
import { useIsMobile } from '@/composables/useIsMobile'

const message = useMessage()
const isMobile = useIsMobile()
const text = ref('')
const prefer = ref('any')
const source = ref('QQMusicClient')
const loading = ref(false)

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
      source: source.value,
    })
    message.success('已创建批量下载任务')
  } catch (err) {
    message.error(err.response?.data?.detail || '导入下载失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.import-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.source-select {
  width: 150px;
}
.format-select {
  width: 140px;
}
@media (max-width: 768px) {
  .import-toolbar {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }
  .source-select,
  .format-select,
  .start-btn {
    width: 100%;
  }
  .start-btn {
    grid-column: 1 / -1;
  }
}
</style>
