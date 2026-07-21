<template>
  <div class="task-detail">
    <div class="task-detail-row">
      <n-text depth="3">ID</n-text>
      <n-text>#{{ task.id }}</n-text>
    </div>
    <div class="task-detail-row">
      <n-text depth="3">{{ isTerminal ? '结束于' : '最后心跳' }}</n-text>
      <n-text :type="heartbeatStale ? 'warning' : 'default'">
        {{ formatTime(task.updated_at) }}
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
    <div v-if="logs.length" class="task-detail-logs">
      <n-text depth="3">运行日志（{{ logs.length }} 条）</n-text>
      <div class="task-detail-log-list">
        <div v-for="(log, i) in logs" :key="i" class="task-detail-log-line">
          <span class="task-detail-log-time">{{ logTime(log.t) }}</span>
          <span>{{ log.m }}</span>
        </div>
      </div>
    </div>
    <n-text v-else depth="3" style="font-size: 12px">暂无运行日志</n-text>
  </div>
</template>

<script setup>
import { computed } from 'vue'

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
  const ms = heartbeatMs.value
  if (ms == null) return ''
  const sec = Math.round(ms / 1000)
  if (sec < 60) return `${sec} 秒前`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min} 分钟前`
  const h = Math.floor(min / 60)
  return `${h} 小时 ${min % 60} 分钟前`
})

function formatTime(value) {
  if (!value) return '-'
  try {
    return new Date(value).toLocaleString('zh-CN', {
      month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit',
    })
  } catch { return '-' }
}

function logTime(value) {
  if (!value) return ''
  try {
    return new Date(value).toLocaleTimeString('zh-CN', { hour12: false })
  } catch { return '' }
}
</script>

<style scoped>
.task-detail {
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--action-color, rgba(127, 127, 127, 0.08));
  font-size: 12px;
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
