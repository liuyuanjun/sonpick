<template>
    <div class="library-layout">
    <div class="library-side">
      <n-card class="source-panel" title="曲库来源" size="small">
        <template #header-extra>
          <n-space size="small">
            <n-dropdown trigger="click" :options="createOptions" @select="openCreate">
              <n-button type="primary" size="small">添加曲库</n-button>
            </n-dropdown>
            <n-button size="small" :loading="sourcesLoading" @click="loadSources">刷新</n-button>
          </n-space>
        </template>

        <n-empty v-if="!sources.length && !sourcesLoading" description="暂无曲库" />
        <n-spin :show="sourcesLoading">
          <n-space vertical size="small">
              <n-card
                v-for="source in sources"
                :key="source.id"
                class="source-card"
                :class="{ active: selectedSourceId === source.id }"
                size="small"
                hoverable
                @click="selectSource(source)"
              >
              <n-space vertical size="small">
                <n-space justify="space-between" align="center">
                  <n-space size="small" align="center">
                    <n-text strong>{{ source.name }}</n-text>
                    <n-tag v-if="source.is_builtin" size="small" type="warning">内置</n-tag>
                  </n-space>
                  <n-tag size="small" :type="source.type === 'webdav' ? 'info' : 'success'">
                    {{ source.type === 'webdav' ? 'WebDAV' : '本地' }}
                  </n-tag>
                </n-space>
                <n-space size="small" align="center" wrap>
                  <n-tag size="small" :type="source.enabled ? 'success' : 'default'">{{ source.enabled ? '启用' : '停用' }}</n-tag>
                  <n-tag size="small" :type="statusTagType(source)">{{ statusText(source) }}</n-tag>
                  <n-tag v-if="source.is_default_upload" size="small" type="warning">默认上传</n-tag>
                  <n-text depth="3" style="font-size: 12px">歌曲 {{ source.song_count ?? '-' }}</n-text>
                </n-space>
                <n-text depth="3" class="source-path">{{ sourcePath(source) }}</n-text>
                <n-space size="small" wrap @click.stop>
                  <n-button size="tiny" @click="openEdit(source)">编辑</n-button>
                  <n-button size="tiny" @click="onTest(source)">测试</n-button>
                  <n-button size="tiny" type="primary" @click="onScan(source)">扫描</n-button>
                  <n-button size="tiny" @click="openReorg(source)">整理</n-button>
                  <n-button size="tiny" @click="openScrape(source)">刮削</n-button>
                  <n-button size="tiny" type="info" @click="openBrowseMode(source)">浏览</n-button>
                  <n-button v-if="source.type === 'webdav' && !source.is_default_upload" size="tiny" @click="onDefault(source)">默认上传</n-button>
                  <n-button v-if="source.deletable !== false && !source.is_builtin" size="tiny" type="error" @click="onDeleteSource(source)">删除</n-button>
                </n-space>
              </n-space>
            </n-card>
          </n-space>
        </n-spin>
      </n-card>
    </div>

    <div class="library-main">
      <n-card class="content-panel" :title="selectedSource ? selectedSource.name : '曲库内容'" size="small">
        <template #header-extra>
          <n-tabs v-model:value="mode" class="library-mode-tabs" type="segment" size="medium" @update:value="onModeChange">
            <n-tab-pane name="songs">
              <template #tab><span class="mode-tab-label"><n-icon size="16"><MusicalNotesOutline /></n-icon>歌曲列表</span></template>
            </n-tab-pane>
            <n-tab-pane name="browse">
              <template #tab><span class="mode-tab-label"><n-icon size="16"><FolderOpenOutline /></n-icon>浏览文件</span></template>
            </n-tab-pane>
          </n-tabs>
        </template>

        <template v-if="mode === 'songs'">
          <n-space vertical size="medium">
            <n-space class="library-toolbar" justify="space-between" align="center" wrap>
              <n-input v-model:value="q" clearable placeholder="搜索歌名/歌手" style="width: min(100%, 320px)" @keydown.enter="loadSongs" />
              <n-space size="small" wrap>
                <n-button @click="loadSongs" :loading="songsLoading">刷新歌曲</n-button>
                <n-button v-if="songs.length" type="primary" secondary @click="openScrape(selectedSource)">刮削曲库</n-button>
              </n-space>
            </n-space>
            <n-data-table :columns="songColumns" :data="songs" :loading="songsLoading" :row-key="(r) => r.id" />
          </n-space>
        </template>

        <template v-else>
          <n-space vertical size="medium">
            <n-space justify="space-between" align="center">
              <n-space size="small">
                <n-button size="small" :disabled="!browsePath" @click="browseGoUp">上级</n-button>
                <n-button size="small" @click="browseTo('')">根目录</n-button>
              </n-space>
              <n-button size="small" :loading="browseLoading" @click="loadBrowse">刷新</n-button>
            </n-space>
            <n-breadcrumb>
              <n-breadcrumb-item @click="browseTo('')">根目录</n-breadcrumb-item>
              <n-breadcrumb-item
                v-for="(seg, idx) in browseSegments"
                :key="idx"
                @click="browseTo(browseSegments.slice(0, idx + 1).join('/'))"
              >
                {{ seg }}
              </n-breadcrumb-item>
            </n-breadcrumb>
            <n-alert v-if="browseError" type="error">{{ browseError }}</n-alert>
            <n-data-table
              :columns="browseColumns"
              :data="browseEntries"
              :loading="browseLoading"
              :row-key="(row) => row.path || row.name"
              size="small"
            />
          </n-space>
        </template>
      </n-card>
    </div>
  </div>

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
          <n-input v-model:value="form.scan_dirs_text" type="textarea" :rows="3" placeholder="每行一个，相对根目录或绝对路径；空表示扫根目录" />
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
          <n-input v-model:value="form.webdav_password" type="password" show-password-on="click" placeholder="留空表示不修改" />
        </n-form-item>
        <n-form-item label="远程根目录">
          <n-input v-model:value="form.remote_dir" placeholder="/music 或留空" />
        </n-form-item>
        <n-form-item label="扫描目录">
          <n-input v-model:value="form.scan_remote_dirs_text" type="textarea" :rows="3" placeholder="每行一个远程相对目录；空表示远程根目录" />
        </n-form-item>
        <n-form-item label="上传侧车文件">
          <n-switch v-model:value="form.upload_sidecar" />
        </n-form-item>
        <n-form-item label="冲突策略">
          <n-select v-model:value="form.conflict_policy" :options="conflictOptions" />
        </n-form-item>
        <n-form-item label="上传后删本地">
          <n-switch v-model:value="form.delete_local_after_upload" />
        </n-form-item>
      </template>

      <n-form-item label="排除规则">
        <n-input v-model:value="form.exclude_globs_text" type="textarea" :rows="3" placeholder="每行一个 glob，如 **/@eaDir/**" />
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

  <n-modal v-model:show="showReorg" preset="card" title="整理曲库" style="width: 960px; max-width: 96vw">
    <n-form label-placement="left" label-width="110px">
      <n-alert type="info" style="margin-bottom: 12px">
        当前曲库：{{ reorgSource?.name || '-' }}；目录：/{{ reorgForm.relative_dir || '' }}
      </n-alert>
      <n-form-item label="选择目录">
        <n-space vertical style="width: 100%">
          <n-space>
            <n-button size="small" @click="reorgGoRoot">根目录</n-button>
            <n-button size="small" :disabled="!reorgForm.relative_dir" @click="reorgGoUp">上级</n-button>
            <n-button size="small" :loading="reorgDirsLoading" @click="loadReorgDirs">刷新目录</n-button>
          </n-space>
          <n-select
            v-model:value="reorgSelectedChild"
            filterable
            clearable
            :loading="reorgDirsLoading"
            :options="reorgDirOptions"
            placeholder="选择子目录进入；不选则整理当前目录"
            @update:value="onReorgEnterDir"
          />
        </n-space>
      </n-form-item>
      <n-form-item label="数量限制">
        <n-input-number v-model:value="reorgForm.limit" :min="0" :max="100000" style="width: 180px" />
        <n-text depth="3" style="margin-left: 8px; font-size: 12px">0 表示不限制；建议先小批量预览</n-text>
      </n-form-item>
      <n-form-item label="包含失败目录">
        <n-switch v-model:value="reorgForm.include_failed" />
      </n-form-item>
      <n-form-item label="按格式归档">
        <n-space align="center">
          <n-switch v-model:value="reorgForm.relocate_format_dirs" />
          <n-text depth="3" style="font-size: 12px">开启后，整理时会把错放的无损文件（FLAC/APE/WAV 等）移入「无损存放目录」、MP3 等有损文件移入「MP3 存放目录」下对应的艺术家/专辑位置（目录在设置页配置，默认不开启）。仅本地曲库生效。</n-text>
        </n-space>
      </n-form-item>
      <n-form-item label="允许网络补全">
        <n-switch v-model:value="reorgForm.allow_network" />
      </n-form-item>
      <n-space style="margin-bottom: 12px">
        <n-button :loading="reorgLoading" @click="runReorgPreview">预览</n-button>
        <n-button type="primary" :loading="reorgLoading" :disabled="!reorgPreview.items?.length" @click="runReorgApply">执行整理</n-button>
      </n-space>
      <n-alert v-if="reorgResult" type="success" style="margin-bottom: 12px">
        已整理 {{ reorgResult.changed || 0 }} / {{ reorgResult.total || 0 }}；失败 {{ reorgResult.failed || 0 }}
      </n-alert>
      <n-data-table :columns="reorgColumns" :data="reorgPreview.items || []" :loading="reorgLoading" size="small" max-height="420" />
    </n-form>
  </n-modal>

  <n-modal v-model:show="showScrape" preset="card" title="刮削曲库" style="width: 640px">
    <n-form label-placement="left" label-width="130px">
      <n-alert type="info" style="margin-bottom: 12px">
        当前曲库：{{ scrapeTarget?.name || '-' }}
      </n-alert>
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
      <n-alert v-if="scrapeTaskId" type="info" style="margin-top: 12px">
        任务 #{{ scrapeTaskId }} · {{ scrapeTaskStatus || 'pending' }} · {{ scrapeTaskMessage || '排队中' }}
      </n-alert>
      <n-alert v-if="scrapeResult" type="success" style="margin-top: 12px">
        更新 {{ scrapeResult.updated || 0 }}，跳过 {{ scrapeResult.skipped || 0 }}，失败 {{ scrapeResult.failed || 0 }}
      </n-alert>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="showScrape = false">关闭</n-button>
        <n-button type="primary" :loading="scrapeLoading" @click="runScrape">开始刮削</n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup>
import { computed, h, onMounted, reactive, ref } from 'vue'
import { NButton, NDropdown, NIcon, NSpace, NTag, NTooltip, useMessage } from 'naive-ui'
import { FolderOpenOutline, MusicalNotesOutline, PlayOutline, TrashOutline, CloudUploadOutline, SwapHorizontalOutline } from '@vicons/ionicons5'
import {
  applyReorganize,
  browseLocalSource,
  convertSong,
  createSource,
  deleteBrowseItem,
  deleteSong,
  deleteSource,
  deleteWebdavItem,
  fetchSongs,
  fetchSources,
  listReorganizeDirs,
  listWebdav,
  previewReorganize,
  scanSource,
  scrapeSource,
  setDefaultUploadSource,
  testSource,
  updateSource,
  uploadSongToWebdav,
  waitTask,
} from '@/api/music'
import { usePlayerStore } from '@/stores/player'

const message = useMessage()
const player = usePlayerStore()
const mode = ref('songs')
const sourcesLoading = ref(false)
const songsLoading = ref(false)
const browseLoading = ref(false)
const sources = ref([])
const songs = ref([])
const q = ref('')
const webdavSources = ref([])
const selectedSourceId = ref(null)
const browsePath = ref('')
const browseEntries = ref([])
const browseError = ref('')
const showForm = ref(false)
const saving = ref(false)
const editingId = ref(null)
const editingBuiltin = ref(false)

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

const showReorg = ref(false)
const reorgSource = ref(null)
const reorgLoading = ref(false)
const reorgDirsLoading = ref(false)
const reorgPreview = ref({ total: 0, changed: 0, scanned: 0, items: [] })
const reorgResult = ref(null)
const reorgForm = reactive({ relative_dir: '', limit: 20, include_failed: false, allow_network: false, relocate_format_dirs: false })
const reorgDirOptions = ref([])
const reorgSelectedChild = ref(null)

const showScrape = ref(false)
const scrapeTarget = ref(null)
const scrapeLoading = ref(false)
const scrapeResult = ref(null)
const scrapeForm = reactive({ allow_network: true, overwrite: false, write_file_tags: true, limit: 20 })
const scrapeTaskId = ref(null)
const scrapeTaskStatus = ref('')
const scrapeTaskMessage = ref('')

const createOptions = [
  { label: '添加本地曲库', key: 'local' },
  { label: '添加 WebDAV 曲库', key: 'webdav' },
]
const conflictOptions = [
  { label: '重命名', value: 'rename' },
  { label: '覆盖', value: 'overwrite' },
  { label: '跳过', value: 'skip' },
]
const selectedSource = computed(() => sources.value.find((s) => s.id === selectedSourceId.value) || null)
const isEditingBuiltin = computed(() => editingBuiltin.value)
const formTitle = computed(() => (editingId.value ? '编辑曲库' : `添加${form.type === 'webdav' ? ' WebDAV ' : '本地'}曲库`))
const browseSegments = computed(() => (browsePath.value || '').split('/').filter(Boolean))

const statusLabels = { local: '本地', remote: '远程', both: '双边', uploaded: '已上传' }
const statusTagTypes = { local: 'success', remote: 'info', both: 'warning', uploaded: 'info' }

const songColumns = [
  {
    title: '歌曲', key: 'song',
    render(row) {
      const artist = row.artist || '未知艺术家'
      const album = row.album ? ` · ${row.album}` : ''
      return h('div', { class: 'song-cell' }, [
        h('div', { class: 'song-cell-title', title: row.title || '' }, row.title || '-'),
        h('div', { class: 'song-cell-sub', title: `${artist}${album}` }, `${artist}${album}`),
      ])
    },
  },
  {
    title: '来源', key: 'source', width: 200,
    render(row) {
      const type = row.library_source_type || (row.webdav_path && !row.local_path ? 'webdav' : 'local')
      const name = row.library_source_name || (row.webdav_path ? 'WebDAV' : row.local_path ? '本地' : '-')
      const path = row.local_path || row.webdav_path || '-'
      const status = statusLabels[row.status] || row.status || '-'
      return h('div', { class: 'song-cell' }, [
        h('div', { class: 'song-cell-line' }, [
          h(NTag, { size: 'small', type: type === 'webdav' ? 'info' : 'success' }, { default: () => (type === 'webdav' ? 'WebDAV' : '本地') }),
          h(NTooltip, null, {
            trigger: () => h('span', { class: 'song-cell-name' }, name),
            default: () => path,
          }),
        ]),
        h('div', { class: 'song-cell-line' }, [
          h(NTag, { size: 'small', type: statusTagTypes[row.status] || 'default', bordered: false }, { default: () => status }),
        ]),
      ])
    },
  },
  {
    title: '格式', key: 'format', width: 170,
    render(row) {
      const formats = (row.available_formats || [row.format]).filter(Boolean).map((format) => String(format).toUpperCase()).join(' / ')
      const versions = (row.versions || []).map((item) => `${String(item.format || '').toUpperCase()}·${item.availability_status === 'unavailable' ? '不可用' : '可用'}`).join(' / ')
      return h('div', { class: 'song-cell' }, [
        h('div', { class: 'song-cell-title' }, formats || '-'),
        h('div', { class: 'song-cell-sub', title: versions }, versions || '-'),
      ])
    },
  },
  {
    title: '操作', key: 'actions', width: 150,
    render(row) {
      const iconBtn = (icon, tip, props, onClick) => h(NTooltip, null, {
        trigger: () => h(NButton, {
          size: 'tiny', quaternary: true, circle: true, class: 'song-icon-button',
          'aria-label': tip, onClick, ...props,
        }, { icon: () => h(NIcon, { size: 16 }, { default: () => h(icon) }) }),
        default: () => tip,
      })
      const btns = [iconBtn(PlayOutline, '播放', { type: 'primary' }, () => play(row))]
      if (!(row.available_formats || [row.format]).map((format) => String(format).toLowerCase()).includes('mp3')) {
        btns.push(iconBtn(SwapHorizontalOutline, '转为 MP3', {}, () => onConvert(row)))
      }
      if (row.local_path && webdavSources.value.length) {
        btns.push(h(NTooltip, null, {
          trigger: () => h(NDropdown, {
            trigger: 'click',
            options: webdavSources.value.map((s) => ({ label: s.is_default_upload ? `${s.name}（默认）` : s.name, key: s.id })),
            onSelect: (key) => onUpload(row, key),
          }, {
            default: () => h(NButton, {
              size: 'tiny', quaternary: true, circle: true, type: 'info', class: 'song-icon-button', 'aria-label': '上传到 WebDAV',
            }, { icon: () => h(NIcon, { size: 16 }, { default: () => h(CloudUploadOutline) }) }),
          }),
          default: () => '上传到 WebDAV',
        }))
      }
      btns.push(iconBtn(TrashOutline, '删除', { type: 'error' }, () => onDeleteSong(row)))
      return h(NSpace, { size: 4, class: 'song-action-group', wrap: false }, { default: () => btns })
    },
  },
]

const browseColumns = [
  {
    title: '名称', key: 'name', ellipsis: { tooltip: true },
    render(row) {
      const name = row.name || row.path || ''
      if (isDir(row)) return h(NButton, { text: true, type: 'primary', onClick: () => browseTo(row.path || name) }, { default: () => `📁 ${name}` })
      return name
    },
  },
  { title: '类型', key: 'type', width: 90, render: (row) => h(NTag, { size: 'small', type: isDir(row) ? 'info' : 'default' }, { default: () => (isDir(row) ? '目录' : '文件') }) },
  { title: '大小', key: 'size', width: 110, render: (row) => formatSize(row.size) },
  {
    title: '操作', key: 'actions', width: 110,
    render(row) {
      const iconBtn = (icon, tip, props, onClick) => h(NTooltip, null, {
        trigger: () => h(NButton, {
          size: 'tiny', quaternary: true, circle: true, class: 'song-icon-button',
          'aria-label': tip, onClick, ...props,
        }, { icon: () => h(NIcon, { size: 16 }, { default: () => h(icon) }) }),
        default: () => tip,
      })
      const btns = []
      if (!isDir(row) && selectedSource.value?.type === 'webdav' && isAudio(row.name || row.path || '')) {
        btns.push(iconBtn(PlayOutline, '播放', { type: 'primary' }, () => playRemote(row)))
      }
      btns.push(iconBtn(TrashOutline, '删除', { type: 'error' }, () => onDeleteBrowseItem(row)))
      return h(NSpace, { size: 4, wrap: false }, { default: () => btns })
    },
  },
]

const reorgColumns = [
  { title: '标题', key: 'title', ellipsis: { tooltip: true }, width: 140 },
  { title: '艺术家', key: 'artist', width: 110, ellipsis: { tooltip: true } },
  { title: '专辑', key: 'album', width: 120, ellipsis: { tooltip: true } },
  { title: '从', key: 'from_path', ellipsis: { tooltip: true } },
  { title: '到', key: 'to_path', ellipsis: { tooltip: true } },
  { title: '变更', key: 'changed', width: 70, render: (r) => h(NTag, { size: 'small', type: r.changed ? 'warning' : 'success' }, { default: () => (r.changed ? '是' : '否') }) },
]

function formatApiError(err, fallback = '操作失败') {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) return detail.map((item) => (typeof item === 'string' ? item : item?.msg || JSON.stringify(item))).filter(Boolean).join('; ') || fallback
  if (detail && typeof detail === 'object') return JSON.stringify(detail)
  return err?.message || fallback
}
function statusText(row) { return ({ ok: '正常', failed: '失败', not_configured: '未配置', unknown: '未知' }[row.connection_status || 'unknown'] || '未知') }
function statusTagType(row) { return ({ ok: 'success', failed: 'error', not_configured: 'warning', unknown: 'default' }[row.connection_status || 'unknown'] || 'default') }
function sourcePath(row) { return row.type === 'webdav' ? (row.remote_dir || row.webdav_url || '-') : (row.root_path || '-') }
function linesToList(text) { return String(text || '').split(/\r?\n/).map((s) => s.trim()).filter(Boolean) }
function listToLines(arr) { return (arr || []).join('\n') }
function isDir(row) { return row.is_dir || row.type === 'dir' || row.isdir }
function isAudio(name = '') { return /\.(mp3|flac|m4a|wav|ogg|aac|ape|wma|opus)$/i.test(name) }
function formatSize(value) {
  const n = Number(value || 0)
  if (!n) return '-'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}
function resetForm(type = 'local') {
  editingId.value = null; editingBuiltin.value = false; form.name = ''; form.type = type; form.enabled = true
  form.root_path = ''; form.scan_dirs_text = ''; form.webdav_url = ''; form.webdav_username = ''; form.webdav_password = ''
  form.remote_dir = ''; form.scan_remote_dirs_text = ''; form.exclude_globs_text = ''; form.audio_exts = 'mp3,flac,m4a,ogg,wav,aac'
  form.upload_sidecar = true; form.conflict_policy = 'rename'; form.delete_local_after_upload = false
}
function openCreate(type) { resetForm(type); showForm.value = true }
function openEdit(row) {
  editingId.value = row.id
  editingBuiltin.value = !!row.is_builtin || (row.type === 'local' && String(row.root_path || '').replace(/\/+$/, '') === '/app/downloads')
  form.name = row.name || ''; form.type = row.type; form.enabled = !!row.enabled; form.root_path = row.root_path || ''; form.scan_dirs_text = listToLines(row.scan_dirs)
  form.webdav_url = row.webdav_url || ''; form.webdav_username = row.webdav_username || ''; form.webdav_password = ''; form.remote_dir = row.remote_dir || ''
  form.scan_remote_dirs_text = listToLines(row.scan_remote_dirs); form.exclude_globs_text = listToLines(row.exclude_globs); form.audio_exts = row.audio_exts || 'mp3,flac,m4a,ogg,wav,aac'
  form.upload_sidecar = row.upload_sidecar !== false; form.conflict_policy = row.conflict_policy || 'rename'; form.delete_local_after_upload = !!row.delete_local_after_upload
  showForm.value = true
}
function buildPayload() {
  const payload = { name: form.name.trim(), type: form.type, enabled: form.enabled, exclude_globs: linesToList(form.exclude_globs_text), audio_exts: form.audio_exts || null }
  if (form.type === 'local') { payload.root_path = form.root_path || null; payload.scan_dirs = linesToList(form.scan_dirs_text) }
  else {
    payload.webdav_url = form.webdav_url || null; payload.webdav_username = form.webdav_username || null; if (form.webdav_password) payload.webdav_password = form.webdav_password
    payload.remote_dir = form.remote_dir || null; payload.scan_remote_dirs = linesToList(form.scan_remote_dirs_text); payload.upload_sidecar = form.upload_sidecar
    payload.conflict_policy = form.conflict_policy; payload.delete_local_after_upload = form.delete_local_after_upload
  }
  return payload
}
function selectDefaultSource(list) {
  if (!list.length) return
  if (selectedSourceId.value && list.some((s) => s.id === selectedSourceId.value)) return
  selectedSourceId.value = (list.find((s) => s.name === '本地曲库') || list.find((s) => s.type === 'local') || list[0]).id
}
function selectSource(source) { selectedSourceId.value = source.id; browsePath.value = ''; if (mode.value === 'songs') loadSongs(); else loadBrowse() }
function onModeChange(value) { if (value === 'songs') loadSongs(); else loadBrowse() }
function openBrowseMode(source) { selectedSourceId.value = source.id; browsePath.value = ''; mode.value = 'browse'; loadBrowse() }

async function loadSources() {
  sourcesLoading.value = true
  try {
    const res = await fetchSources()
    sources.value = res.data || res || []
    webdavSources.value = sources.value.filter((s) => s.type === 'webdav' && s.enabled !== false).sort((a, b) => Number(b.is_default_upload) - Number(a.is_default_upload))
    selectDefaultSource(sources.value)
  } catch (err) { message.error(formatApiError(err, '加载曲库失败')) }
  finally { sourcesLoading.value = false }
}
async function loadSongs() {
  songsLoading.value = true
  try {
    const params = { q: q.value || undefined, page: 1, page_size: 500 }
    if (selectedSourceId.value != null) params.source_id = selectedSourceId.value
    const res = await fetchSongs(params)
    songs.value = res.data || []
  } catch (err) { message.error(formatApiError(err, '加载歌曲失败')) }
  finally { songsLoading.value = false }
}
async function loadBrowse() {
  if (!selectedSource.value) return
  browseLoading.value = true; browseError.value = ''
  try {
    const res = selectedSource.value.type === 'webdav' ? await listWebdav(browsePath.value, selectedSourceId.value) : await browseLocalSource(selectedSourceId.value, browsePath.value)
    const data = res?.data ?? res
    browseEntries.value = Array.isArray(data) ? data : data?.items || data?.entries || []
  } catch (err) { browseEntries.value = []; browseError.value = formatApiError(err, '浏览失败') }
  finally { browseLoading.value = false }
}
function browseTo(path) { browsePath.value = path || ''; loadBrowse() }
function browseGoUp() { const parts = (browsePath.value || '').split('/').filter(Boolean); parts.pop(); browseTo(parts.join('/')) }
function play(row) { player.play(row, songs.value) }
function playRemote(row) {
  const path = row.path || row.name
  if (!path || !selectedSource.value) return
  player.play?.({ id: `webdav:${selectedSourceId.value}:${path}`, title: row.name || path.split('/').pop(), artist: '', album: '', webdav_path: path, library_source_id: selectedSourceId.value, source: 'webdav' })
  message.success('已发送到播放器')
}
async function saveForm() {
  if (!form.name.trim()) { message.warning('请填写名称'); return }
  saving.value = true
  try {
    const payload = buildPayload()
    if (editingId.value) { await updateSource(editingId.value, payload); message.success('已更新') }
    else { await createSource(payload); message.success('已创建') }
    showForm.value = false; await loadSources(); if (mode.value === 'songs') await loadSongs(); else await loadBrowse()
  } catch (err) { message.error(formatApiError(err, '保存失败')) }
  finally { saving.value = false }
}
async function onTest(row) {
  try {
    const d = (await testSource(row.id)).data || {}
    if (d.ok || d.connection_status === 'ok') message.success(d.message || '连接正常')
    else message.error(d.message || d.connection_message || '连接失败')
    await loadSources()
  } catch (err) { message.error(formatApiError(err, '测试失败')) }
}
async function onScan(row) {
  try {
    const d = (await scanSource(row.id)).data || {}
    message.success(`扫描完成：新增 ${d.created || 0}，更新 ${d.updated || 0}，跳过 ${d.skipped || 0}`)
    await loadSources(); await loadSongs()
  } catch (err) { message.error(formatApiError(err, '扫描失败')) }
}
async function onDefault(row) { try { await setDefaultUploadSource(row.id); message.success('已设为默认上传曲库'); await loadSources() } catch (err) { message.error(formatApiError(err, '设置失败')) } }
async function onDeleteSource(row) {
  if (!window.confirm(`删除曲库「${row.name}」？歌曲关联会被解除。`)) return
  try { await deleteSource(row.id); message.success('已删除'); selectedSourceId.value = null; await loadSources(); await loadSongs() }
  catch (err) { message.error(formatApiError(err, '删除失败')) }
}
function reorgPayload() { return { relative_dir: reorgForm.relative_dir || '', limit: Number(reorgForm.limit ?? 20), include_failed: !!reorgForm.include_failed, allow_network: !!reorgForm.allow_network, relocate_format_dirs: !!reorgForm.relocate_format_dirs } }
async function loadReorgDirs() {
  if (!reorgSource.value) return
  reorgDirsLoading.value = true; reorgSelectedChild.value = null
  try { const dirs = ((await listReorganizeDirs(reorgSource.value.id, reorgForm.relative_dir || '')).data || {}).dirs || []; reorgDirOptions.value = dirs.map((d) => ({ label: d.name, value: d.path })) }
  catch (err) { reorgDirOptions.value = []; message.error(formatApiError(err, '加载目录失败')) }
  finally { reorgDirsLoading.value = false }
}
async function onReorgEnterDir(path) { if (!path) return; reorgForm.relative_dir = path; reorgPreview.value = { total: 0, changed: 0, scanned: 0, items: [] }; reorgResult.value = null; await loadReorgDirs() }
async function reorgGoRoot() { reorgForm.relative_dir = ''; reorgPreview.value = { total: 0, changed: 0, scanned: 0, items: [] }; reorgResult.value = null; await loadReorgDirs() }
async function reorgGoUp() { const parts = String(reorgForm.relative_dir || '').replaceAll('\\', '/').replace(/^\/+|\/+$/g, '').split('/').filter(Boolean); parts.pop(); reorgForm.relative_dir = parts.join('/'); reorgPreview.value = { total: 0, changed: 0, scanned: 0, items: [] }; reorgResult.value = null; await loadReorgDirs() }
async function openReorg(row) {
  if (row.type !== 'local') { message.warning('仅本地曲库支持整理'); return }
  reorgSource.value = row; reorgResult.value = null; reorgPreview.value = { total: 0, changed: 0, scanned: 0, items: [] }
  reorgForm.relative_dir = ''; reorgForm.limit = 20; reorgForm.include_failed = false; reorgForm.allow_network = false; reorgForm.relocate_format_dirs = false; reorgDirOptions.value = []; showReorg.value = true; await loadReorgDirs()
}
async function runReorgPreview() {
  if (!reorgSource.value) return
  reorgLoading.value = true
  try { reorgPreview.value = (await previewReorganize(reorgSource.value.id, reorgPayload())).data || { total: 0, changed: 0, scanned: 0, items: [] } }
  catch (err) { message.error(formatApiError(err, '预览失败')) }
  finally { reorgLoading.value = false }
}
async function runReorgApply() {
  if (!reorgSource.value || !window.confirm(`确认整理曲库「${reorgSource.value.name}」？`)) return
  reorgLoading.value = true
  try { reorgResult.value = (await applyReorganize(reorgSource.value.id, reorgPayload())).data || {}; message.success('整理完成'); await loadSources(); await loadSongs() }
  catch (err) { message.error(formatApiError(err, '整理失败')) }
  finally { reorgLoading.value = false }
}
function openScrape(row) { scrapeTarget.value = row; scrapeResult.value = null; scrapeTaskId.value = null; scrapeTaskStatus.value = ''; scrapeTaskMessage.value = ''; scrapeForm.allow_network = true; scrapeForm.overwrite = false; scrapeForm.write_file_tags = true; scrapeForm.limit = 20; showScrape.value = true }
async function pollScrapeTask(taskId) {
  try {
    const task = await waitTask(taskId, { timeoutMs: 30 * 60 * 1000, onProgress: (t) => { scrapeTaskStatus.value = t?.status || ''; const p = t?.progress || t?.progress_json || {}; scrapeTaskMessage.value = p.message || p.current || '' } })
    scrapeTaskStatus.value = task?.status || scrapeTaskStatus.value; scrapeTaskMessage.value = task?.status === 'completed' ? '完成' : (task?.status || '')
    if (task?.status === 'completed') { message.success('刮削完成'); await loadSources(); await loadSongs() }
    else if (task?.status === 'failed') message.error('刮削失败')
  } catch (err) { scrapeTaskMessage.value = formatApiError(err, '任务等待失败') }
  finally { scrapeLoading.value = false }
}
async function runScrape() {
  if (!scrapeTarget.value) return
  scrapeLoading.value = true; scrapeResult.value = null
  try {
    const data = (await scrapeSource(scrapeTarget.value.id, { ...scrapeForm, async_mode: true })).data || {}
    if (data.async && data.task_id) { scrapeTaskId.value = data.task_id; scrapeTaskStatus.value = data.status || 'pending'; scrapeTaskMessage.value = '已创建任务'; message.success(`刮削任务 #${data.task_id} 已创建`); await pollScrapeTask(data.task_id) }
    else { scrapeResult.value = data; scrapeLoading.value = false; message.success('刮削完成'); await loadSources(); await loadSongs() }
  } catch (err) { scrapeLoading.value = false; message.error(formatApiError(err, '刮削失败')) }
}
async function onConvert(row) { try { await convertSong(row.id); message.success('转码完成'); await loadSongs() } catch (err) { message.error(formatApiError(err, '转码失败')) } }
async function onUpload(row, sourceId) { try { const res = await uploadSongToWebdav(row.id, sourceId); message.success(`上传完成：${res.data?.status || 'ok'}`); await loadSongs() } catch (err) { message.error(formatApiError(err, '上传失败')) } }
async function onDeleteSong(row) {
  if (!window.confirm(`删除「${row.title}」？`)) return
  try { await deleteSong(row.id, true); message.success('已删除'); await loadSources(); await loadSongs() }
  catch (err) { message.error(formatApiError(err, '删除失败')) }
}
async function onDeleteBrowseItem(row) {
  const path = row.path || row.name
  const name = row.name || path
  if (!path || !selectedSource.value) return
  const kind = isDir(row) ? '目录（含其中所有内容）' : '文件'
  if (!window.confirm(`删除${kind}「${name}」？此操作不可恢复。`)) return
  try {
    if (selectedSource.value.type === 'webdav') await deleteWebdavItem(path, selectedSourceId.value)
    else await deleteBrowseItem(selectedSourceId.value, path)
    message.success('已删除')
    await loadSources(); await loadBrowse(); if (mode.value === 'songs') await loadSongs()
  } catch (err) { message.error(formatApiError(err, '删除失败')) }
}

onMounted(async () => { await loadSources(); await loadSongs() })
</script>

<style scoped>
.library-layout {
  display: flex;
  gap: 18px;
  align-items: flex-start;
}
.library-side {
  flex: 0 0 500px;
  width: 500px;
  max-width: 100%;
}
.library-main {
  flex: 1;
  min-width: 0;
}
.source-panel,
.content-panel {
  border: 1px solid var(--border-color);
  background: color-mix(in srgb, var(--card-color) 94%, var(--primary-color) 6%);
  box-shadow: 0 14px 34px rgba(21, 32, 53, .07);
}
.source-card {
  cursor: pointer;
  margin-bottom: 10px;
  border: 1px solid transparent;
  border-radius: 12px;
  transition: transform .2s ease, border-color .2s ease, box-shadow .2s ease;
}
.source-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 22px rgba(21, 32, 53, .09);
}
.source-card.active {
  border-color: var(--primary-color);
  background: color-mix(in srgb, var(--primary-color) 10%, var(--card-color));
  box-shadow: 0 10px 22px color-mix(in srgb, var(--primary-color) 18%, transparent);
}
.source-path {
  display: block;
  font-size: 12px;
  word-break: break-all;
}
.library-toolbar {
  padding: 10px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  background: color-mix(in srgb, var(--body-color) 72%, var(--primary-color) 4%);
}
.library-mode-tabs :deep(.n-tabs-nav) {
  padding: 3px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  background: color-mix(in srgb, var(--body-color) 78%, var(--primary-color) 5%);
}
.library-mode-tabs :deep(.n-tabs-tab) {
  min-width: 116px;
  padding: 7px 12px;
}
.mode-tab-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  font-weight: 600;
}
.song-cell {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
  padding: 2px 0;
}
.song-cell-title {
  font-weight: 600;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.song-cell-sub {
  font-size: 12px;
  line-height: 1.3;
  color: var(--text-color-3, #8a8f99);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.song-cell-line {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  line-height: 1.4;
}
.song-cell-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: default;
}
.song-action-group {
  flex-wrap: nowrap;
}
.song-icon-button {
  transition: transform .15s ease, box-shadow .15s ease;
}
.song-icon-button:hover {
  transform: translateY(-1px);
}
@media (max-width: 1100px) {
  .library-layout {
    flex-direction: column;
  }
  .library-side {
    flex: none;
    width: 100%;
  }
  .library-main {
    width: 100%;
  }
  .source-panel,
  .content-panel { box-shadow: none; }
}
</style>
