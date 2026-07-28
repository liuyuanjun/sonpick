<template>
  <n-modal :show="show" preset="card" title="批量获取歌词" style="width: 560px; max-width: 94vw" @update:show="emit('update:show', $event)">
    <n-space vertical size="large">
      <n-alert type="info" :show-icon="false">{{ targetLabel }}。任务创建后将在任务中心后台严格串行执行。</n-alert>
      <n-form label-placement="left" label-width="120">
        <n-form-item label="处理方式">
          <n-radio-group v-model:value="mode">
            <n-radio value="missing">仅补缺失歌词</n-radio>
            <n-radio value="overwrite">覆盖已有歌词</n-radio>
          </n-radio-group>
        </n-form-item>
        <n-form-item label="歌词源">
          <n-select v-model:value="lyricsSource" :options="sourceOptions" :loading="loadingSources" />
        </n-form-item>
        <n-form-item label="音频标签">
          <n-checkbox v-model:checked="writeFileTags">同时写入音频内嵌歌词</n-checkbox>
        </n-form-item>
      </n-form>
      <n-alert v-if="mode === 'overwrite'" type="warning" :show-icon="false">已有歌词将被覆盖，请确认目标范围。</n-alert>
      <n-space justify="end">
        <n-button @click="emit('update:show', false)">取消</n-button>
        <n-button type="primary" :loading="submitting" @click="submit">创建歌词任务</n-button>
      </n-space>
    </n-space>
  </n-modal>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useMessage } from 'naive-ui'
import api from '@/api/client'
import { lyricsSongs } from '@/api/music'

const props = defineProps({
  show: { type: Boolean, default: false },
  songIds: { type: Array, default: () => [] },
  librarySourceId: { type: Number, default: null },
  targetLabel: { type: String, default: '当前范围' },
})
const emit = defineEmits(['update:show', 'created'])
const message = useMessage()
const mode = ref('missing')
const lyricsSource = ref('auto')
const writeFileTags = ref(true)
const sourceOptions = ref([{ label: '自动选择歌词源', value: 'auto' }])
const loadingSources = ref(false)
const submitting = ref(false)

async function loadSources() {
  loadingSources.value = true
  try {
    const response = await api.get('/settings')
    const data = response.data || response || {}
    sourceOptions.value = [
      { label: '自动选择歌词源', value: 'auto' },
      ...(data.lyrics_sources || []).filter(item => item.enabled).map(item => ({ label: item.name, value: item.id })),
    ]
  } catch {
    sourceOptions.value = [{ label: '自动选择歌词源', value: 'auto' }]
  } finally {
    loadingSources.value = false
  }
}

async function submit() {
  submitting.value = true
  try {
    const response = await lyricsSongs({
      song_ids: props.songIds.length ? [...props.songIds] : null,
      library_source_id: props.librarySourceId,
      source_id: lyricsSource.value,
      only_missing: mode.value === 'missing',
      overwrite: mode.value === 'overwrite',
      write_file_tags: writeFileTags.value,
    })
    const data = response.data || response || {}
    message.success(`歌词任务 #${data.task_id} 已创建，请在任务中心查看`)
    emit('created', data)
    emit('update:show', false)
  } catch (error) {
    const detail = error.response?.data?.detail
    message.error(detail?.message || detail || error.message || '创建歌词任务失败')
  } finally {
    submitting.value = false
  }
}

onMounted(loadSources)
</script>
