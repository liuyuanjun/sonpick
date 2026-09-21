<template>
  <n-space vertical size="large" style="width: 100%" class="logs-page" :class="{ mobile: isMobile }">
    <n-card :title="isMobile ? undefined : '操作日志'" class="logs-card">
      <n-space vertical size="medium">
        <div class="filters">
          <n-select
            v-model:value="filters.action"
            clearable
            placeholder="操作类型"
            class="filter-action"
            :options="actionOptions"
          />
          <n-select
            v-model:value="filters.status"
            clearable
            placeholder="状态"
            class="filter-status"
            :options="statusOptions"
          />
          <n-input
            v-model:value="filters.q"
            clearable
            placeholder="搜索标题/路径/说明"
            class="filter-q"
            @keyup.enter="load"
          />
          <div class="filter-actions">
            <n-button type="primary" class="filter-btn" :loading="loading" @click="load">查询</n-button>
            <n-button class="filter-btn" @click="resetFilters">重置</n-button>
            <n-button type="error" secondary class="filter-btn" :loading="clearing" @click="clearAll">清空日志</n-button>
          </div>
        </div>

        <sp-table
          v-if="!isMobile"
          :columns="columns"
          :data="rows"
          :loading="loading"
          :bordered="false"
          :single-line="false"
          size="small"
        />

        <div v-else class="mobile-log-list">
          <n-spin :show="loading">
            <n-empty v-if="!rows.length && !loading" description="暂无操作日志" />
            <n-space v-else vertical size="small">
              <div v-for="row in rows" :key="row.id || `${row.created_at}-${row.title}`" class="log-card">
                <div class="log-head">
                  <div class="log-tags">
                    <n-tag size="small" :bordered="false">{{ actionLabel[row.action] || row.action }}</n-tag>
                    <n-tag size="small" :bordered="false" :type="statusType[row.status] || 'default'">
                      {{ statusLabel[row.status] || row.status }}
                    </n-tag>
                  </div>
                  <n-text depth="3" class="log-time">{{ formatDateTime(row.created_at, { withYear: true }) }}</n-text>
                </div>
                <div class="log-title">{{ row.title || '—' }}</div>
                <div v-if="row.message" class="log-message">{{ row.message }}</div>
                <div v-if="row.local_path" class="log-path">本地：{{ row.local_path }}</div>
                <div v-if="row.remote_path" class="log-path">远程：{{ row.remote_path }}</div>
                <div v-if="row.task_id != null" class="log-task">任务 #{{ row.task_id }}</div>
              </div>
            </n-space>
          </n-spin>
        </div>
      </n-space>
    </n-card>
  </n-space>
</template>

<script setup>
import { h, onMounted, reactive, ref } from 'vue'
import { NTag, useDialog, useMessage } from 'naive-ui'
import api from '@/api/client'
import { useIsMobile } from '@/composables/useIsMobile'
import { formatDateTime } from '@/utils/format'

const message = useMessage()
const dialog = useDialog()
const isMobile = useIsMobile()
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

/**
 * 状态文案。后端返回的是英文枚举（success / failed / …），
 * 直接渲染会让界面出现中英混排 —— 违反「中文优先」红线。
 * 所有状态的展示都必须过这张表。
 */
const statusLabel = {
  success: '成功',
  failed: '失败',
  skipped: '跳过',
  partial: '部分成功',
  renamed: '已重命名',
}

/**
 * 路径列只展示文件名。
 * 完整路径对用户零价值（同一批日志前缀全相同），却会把列撑爆
 * ——实测 565px 内容塞进 153px，12 行全部被截断成 `/Users/yuanjun/Work/...`。
 * 完整路径挂在 title 上，悬停可见，信息不丢失。
 */
function baseName(p) {
  if (!p) return '—'
  const parts = String(p).split(/[\\/]/).filter(Boolean)
  return parts.length ? parts[parts.length - 1] : String(p)
}

const columns = [
  {
    title: '时间',
    key: 'created_at',
    width: 170,
    className: 'sp-num',
    render: (row) => formatDateTime(row.created_at, { withYear: true }),
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
        { default: () => statusLabel[row.status] || row.status },
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
    width: 170,
    ellipsis: { tooltip: false },
    render: (row) => h('span', { title: row.local_path || '' }, baseName(row.local_path)),
  },
  {
    title: '远程路径',
    key: 'remote_path',
    width: 170,
    ellipsis: { tooltip: false },
    render: (row) => h('span', { title: row.remote_path || '' }, baseName(row.remote_path)),
  },
  {
    title: '任务',
    key: 'task_id',
    width: 80,
    render: (row) => (row.task_id != null ? `#${row.task_id}` : '—'),
  },
]

function isDir(row) { return row.is_dir || row.type === 'dir' || row.isdir }

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

<style scoped>
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.filter-action,
.filter-status {
  width: 140px;
}
.filter-q {
  width: 260px;
}
.filter-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.log-card {
  border: 1px solid var(--sp-ui-border);
  border-radius: var(--sp-radius-lg);
  padding: 12px;
  background: color-mix(in srgb, var(--sp-ui-card) 92%, transparent);
}
.log-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: flex-start;
}
.log-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.log-time {
  flex-shrink: 0;
  font-size: var(--sp-fs-caption);
  line-height: 1.4;
}
.log-title {
  margin-top: 8px;
  font-weight: 600;
  line-height: 1.4;
  word-break: break-word;
}
.log-message,
.log-path,
.log-task {
  margin-top: 6px;
  color: var(--sp-ui-text-3);
  font-size: var(--sp-fs-caption);
  line-height: 1.45;
  word-break: break-word;
}
@media (max-width: 768px) {
  .logs-card :deep(.n-card__content) {
    padding-top: 12px;
  }
  .filters {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }
  .filter-action,
  .filter-status,
  .filter-q {
    width: 100%;
  }
  .filter-q {
    grid-column: 1 / -1;
  }
  .filter-actions {
    grid-column: 1 / -1;
  }
  .filter-btn {
    flex: 1;
  }
}
</style>
