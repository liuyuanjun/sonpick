<template>
  <div class="task-detail">
    <div class="task-detail-row">
      <n-text depth="3">ID</n-text>
      <n-text>#{{ task.id }}</n-text>
    </div>
    <div class="task-detail-row">
      <n-text depth="3">添加于</n-text>
      <n-text>{{ formatDateTime(task.created_at, { fallback: '-' }) }}</n-text>
    </div>
    <div v-if="task.started_at" class="task-detail-row">
      <n-text depth="3">开始于</n-text>
      <n-text>{{ formatDateTime(task.started_at, { fallback: '-' }) }}</n-text>
    </div>
    <div class="task-detail-row">
      <n-text depth="3">{{ isTerminal ? '结束于' : '最后心跳' }}</n-text>
      <n-text :type="heartbeatStale ? 'warning' : 'default'">
        {{ formatDateTime(task.updated_at, { fallback: '-' }) }}
        <template v-if="!isTerminal">（{{ heartbeatText }}）</template>
      </n-text>
    </div>
    <div v-if="task.error_message" class="task-detail-row">
      <n-text depth="3">错误</n-text>
      <n-text type="error" class="task-detail-pre">{{ task.error_message }}</n-text>
    </div>
    <div v-if="resultMessage" class="task-detail-row">
      <n-text depth="3">结果</n-text>
      <n-text :type="task.status === 'failed' ? 'error' : 'success'" class="task-detail-pre">
        {{ resultMessage }}
      </n-text>
    </div>
    <div v-if="lyricsStats" class="task-detail-row">
      <n-text depth="3">歌词统计</n-text>
      <n-text class="task-detail-pre">{{ lyricsStats }}</n-text>
    </div>
    <div v-if="logs.length" class="task-detail-logs">
      <n-text depth="3">运行日志（{{ logs.length }} 条）</n-text>
      <div class="task-detail-log-list">
        <div v-for="(log, i) in logs" :key="i" class="task-detail-log-line">
          <span class="task-detail-log-time">{{ formatTimeOfDay(log.t) }}</span>
          <span>{{ log.m }}</span>
        </div>
      </div>
    </div>
    <n-text v-else depth="3" style="font-size: var(--sp-fs-caption)">暂无运行日志</n-text>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { formatDateTime, formatRelativeTime, formatTimeOfDay } from '@/utils/format'

const props = defineProps({
  task: { type: Object, required: true },
  now: { type: Number, default: () => Date.now() },
})

const TERMINAL = ['completed', 'failed', 'cancelled']

const isTerminal = computed(() => TERMINAL.includes(props.task.status))

const logs = computed(() => {
  const list = props.task.progress?.logs
  return Array.isArray(list) ? list.slice(-30) : []
})

const resultMessage = computed(() => {
  const r = props.task.result
  if (!r || typeof r !== 'object') return ''
  return r.message || ''
})

const lyricsStats = computed(() => {
  if (props.task.type !== 'lyrics') return ''
  const r = props.task.result || {}
  if (r.total == null) return ''
  return `总数 ${r.total} · 已处理 ${r.processed || 0} · 匹配 ${r.matched || 0} · 写入 ${r.written || 0} · 纯音乐 ${r.instrumental || 0} · 跳过已有 ${r.skipped_existing || 0} · 未命中 ${r.not_found || 0} · 限流等待 ${r.rate_limit_waits || 0} · 失败 ${r.failed || 0}`
})

const heartbeatMs = computed(() => {
  if (!props.task.updated_at) return null
  const t = new Date(props.task.updated_at).getTime()
  if (Number.isNaN(t)) return null
  return Math.max(0, props.now - t)
})

// 运行中任务超过 2 分钟没有心跳视为可疑（可能已卡死）
const heartbeatStale = computed(
  () => !isTerminal.value && heartbeatMs.value != null && heartbeatMs.value > 120000
)

const heartbeatText = computed(() => {
  const sec = heartbeatMs.value == null ? null : Math.round(heartbeatMs.value / 1000)
  return formatRelativeTime(sec)
})

</script>

<style scoped>
.task-detail {
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: var(--sp-radius-sm);
  background: var(--action-color, rgba(127, 127, 127, 0.08));
  font-size: var(--sp-fs-caption);
}
.task-detail-row {
  display: flex;
  gap: 8px;
  margin-bottom: 4px;
  align-items: baseline;
}
.task-detail-row > :first-child {
  flex-shrink: 0;
  min-width: 56px;
}
.task-detail-pre {
  white-space: pre-wrap;
  word-break: break-all;
}
.task-detail-logs {
  margin-top: 6px;
}
.task-detail-log-list {
  margin-top: 4px;
  max-height: 180px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.task-detail-log-line {
  display: flex;
  gap: 8px;
  line-height: 1.5;
  word-break: break-all;
}
.task-detail-log-time {
  flex-shrink: 0;
  opacity: 0.5;
  font-variant-numeric: tabular-nums;
}
</style>
