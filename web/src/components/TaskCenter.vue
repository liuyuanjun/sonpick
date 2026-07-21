<template>
  <n-badge :value="activeTasks.length" :max="99" :show="activeTasks.length > 0" type="info">
    <n-button quaternary circle aria-label="任务中心" @click="openDrawer">
      <template #icon>
        <n-icon :class="{ 'task-spin': runningTasks.length > 0 }">
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
          <n-text strong class="task-section-title">进行中（{{ runningTasks.length }}）</n-text>
          <n-empty v-if="!runningTasks.length" description="暂无进行中的任务" size="small" style="margin: 12px 0" />
          <div v-for="task in runningTasks" :key="task.id" class="task-item">
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
              :processing="task.status === 'running'"
              style="margin: 6px 0 4px"
            />
            <div class="task-item-foot">
              <n-text depth="3" class="task-message" :title="taskMessage(task)">
                {{ taskMessage(task) || '等待执行' }} · 已耗时 {{ elapsedText(task) }}
              </n-text>
              <n-button size="tiny" quaternary @click="toggleDetail(task.id)">
                {{ expandedIds.has(task.id) ? '收起' : '详情' }}
              </n-button>
            </div>
            <task-detail v-if="expandedIds.has(task.id)" :task="task" :now="now" />
          </div>
        </div>

        <div>
          <n-text strong class="task-section-title">排队中（{{ pendingTasks.length }}）</n-text>
          <n-empty v-if="!pendingTasks.length" description="暂无排队中的任务" size="small" style="margin: 12px 0" />
          <div v-for="task in pendingTasks" :key="task.id" class="task-item">
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
              :show-indicator="false"
              :processing="false"
              style="margin: 6px 0 4px"
            />
            <div class="task-item-foot">
              <n-text depth="3" class="task-message" :title="taskMessage(task)">
                {{ taskMessage(task) || '等待前序任务完成' }} · 已排队 {{ elapsedText(task) }}
              </n-text>
              <n-button size="tiny" quaternary @click="toggleDetail(task.id)">
                {{ expandedIds.has(task.id) ? '收起' : '详情' }}
              </n-button>
            </div>
            <task-detail v-if="expandedIds.has(task.id)" :task="task" :now="now" />
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
            <div class="task-item-foot">
              <n-text depth="3" class="task-message" :title="taskMessage(task)">
                {{ taskMessage(task) || task.error_message || '-' }} · 耗时 {{ elapsedText(task) }} · {{ formatTime(task.updated_at) }}
              </n-text>
              <n-button size="tiny" quaternary @click="toggleDetail(task.id)">
                {{ expandedIds.has(task.id) ? '收起' : '详情' }}
              </n-button>
            </div>
            <task-detail v-if="expandedIds.has(task.id)" :task="task" :now="now" />
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
import TaskDetail from '@/components/TaskDetail.vue'

const message = useMessage()
const show = ref(false)
const loading = ref(false)
const tasks = ref([])
const now = ref(Date.now())
const expandedIds = ref(new Set())

function toggleDetail(id) {
  const next = new Set(expandedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedIds.value = next
}

const TERMINAL_STATUSES = ['completed', 'failed', 'cancelled']

const pendingTasks = computed(() => tasks.value.filter((t) => t.status === 'pending'))
const runningTasks = computed(() => tasks.value.filter((t) => t.status === 'running'))
const activeTasks = computed(() => [...runningTasks.value, ...pendingTasks.value])
const recentTasks = computed(() => tasks.value.filter((t) => TERMINAL_STATUSES.includes(t.status)).slice(0, 15))

const TYPE_LABELS = {
  search_download: '搜索下载',
  batch_download: '批量下载',
  scrape: '刮削',
  convert: '转码',
  scan: '扫描',
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
  if (task.type === 'scan') return `扫描曲库 #${payload.source_ids?.[0] ?? task.id}`
  if (task.type === 'convert') return `转码歌曲 #${payload.song_id ?? task.id}`
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
function elapsedText(task) {
  if (!task?.created_at) return '-'
  const start = new Date(task.created_at).getTime()
  if (Number.isNaN(start)) return '-'
  const end = TERMINAL_STATUSES.includes(task.status) && task.updated_at
    ? new Date(task.updated_at).getTime()
    : now.value
  const sec = Math.max(0, Math.round((end - start) / 1000))
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  if (h) return `${h}时${m}分${s}秒`
  if (m) return `${m}分${s}秒`
  return `${s}秒`
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

const _notifiedTaskIds = new Set()

useWebSocket((data) => {
  if (data?.type === 'task_progress') {
    upsertTask({
      id: data.task_id,
      status: data.status,
      progress: data.progress || { message: data.message, percent: data.percent },
    })
  } else if (data?.type === 'task_update') {
    upsertTask({ id: data.task_id, status: data.status })
    // 终态 toast（每条任务只弹一次）
    const terminalStatus = data.status
    const taskKey = `${data.task_id}_${terminalStatus}`
    if (['completed', 'failed', 'cancelled'].includes(terminalStatus) && !_notifiedTaskIds.has(taskKey)) {
      _notifiedTaskIds.add(taskKey)
      const task = tasks.value.find(t => t.id === data.task_id)
      const taskName = task ? taskTitle(task) : `#${data.task_id}`
      const taskMsg = task?.progress?.message || ''
      if (terminalStatus === 'completed') {
        message.success(`${taskName} 完成${taskMsg ? '：' + taskMsg : ''}`)
      } else if (terminalStatus === 'failed') {
        message.error(`${taskName} 失败${taskMsg ? '：' + taskMsg : ''}`, { duration: 6000 })
      } else if (terminalStatus === 'cancelled') {
        message.warning(`${taskName} 已取消`)
      }
    }
  }
})

// 抽屉打开时每 10s 兜底刷新一次（WS 为主，避免高频轮询）；每秒刷新已耗时显示
let pollTimer = null
let tickTimer = null
watch(show, (visible) => {
  if (visible) {
    pollTimer = setInterval(loadTasks, 10000)
    tickTimer = setInterval(() => { now.value = Date.now() }, 1000)
  } else {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
    if (tickTimer) { clearInterval(tickTimer); tickTimer = null }
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
  flex: 1;
  min-width: 0;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.task-item-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.task-spin {
  animation: task-rotate 1.6s linear infinite;
}
@keyframes task-rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
