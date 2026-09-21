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
      <n-select v-model:value="prefer" :options="formatOptions" class="format-select" />
      <n-select v-model:value="dupAction" :options="dupOptions" class="dup-select" />
      <n-button type="primary" class="start-btn" :loading="loading" @click="start">开始批量下载</n-button>
    </div>
    <n-text v-if="lineCount.raw" depth="3" class="line-count">
      共 {{ lineCount.raw }} 行，去重后 {{ lineCount.unique }} 首
    </n-text>
    <source-picker v-model:value="sources" :options="downloadSources" />
  </n-space>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import api from '@/api/client'
import SourcePicker from '@/components/download/SourcePicker.vue'
import { useIsMobile } from '@/composables/useIsMobile'
import { countBatchLines } from '@/utils/batchText'
import { DUPLICATE_ACTION_OPTIONS, FORMAT_PREFER_OPTIONS } from '@/utils/downloadOptions'
import { DOWNLOAD_SOURCES, loadSourcePref, saveSourcePref } from '@/utils/downloadSources'

const message = useMessage()
const isMobile = useIsMobile()
const text = ref('')
const prefer = ref('any')
const dupAction = ref('skip')
const downloadSources = DOWNLOAD_SOURCES
const sources = ref(loadSourcePref())
watch(sources, (val) => saveSourcePref(val), { deep: true })
const loading = ref(false)

const lineCount = computed(() => countBatchLines(text.value))

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

async function start() {
  if (!text.value.trim()) {
    message.warning('请先粘贴歌单')
    return
  }
  if (!sources.value.length) {
    message.warning('请至少选择一个来源')
    return
  }
  loading.value = true
  try {
    await api.post('/download/batch', {
      content: text.value,
      prefer: prefer.value,
      source: sources.value.join(','),
      duplicate_action: dupAction.value,
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
.format-select {
  width: 140px;
}
.dup-select {
  width: 160px;
}
.line-count {
  font-size: var(--sp-fs-caption);
}
@media (max-width: 768px) {
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
