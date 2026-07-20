<template>
  <n-badge :value="activeTasks.length" :max="99" :show="activeTasks.length > 0" type="info">
    <n-button quaternary circle aria-label="任务中心" @click="openDrawer">
      <template #icon>
        <n-icon :class="{ 'task-spin': activeTasks.length > 0 }">
          <SyncOutline v-if="activeTasks.length > 0" />
          <ListOutline v-else />
        </n-icon>
      </template>
    </n-button>
  </n-badge>

  <n-drawer v-model:show="show" placement="right" :width="420">
    <n-drawer-content closable>
      <template #header>
        <n-space align="center" justify="space-between" style="width: 100%">
          <span>任务中心</span>
          <n-button size="tiny" quaternary :loading="loading" @click="loadTasks">刷新</n-button>
        </n-space>
      </template>

      <n-space vertical size="large">
        <div>
          <n-text strong class="task-section-title">进行中（{{ activeTasks.length }}）</n-text>
          <n-empty v-if="!activeTasks.length" description="暂无进行中的任务" size="small" style="margin: 12px 0" />
          <div v-for="task in activeTasks" :key="task.id" class="task-item">
            <div class="task-item-head">
              <n-space size="small" align="center" style="min-width: 0">
                <n-tag size="small" type="info" :bordered="false">{{ typeLabel(task.type) }}</n-tag>
                <span class="task-title" :title="taskTitle(task)">{{ taskTitle(task) }}</span>
              </n-space>
              <n-space size="small" align="center">
                <n-tag size="small" :type="statusTagType(task.status)" :bordered="false">{{ statusLabel(task.status) }}</n-tag>
                <n-button size="tiny" quaternary circle aria-label="取消任务" @click="onCancel(task)">
                  <template #icon><n-icon><CloseOutline /></n-icon></template>
                </n-button>
              </n-space>
            </div>
            <n-progress
              type="line"
              :percentage="taskPercent(task)"
              :status="task.status === 'failed' ? 'error' : 'default'"
              :show-indicator="false"
              processing
              style="margin: 6px 0 4px"
            />
            <n-text depth="3" class="task-message" :title="taskMessage(task)">{{ taskMessage(task) || '等待执行' }}</n-text>
          </div>
        </div>

        <div>
          <n-text strong class="task-section-title">最近任务</n-text>
          <n-empty v-if="!recentTasks.length" description="暂无历史任务" size="small" style="margin: 12px 0" />
          <div v-for="task in recentTasks" :key="task.id" class="task-item">
            <div class="task-item-head">
              <n-space size="small" align="center" style="min-width: 0">
                <n-tag size="small" :bordered="false">{{ typeLabel(task.type) }}</n-tag>
                <span class="task-title" :title="taskTitle(task)">{{ taskTitle(task) }}</span>
              </n-space>
              <n-tag size="small" :type="statusTagType(task.status)" :bordered="false">{{ statusLabel(task.status) }}</n-tag>
            </div>
            <n-text depth="3" class="task-message" :title="taskMessage(task)">
              {{ taskMessage(task) || task.error_message || '-' }} · {{ formatTime(task.updated_at) }}
            </n-text>
          </div>
        </div>
      </n-space>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { CloseOutline, ListOutline, SyncOutline } from '@vicons/ionicons5'
import { cancelTask, listTasks } from '@/api/music'
import { useWebSocket } from '@/composables/useWebSocket'

const message = useMessage()
const show = ref(false)
const loading = ref(false)
const tasks = ref([])

const ACTIVE_STATUSES = ['pending', 'running']
const TERMINAL_STATUSES = ['completed', 'failed', 'cancelled']

const activeTasks = computed(() => tasks.value.filter((t) => ACTIVE_STATUSES.includes(t.status)))
const recentTasks = computed(() => tasks.value.filter((t) => TERMINAL_STATUSES.includes(t.status)).slice(0, 15))

const TYPE_LABELS = {
  search_download: '搜索下载',
  batch_download: '批量下载',
  scrape: '刮削',
}
const STATUS_LABELS = {
  pending: '排队中',
  running: '进行中',
  completed: '完成',
  failed: '失败',
  cancelled: '已取消',
}
const STATUS_TAG_TYPES = {
  pending: 'default',
  running: 'info',
  completed: 'success',
  failed: 'error',
  cancelled: 'warning',
}

function typeLabel(type) { return TYPE_LABELS[type] || type || '任务' }
function statusLabel(status) { return STATUS_LABELS[status] || status || '-' }
function statusTagType(status) { return STATUS_TAG_TYPES[status] || 'default' }
function taskTitle(task) {
  const payload = task.payload || {}
  if (task.type === 'search_download') return payload.keyword || `任务 #${task.id}`
  if (task.type === 'batch_download') {
    const kws = payload.keywords || []
    return kws.length ? `批量下载 ${kws.length} 首：${kws[0]}${kws.length > 1 ? ' 等' : ''}` : `批量下载 #${task.id}`
  }
  if (task.type === 'scrape') return `刮削曲库 #${payload.source_id ?? task.id}`
  return `任务 #${task.id}`
}
function taskPercent(task) {
  const p = Number(task.progress?.percent || 0)
  return Math.max(0, Math.min(100, Math.round(p)))
}
function taskMessage(task) {
  return task.progress?.message || ''
}
function formatTime(value) {
  if (!value) return ''
  try {
    return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  } catch { return '' }
}

function upsertTask(partial) {
  if (!partial || partial.id == null) return
  const clean = Object.fromEntries(Object.entries(partial).filter(([, v]) => v !== undefined && v !== null))
  const idx = tasks.value.findIndex((t) => t.id === clean.id)
  if (idx >= 0) {
    const prev = tasks.value[idx]
    tasks.value.splice(idx, 1, {
      ...prev,
      ...clean,
      progress: { ...(prev.progress || {}), ...(clean.progress || {}) },
    })
  } else {
    // 新任务（WS 先于列表刷新到达）：拉全量
    loadTasks()
  }
  // 按 id 倒序
  tasks.value.sort((a, b) => b.id - a.id)
}

async function loadTasks() {
  loading.value = true
  try {
    const res = await listTasks()
    tasks.value = res.data || []
  } catch {
    // 静默：WS 仍可更新
  } finally {
    loading.value = false
  }
}

function openDrawer() {
  show.value = true
  loadTasks()
}

async function onCancel(task) {
  try {
    await cancelTask(task.id)
    upsertTask({ id: task.id, status: 'cancelled' })
    message.success(`已取消任务 #${task.id}`)
  } catch (err) {
    message.error(err.response?.data?.detail || '取消失败')
  }
}

useWebSocket((data) => {
  if (data?.type === 'task_progress') {
    upsertTask({
      id: data.task_id,
      status: data.status,
      progress: data.progress || { message: data.message, percent: data.percent },
    })
  } else if (data?.type === 'task_update') {
    upsertTask({ id: data.task_id, status: data.status })
  }
})

// 抽屉打开时每 10s 兜底刷新一次（WS 为主，避免高频轮询）
let pollTimer = null
watch(show, (visible) => {
  if (visible) {
    pollTimer = setInterval(loadTasks, 10000)
  } else if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
})

loadTasks()
</script>

<style scoped>
.task-section-title {
  display: block;
  margin-bottom: 8px;
}
.task-item {
  padding: 10px 12px;
  margin-bottom: 8px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
}
.task-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.task-title {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.task-message {
  display: block;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.task-spin {
  animation: task-rotate 1.6s linear infinite;
}
@keyframes task-rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
