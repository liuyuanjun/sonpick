<template>
  <n-space vertical size="large" style="width: 100%">
    <n-card title="歌曲源">
      <template #header-extra>
        <n-space>
          <n-button type="primary" @click="openCreate('local')">添加本地源</n-button>
          <n-button type="info" @click="openCreate('webdav')">添加 WebDAV 源</n-button>
          <n-button :loading="loading" @click="load">刷新</n-button>
        </n-space>
      </template>

      <n-data-table :columns="columns" :data="sources" :loading="loading" :row-key="(r) => r.id" />
    </n-card>

    <n-modal v-model:show="showForm" preset="card" :title="formTitle" style="width: 640px">
      <n-form label-placement="left" label-width="130px">
        <n-form-item label="名称">
          <n-input v-model:value="form.name" placeholder="例如 本地曲库 / NAS WebDAV" :disabled="isEditingBuiltin" />
        </n-form-item>
        <n-form-item label="类型">
          <n-tag>{{ form.type === 'local' ? '本地' : 'WebDAV' }}</n-tag>
        </n-form-item>
        <n-form-item label="启用">
          <n-switch v-model:value="form.enabled" />
        </n-form-item>

        <template v-if="form.type === 'local'">
          <n-form-item label="根目录">
            <n-input v-model:value="form.root_path" placeholder="/app/downloads 或 NAS 路径" :disabled="isEditingBuiltin" />
            <n-text v-if="isEditingBuiltin" depth="3" style="margin-left: 8px; font-size: 12px">内置本地曲库路径不可修改</n-text>
          </n-form-item>
          <n-form-item label="扫描子目录">
            <n-input
              v-model:value="form.scan_dirs_text"
              type="textarea"
              :rows="3"
              placeholder="每行一个，相对根目录或绝对路径；空表示扫根目录"
            />
          </n-form-item>
        </template>

        <template v-else>
          <n-form-item label="WebDAV URL">
            <n-input v-model:value="form.webdav_url" placeholder="https://example.com/dav/music" />
          </n-form-item>
          <n-form-item label="用户名">
            <n-input v-model:value="form.webdav_username" />
          </n-form-item>
          <n-form-item label="密码">
            <n-input
              v-model:value="form.webdav_password"
              type="password"
              show-password-on="click"
              :placeholder="editingId ? '留空表示不修改' : 'WebDAV 密码'"
            />
          </n-form-item>
          <n-form-item label="远程子目录">
            <n-input v-model:value="form.remote_dir" placeholder="可选，相对 WebDAV 根" />
          </n-form-item>
          <n-form-item label="扫描目录">
            <n-input
              v-model:value="form.scan_remote_dirs_text"
              type="textarea"
              :rows="3"
              placeholder="每行一个远程相对路径；空行表示远程根"
            />
          </n-form-item>
          <n-form-item label="上传侧车">
            <n-switch v-model:value="form.upload_sidecar" />
          </n-form-item>
          <n-form-item label="冲突策略">
            <n-select
              v-model:value="form.conflict_policy"
              :options="[
                { label: '重命名', value: 'rename' },
                { label: '覆盖', value: 'overwrite' },
                { label: '跳过', value: 'skip' },
              ]"
            />
          </n-form-item>
          <n-form-item label="上传后删本地">
            <n-switch v-model:value="form.delete_local_after_upload" />
          </n-form-item>
        </template>

        <n-form-item label="排除规则">
          <n-input
            v-model:value="form.exclude_globs_text"
            type="textarea"
            :rows="2"
            placeholder="每行一个 glob，如 **/.@__thumb/**"
          />
        </n-form-item>
        <n-form-item label="音频扩展名">
          <n-input v-model:value="form.audio_exts" placeholder="mp3,flac,m4a,ogg,wav,aac" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showForm = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="saveForm">保存</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 整理预览 -->
    <n-modal v-model:show="showReorg" preset="card" title="歌曲整理" style="width: min(980px, 96vw)">
      <n-space vertical>
        <n-text depth="3">
          源：{{ reorgSource?.name }}（{{ reorgSource?.type }}）。将按「艺术家/专辑/歌名」整理；失败文件会进入
          <code>_failed/</code>。先配置条件并预览，确认后再应用。
        </n-text>
        <n-form label-placement="left" label-width="110" size="small">
          <n-form-item label="整理目录">
            <n-space vertical style="width: 100%">
              <n-space align="center">
                <n-tag size="small" type="info">当前：{{ reorgForm.relative_dir || '（源根目录）' }}</n-tag>
                <n-button size="tiny" :disabled="!reorgForm.relative_dir" @click="reorgGoUp">上级</n-button>
                <n-button size="tiny" @click="reorgGoRoot">根目录</n-button>
                <n-button size="tiny" :loading="reorgDirsLoading" @click="loadReorgDirs">刷新目录</n-button>
              </n-space>
              <n-select
                v-model:value="reorgSelectedChild"
                :options="reorgDirOptions"
                placeholder="进入子目录（可选）"
                clearable
                filterable
                :loading="reorgDirsLoading"
                @update:value="onReorgEnterDir"
              />
            </n-space>
          </n-form-item>
          <n-form-item label="最大数量">
            <n-input-number v-model:value="reorgForm.limit" :min="0" :max="100000" style="width: 180px" />
            <n-text depth="3" style="margin-left: 8px; font-size: 12px">默认 20；填 0 表示不限制</n-text>
          </n-form-item>
          <n-form-item label="包含 _failed">
            <n-switch v-model:value="reorgForm.include_failed" />
            <n-text depth="3" style="margin-left: 8px; font-size: 12px">默认跳过失败目录</n-text>
          </n-form-item>
          <n-form-item label="联网补专辑">
            <n-switch v-model:value="reorgForm.allow_network" />
            <n-text depth="3" style="margin-left: 8px; font-size: 12px">
              默认关。开启仅做短时 MusicBrainz 探测，仍可能较慢；大批量请先用「刮削」
            </n-text>
          </n-form-item>
        </n-form>
        <n-space>
          <n-button type="primary" size="small" :loading="reorgLoading" @click="runReorgPreview">生成预览</n-button>
          <n-tag type="info">匹配 {{ reorgPreview.scanned ?? reorgPreview.total ?? 0 }}</n-tag>
          <n-tag type="default">预览 {{ reorgPreview.total || 0 }}</n-tag>
          <n-tag type="warning">将变更 {{ reorgPreview.changed || 0 }}</n-tag>
          <n-tag type="error">缺专辑跳过 {{ reorgPreview.skipped || 0 }}</n-tag>
        </n-space>
        <n-data-table
          size="small"
          :columns="reorgColumns"
          :data="reorgPreview.items || []"
          :max-height="360"
          :bordered="false"
          :row-key="(r, i) => `${r.from_path}-${i}`"
        />
        <n-alert v-if="reorgResult" :type="reorgResult.failed ? 'warning' : 'success'">
          已应用：移动 {{ reorgResult.moved || 0 }}，保持 {{ reorgResult.kept || 0 }}，失败
          {{ reorgResult.failed || 0 }}
        </n-alert>
      </n-space>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showReorg = false">关闭</n-button>
          <n-button
            type="primary"
            :loading="reorgApplying"
            :disabled="!reorgPreview.total"
            @click="runReorgApply"
          >
            确认整理
          </n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 刮削 -->
    <n-modal v-model:show="showScrape" preset="card" title="刮削元数据" style="width: 520px">
      <n-form label-placement="left" label-width="120px">
        <n-form-item label="目标源">
          <n-text>{{ scrapeTarget?.name }}</n-text>
        </n-form-item>
        <n-form-item label="网络补全">
          <n-switch v-model:value="scrapeForm.allow_network" />
          <n-text depth="3" style="margin-left: 8px; font-size: 12px">MusicBrainz → 网易/QQ/咪咕，异步执行</n-text>
        </n-form-item>
        <n-form-item label="写回文件标签">
          <n-switch v-model:value="scrapeForm.write_file_tags" />
        </n-form-item>
        <n-form-item label="覆盖已有">
          <n-switch v-model:value="scrapeForm.overwrite" />
        </n-form-item>
        <n-form-item label="数量限制">
          <n-input-number v-model:value="scrapeForm.limit" :min="0" :max="100000" style="width: 180px" />
          <n-text depth="3" style="margin-left: 8px; font-size: 12px">默认 20；建议小批量</n-text>
        </n-form-item>
        <n-text depth="3" style="font-size: 12px">
          异步任务：补全库内元数据，并尽量写回本地音频标签；结果可缓存。整理默认跳过无专辑条目。
        </n-text>
        <n-alert v-if="scrapeTaskId" type="info" style="margin-top: 12px">
          任务 #{{ scrapeTaskId }} · {{ scrapeTaskStatus || 'pending' }} · {{ scrapeTaskMessage || '排队中' }}
        </n-alert>
        <n-alert v-if="scrapeResult" type="success" style="margin-top: 12px">
          更新 {{ scrapeResult.updated || 0 }}，跳过 {{ scrapeResult.skipped || 0 }}，失败
          {{ scrapeResult.failed || 0 }}
        </n-alert>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showScrape = false">关闭</n-button>
          <n-button type="primary" :loading="scrapeLoading" @click="runScrape">开始刮削</n-button>
        </n-space>
      </template>
    </n-modal>
  </n-space>
</template>

<script setup>
import { computed, h, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NSpace, NTag, useMessage } from 'naive-ui'
import {
  createSource,
  deleteSource,
  fetchSources,
  updateSource,
  testSource,
  setDefaultUploadSource,
  scanSource,
  listReorganizeDirs,
  previewReorganize,
  applyReorganize,
  scrapeSource,
  waitTask,
} from '@/api/music'

const message = useMessage()
const router = useRouter()

function formatApiError(err, fallback = '操作失败') {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const text = detail
      .map((item) => (typeof item === 'string' ? item : item?.msg || JSON.stringify(item)))
      .filter(Boolean)
      .join('; ')
    if (text) return text
  }
  if (detail && typeof detail === 'object') {
    try {
      return JSON.stringify(detail)
    } catch (_) {
      /* ignore */
    }
  }
  return err?.message || fallback
}

const loading = ref(false)
const sources = ref([])
const showForm = ref(false)
const saving = ref(false)
const editingId = ref(null)

const form = reactive({
  name: '',
  type: 'local',
  enabled: true,
  root_path: '',
  scan_dirs_text: '',
  webdav_url: '',
  webdav_username: '',
  webdav_password: '',
  remote_dir: '',
  scan_remote_dirs_text: '',
  exclude_globs_text: '',
  audio_exts: 'mp3,flac,m4a,ogg,wav,aac',
  upload_sidecar: true,
  conflict_policy: 'rename',
  delete_local_after_upload: false,
})

const formTitle = computed(() =>
  editingId.value ? `编辑源 #${editingId.value}` : form.type === 'local' ? '添加本地源' : '添加 WebDAV 源'
)

// reorganize
const showReorg = ref(false)
const reorgSource = ref(null)
const reorgLoading = ref(false)
const reorgApplying = ref(false)
const reorgDirsLoading = ref(false)
const reorgPreview = ref({ total: 0, changed: 0, scanned: 0, items: [] })
const reorgResult = ref(null)
const reorgForm = reactive({
  relative_dir: '',
  limit: 20,
  include_failed: false,
  allow_network: false,
})
const reorgDirOptions = ref([])
const reorgSelectedChild = ref(null)
const reorgColumns = [
  { title: '标题', key: 'title', ellipsis: { tooltip: true }, width: 140 },
  { title: '艺术家', key: 'artist', width: 110, ellipsis: { tooltip: true } },
  { title: '专辑', key: 'album', width: 120, ellipsis: { tooltip: true } },
  { title: '从', key: 'from_path', ellipsis: { tooltip: true } },
  { title: '到', key: 'to_path', ellipsis: { tooltip: true } },
  {
    title: '变更',
    key: 'changed',
    width: 70,
    render: (r) =>
      h(NTag, { size: 'small', type: r.changed ? 'warning' : 'success' }, { default: () => (r.changed ? '是' : '否') }),
  },
]

// scrape
const showScrape = ref(false)
const scrapeTarget = ref(null)
const scrapeLoading = ref(false)
const scrapeResult = ref(null)
const scrapeForm = reactive({
  allow_network: true,
  overwrite: false,
  write_file_tags: true,
  limit: 20,
})
const scrapeTaskId = ref(null)
const scrapeTaskStatus = ref('')
const scrapeTaskMessage = ref('')

function statusTag(row) {
  const s = row.connection_status || 'unknown'
  const map = {
    ok: { type: 'success', text: '正常' },
    failed: { type: 'error', text: '失败' },
    not_configured: { type: 'warning', text: '未配置' },
    unknown: { type: 'default', text: '未知' },
  }
  const m = map[s] || map.unknown
  return h(NTag, { type: m.type, size: 'small' }, { default: () => m.text })
}

const columns = [
  { title: 'ID', key: 'id', width: 60 },
  {
    title: '名称',
    key: 'name',
    ellipsis: { tooltip: true },
    render: (r) => h(NSpace, { size: 4, align: 'center' }, {
      default: () => [
        r.name,
        r.is_builtin ? h(NTag, { size: 'small', type: 'warning' }, { default: () => '内置' }) : null,
      ].filter(Boolean),
    }),
  },
  {
    title: '类型',
    key: 'type',
    width: 90,
    render: (r) =>
      h(NTag, { size: 'small', type: r.type === 'webdav' ? 'info' : 'success' }, {
        default: () => (r.type === 'webdav' ? 'WebDAV' : '本地'),
      }),
  },
  {
    title: '启用',
    key: 'enabled',
    width: 70,
    render: (r) =>
      h(NTag, { size: 'small', type: r.enabled ? 'success' : 'default' }, {
        default: () => (r.enabled ? '是' : '否'),
      }),
  },
  {
    title: '连通',
    key: 'connection_status',
    width: 90,
    render: (r) => statusTag(r),
  },
  {
    title: '歌曲数',
    key: 'song_count',
    width: 80,
    render: (r) => r.song_count ?? '-',
  },
  {
    title: '默认上传',
    key: 'is_default_upload',
    width: 90,
    render: (r) =>
      r.type === 'webdav'
        ? h(NTag, { size: 'small', type: r.is_default_upload ? 'warning' : 'default' }, {
            default: () => (r.is_default_upload ? '是' : '否'),
          })
        : '-',
  },
  {
    title: '操作',
    key: 'actions',
    width: 420,
    render(row) {
      const buttons = [
        h(NButton, { size: 'tiny', onClick: () => openEdit(row) }, { default: () => '编辑' }),
        h(NButton, { size: 'tiny', onClick: () => onTest(row) }, { default: () => '测试' }),
        h(NButton, { size: 'tiny', type: 'primary', onClick: () => onScan(row) }, { default: () => '扫描' }),
        h(NButton, { size: 'tiny', onClick: () => openReorg(row) }, { default: () => '整理' }),
        h(NButton, { size: 'tiny', onClick: () => openScrape(row) }, { default: () => '刮削' }),
      ]
      if (row.type === 'webdav') {
        buttons.push(
          h(NButton, { size: 'tiny', type: 'info', onClick: () => openBrowse(row) }, { default: () => '浏览' })
        )
        if (!row.is_default_upload) {
          buttons.push(
            h(NButton, { size: 'tiny', onClick: () => onDefault(row) }, { default: () => '默认上传' })
          )
        }
      }
      if (row.deletable !== false && !row.is_builtin) {
        buttons.push(
          h(NButton, { size: 'tiny', type: 'error', onClick: () => onDelete(row) }, { default: () => '删除' })
        )
      }
      return h(NSpace, { size: 4, wrap: true }, { default: () => buttons })
    },
  },
]

function linesToList(text) {
  return String(text || '')
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter(Boolean)
}

function listToLines(arr) {
  return (arr || []).join('\n')
}

function resetForm(type = 'local') {
  editingId.value = null
  editingBuiltin.value = false
  form.name = ''
  form.type = type
  form.enabled = true
  form.root_path = ''
  form.scan_dirs_text = ''
  form.webdav_url = ''
  form.webdav_username = ''
  form.webdav_password = ''
  form.remote_dir = ''
  form.scan_remote_dirs_text = type === 'webdav' ? '' : ''
  form.exclude_globs_text = ''
  form.audio_exts = 'mp3,flac,m4a,ogg,wav,aac'
  form.upload_sidecar = true
  form.conflict_policy = 'rename'
  form.delete_local_after_upload = false
}

function openCreate(type) {
  resetForm(type)
  showForm.value = true
}

function openEdit(row) {
  resetForm(row.type)
  editingId.value = row.id
  editingBuiltin.value = !!row.is_builtin || (row.type === 'local' && String(row.root_path || '').replace(/\/+$/, '') === '/app/downloads')
  form.name = row.name || ''
  form.type = row.type
  form.enabled = !!row.enabled
  form.root_path = row.root_path || ''
  form.scan_dirs_text = listToLines(row.scan_dirs)
  form.webdav_url = row.webdav_url || ''
  form.webdav_username = row.webdav_username || ''
  form.webdav_password = ''
  form.remote_dir = row.remote_dir || ''
  form.scan_remote_dirs_text = listToLines(row.scan_remote_dirs)
  form.exclude_globs_text = listToLines(row.exclude_globs)
  form.audio_exts = row.audio_exts || 'mp3,flac,m4a,ogg,wav,aac'
  form.upload_sidecar = row.upload_sidecar !== false
  form.conflict_policy = row.conflict_policy || 'rename'
  form.delete_local_after_upload = !!row.delete_local_after_upload
  showForm.value = true
}

function openBrowse(row) {
  router.push({ path: '/webdav', query: { source_id: row.id } })
}

function reorgPayload() {
  return {
    relative_dir: reorgForm.relative_dir || '',
    limit: Number(reorgForm.limit ?? 20),
    include_failed: !!reorgForm.include_failed,
    allow_network: !!reorgForm.allow_network,
  }
}

async function loadReorgDirs() {
  if (!reorgSource.value) return
  reorgDirsLoading.value = true
  reorgSelectedChild.value = null
  try {
    const res = await listReorganizeDirs(reorgSource.value.id, reorgForm.relative_dir || '')
    const data = res.data || res || {}
    const dirs = data.dirs || []
    reorgDirOptions.value = dirs.map((d) => ({
      label: d.name,
      value: d.path,
    }))
  } catch (err) {
    reorgDirOptions.value = []
    message.error(formatApiError(err, '加载目录失败'))
  } finally {
    reorgDirsLoading.value = false
  }
}

async function onReorgEnterDir(path) {
  if (!path) return
  reorgForm.relative_dir = path
  reorgSelectedChild.value = null
  reorgPreview.value = { total: 0, changed: 0, scanned: 0, items: [] }
  reorgResult.value = null
  await loadReorgDirs()
}

async function reorgGoRoot() {
  reorgForm.relative_dir = ''
  reorgSelectedChild.value = null
  reorgPreview.value = { total: 0, changed: 0, scanned: 0, items: [] }
  reorgResult.value = null
  await loadReorgDirs()
}

async function reorgGoUp() {
  const cur = String(reorgForm.relative_dir || '').replaceAll('\\', '/').replace(/^\/+|\/+$/g, '')
  if (!cur) return
  const parts = cur.split('/').filter(Boolean)
  parts.pop()
  reorgForm.relative_dir = parts.join('/')
  reorgSelectedChild.value = null
  reorgPreview.value = { total: 0, changed: 0, scanned: 0, items: [] }
  reorgResult.value = null
  await loadReorgDirs()
}

async function openReorg(row) {
  reorgSource.value = row
  reorgResult.value = null
  reorgPreview.value = { total: 0, changed: 0, scanned: 0, items: [] }
  reorgForm.relative_dir = ''
  reorgForm.limit = 20
  reorgForm.include_failed = false
  reorgForm.allow_network = false
  reorgSelectedChild.value = null
  reorgDirOptions.value = []
  showReorg.value = true
  await loadReorgDirs()
}

async function runReorgPreview() {
  if (!reorgSource.value) return
  reorgLoading.value = true
  try {
    const res = await previewReorganize(reorgSource.value.id, reorgPayload())
    reorgPreview.value = res.data || res || { total: 0, changed: 0, scanned: 0, items: [] }
  } catch (err) {
    message.error(formatApiError(err, '预览失败'))
  } finally {
    reorgLoading.value = false
  }
}

async function runReorgApply() {
  if (!reorgSource.value) return
  const payload = reorgPayload()
  const dirLabel = payload.relative_dir || '源根目录'
  const limitLabel = payload.limit > 0 ? payload.limit : '不限制'
  if (
    !window.confirm(
      `确认整理源「${reorgSource.value.name}」？\n目录：${dirLabel}\n最大数量：${limitLabel}\n包含 _failed：${payload.include_failed ? '是' : '否'}\n此操作会移动文件，失败项将进入 _failed/`,
    )
  ) {
    return
  }
  reorgApplying.value = true
  try {
    const res = await applyReorganize(reorgSource.value.id, payload)
    reorgResult.value = res.data || res || {}
    message.success('整理完成')
    await runReorgPreview()
    await load()
  } catch (err) {
    message.error(formatApiError(err, '整理失败'))
  } finally {
    reorgApplying.value = false
  }
}

let stopScrapeWatch = null
function stopScrapePoll() {
  if (stopScrapeWatch) {
    try { stopScrapeWatch() } catch (_) {}
    stopScrapeWatch = null
  }
}

function openScrape(row) {
  stopScrapePoll()
  scrapeTarget.value = row
  scrapeResult.value = null
  scrapeTaskId.value = null
  scrapeTaskStatus.value = ''
  scrapeTaskMessage.value = ''
  scrapeForm.allow_network = true
  scrapeForm.overwrite = false
  scrapeForm.write_file_tags = true
  scrapeForm.limit = 20
  showScrape.value = true
}

async function pollScrapeTask(taskId) {
  stopScrapePoll()
  try {
    const task = await waitTask(taskId, {
      onProgress: (t) => {
        scrapeTaskStatus.value = t?.status || ''
        scrapeTaskMessage.value = t?.progress?.message || ''
      },
    })
    scrapeTaskStatus.value = task?.status || ''
    scrapeTaskMessage.value = task?.progress?.message || ''
    if (task?.status === 'completed') {
      scrapeResult.value = task.result || {}
      scrapeLoading.value = false
      message.success('刮削完成')
      await load()
    } else {
      scrapeLoading.value = false
      message.error(task?.error_message || '刮削失败')
    }
  } catch (err) {
    scrapeLoading.value = false
    message.error(formatApiError(err, '查询刮削任务失败'))
  } finally {
    stopScrapePoll()
  }
}

async function runScrape() {
  if (!scrapeTarget.value) return
  scrapeLoading.value = true
  scrapeResult.value = null
  scrapeTaskId.value = null
  try {
    const res = await scrapeSource(scrapeTarget.value.id, {
      allow_network: scrapeForm.allow_network,
      overwrite: scrapeForm.overwrite,
      write_file_tags: scrapeForm.write_file_tags,
      limit: scrapeForm.limit || 20,
      async_mode: true,
    })
    const data = res.data || res || {}
    if (data.task_id) {
      scrapeTaskId.value = data.task_id
      scrapeTaskStatus.value = data.status || 'pending'
      scrapeTaskMessage.value = '已创建任务'
      message.success(`刮削任务 #${data.task_id} 已创建`)
      await pollScrapeTask(data.task_id)
    } else {
      scrapeResult.value = data
      scrapeLoading.value = false
      message.success('刮削完成')
      await load()
    }
  } catch (err) {
    scrapeLoading.value = false
    message.error(formatApiError(err, '刮削失败'))
  }
}

async function load() {
  loading.value = true
  try {
    const res = await fetchSources()
    sources.value = res.data || res || []
  } catch (err) {
    message.error(err.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

function buildPayload() {
  const payload = {
    name: form.name.trim(),
    type: form.type,
    enabled: form.enabled,
    exclude_globs: linesToList(form.exclude_globs_text),
    audio_exts: form.audio_exts || null,
  }
  if (form.type === 'local') {
    payload.root_path = form.root_path || null
    payload.scan_dirs = linesToList(form.scan_dirs_text)
  } else {
    payload.webdav_url = form.webdav_url || null
    payload.webdav_username = form.webdav_username || null
    if (form.webdav_password) payload.webdav_password = form.webdav_password
    payload.remote_dir = form.remote_dir || null
    payload.scan_remote_dirs = linesToList(form.scan_remote_dirs_text)
    payload.upload_sidecar = form.upload_sidecar
    payload.conflict_policy = form.conflict_policy
    payload.delete_local_after_upload = form.delete_local_after_upload
  }
  return payload
}

async function saveForm() {
  if (!form.name.trim()) {
    message.warning('请填写名称')
    return
  }
  saving.value = true
  try {
    const payload = buildPayload()
    if (editingId.value) {
      await updateSource(editingId.value, payload)
      message.success('已更新')
    } else {
      await createSource(payload)
      message.success('已创建')
    }
    showForm.value = false
    await load()
  } catch (err) {
    message.error(err.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function onTest(row) {
  try {
    const res = await testSource(row.id)
    const d = res.data || {}
    if (d.ok || d.connection_status === 'ok') message.success(d.message || '连接正常')
    else message.error(d.message || d.connection_message || '连接失败')
    await load()
  } catch (err) {
    message.error(err.response?.data?.detail || '测试失败')
  }
}

async function onScan(row) {
  try {
    message.loading('正在扫描...', { duration: 1200 })
    const res = await scanSource(row.id)
    const d = res.data || {}
    message.success(`扫描完成：新增 ${d.total_added || 0}，更新 ${d.total_updated || 0}`)
    await load()
  } catch (err) {
    message.error(err.response?.data?.detail || '扫描失败')
  }
}

async function onDefault(row) {
  try {
    await setDefaultUploadSource(row.id)
    message.success('已设为默认上传源')
    await load()
  } catch (err) {
    message.error(err.response?.data?.detail || '设置失败')
  }
}

async function onDelete(row) {
  if (!window.confirm(`确定删除源「${row.name}」？关联歌曲不会删除文件，仅解除来源标记。`)) return
  try {
    await deleteSource(row.id)
    message.success('已删除')
    await load()
  } catch (err) {
    message.error(err.response?.data?.detail || '删除失败')
  }
}

onMounted(load)
</script>
