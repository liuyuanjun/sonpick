<template>
  <n-space vertical size="large" style="width: 100%">
    <n-card title="操作日志">
      <n-space vertical size="medium">
        <n-space wrap>
          <n-select
            v-model:value="filters.action"
            clearable
            placeholder="操作类型"
            style="width: 140px"
            :options="actionOptions"
          />
          <n-select
            v-model:value="filters.status"
            clearable
            placeholder="状态"
            style="width: 140px"
            :options="statusOptions"
          />
          <n-input
            v-model:value="filters.q"
            clearable
            placeholder="搜索标题/路径/说明"
            style="width: 260px"
            @keyup.enter="load"
          />
          <n-button type="primary" :loading="loading" @click="load">查询</n-button>
          <n-button @click="resetFilters">重置</n-button>
          <n-button type="error" secondary :loading="clearing" @click="clearAll">清空日志</n-button>
        </n-space>

        <n-data-table
          :columns="columns"
          :data="rows"
          :loading="loading"
          :bordered="false"
          :single-line="false"
          size="small"
        />
      </n-space>
    </n-card>
  </n-space>
</template>

<script setup>
import { h, onMounted, reactive, ref } from 'vue'
import { NTag, NText, useDialog, useMessage } from 'naive-ui'
import api from '@/api/client'

const message = useMessage()
const dialog = useDialog()
const loading = ref(false)
const clearing = ref(false)
const rows = ref([])
const filters = reactive({
  action: null,
  status: null,
  q: '',
})

const actionOptions = [
  { label: '下载', value: 'download' },
  { label: '上传', value: 'upload' },
  { label: '删除', value: 'delete' },
  { label: '转码', value: 'convert' },
]

const statusOptions = [
  { label: '成功', value: 'success' },
  { label: '失败', value: 'failed' },
  { label: '跳过', value: 'skipped' },
  { label: '部分成功', value: 'partial' },
]

const actionLabel = {
  download: '下载',
  upload: '上传',
  delete: '删除',
  convert: '转码',
}

const statusType = {
  success: 'success',
  failed: 'error',
  skipped: 'warning',
  partial: 'info',
  renamed: 'info',
}

const columns = [
  {
    title: '时间',
    key: 'created_at',
    width: 180,
    render: (row) => formatTime(row.created_at),
  },
  {
    title: '操作',
    key: 'action',
    width: 90,
    render: (row) =>
      h(
        NTag,
        { size: 'small', bordered: false, type: 'default' },
        { default: () => actionLabel[row.action] || row.action },
      ),
  },
  {
    title: '状态',
    key: 'status',
    width: 100,
    render: (row) =>
      h(
        NTag,
        { size: 'small', bordered: false, type: statusType[row.status] || 'default' },
        { default: () => row.status },
      ),
  },
  {
    title: '标题',
    key: 'title',
    ellipsis: { tooltip: true },
  },
  {
    title: '说明',
    key: 'message',
    ellipsis: { tooltip: true },
  },
  {
    title: '本地路径',
    key: 'local_path',
    ellipsis: { tooltip: true },
    render: (row) => row.local_path || '—',
  },
  {
    title: '远程路径',
    key: 'remote_path',
    ellipsis: { tooltip: true },
    render: (row) => row.remote_path || '—',
  },
  {
    title: '任务',
    key: 'task_id',
    width: 80,
    render: (row) => (row.task_id != null ? `#${row.task_id}` : '—'),
  },
]

function formatTime(v) {
  if (!v) return '—'
  try {
    return new Date(v).toLocaleString()
  } catch {
    return v
  }
}

async function load() {
  loading.value = true
  try {
    const res = await api.get('/logs', {
      params: {
        action: filters.action || undefined,
        status: filters.status || undefined,
        q: filters.q || undefined,
        limit: 200,
      },
    })
    rows.value = res.data || []
  } catch (err) {
    message.error(err.response?.data?.detail || '加载日志失败')
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  filters.action = null
  filters.status = null
  filters.q = ''
  load()
}

function clearAll() {
  dialog.warning({
    title: '清空操作日志',
    content: '确定清空全部操作日志？此操作不可恢复。',
    positiveText: '清空',
    negativeText: '取消',
    onPositiveClick: async () => {
      clearing.value = true
      try {
        const res = await api.delete('/logs')
        message.success(`已删除 ${res.data?.deleted ?? 0} 条`)
        await load()
      } catch (err) {
        message.error(err.response?.data?.detail || '清空失败')
      } finally {
        clearing.value = false
      }
    },
  })
}

onMounted(load)
</script>
