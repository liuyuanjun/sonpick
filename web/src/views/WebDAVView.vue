<template>
  <n-space vertical size="large" style="width: 100%">
    <n-card :title="pageTitle">
      <template #header-extra>
        <n-space>
          <n-button size="small" @click="goBackSources">返回曲库</n-button>
          <n-button size="small" :loading="loading" @click="loadList">刷新</n-button>
        </n-space>
      </template>

      <n-alert v-if="!sourceId" type="warning" style="margin-bottom: 12px">
        请从「曲库」中的 WebDAV 源进入浏览。
      </n-alert>
      <n-alert v-else-if="error" type="error" style="margin-bottom: 12px">
        {{ error }}
      </n-alert>
      <n-text v-else depth="3" style="display:block;margin-bottom:12px;font-size:13px">
        当前源 ID：{{ sourceId }}；路径：/{{ currentPath || '' }}
      </n-text>

      <n-breadcrumb style="margin-bottom: 12px">
        <n-breadcrumb-item @click="navigateTo('')">根目录</n-breadcrumb-item>
        <n-breadcrumb-item
          v-for="(seg, idx) in pathSegments"
          :key="idx"
          @click="navigateTo(pathSegments.slice(0, idx + 1).join('/'))"
        >
          {{ seg }}
        </n-breadcrumb-item>
      </n-breadcrumb>

      <n-data-table
        :columns="columns"
        :data="entries"
        :loading="loading"
        :bordered="false"
        size="small"
        :row-key="(row) => row.path || row.name"
      />
    </n-card>
  </n-space>
</template>

<script setup>
import { computed, h, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NSpace, NTag, useMessage } from 'naive-ui'
import { listWebdav } from '@/api/music'
import { usePlayerStore } from '@/stores/player'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const player = usePlayerStore()

const loading = ref(false)
const error = ref('')
const entries = ref([])
const currentPath = ref('')

const sourceId = computed(() => {
  const q = route.query.source_id
  if (q == null || q === '') return null
  const n = Number(q)
  return Number.isFinite(n) ? n : null
})

const pageTitle = computed(() =>
  sourceId.value != null ? `WebDAV 浏览 · 源 #${sourceId.value}` : 'WebDAV 浏览'
)

const pathSegments = computed(() =>
  (currentPath.value || '').split('/').filter(Boolean)
)

function goBackSources() {
  router.push('/library')
}

function navigateTo(path) {
  currentPath.value = path || ''
  loadList()
}

async function loadList() {
  if (sourceId.value == null) {
    entries.value = []
    error.value = '缺少 source_id'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const res = await listWebdav(currentPath.value, sourceId.value)
    const data = res?.data ?? res
    entries.value = Array.isArray(data) ? data : data?.items || data?.entries || []
  } catch (e) {
    error.value = e?.response?.data?.detail || e.message || '加载失败'
    entries.value = []
  } finally {
    loading.value = false
  }
}

function isAudio(name = '') {
  return /\.(mp3|flac|m4a|wav|ogg|aac|ape|wma|opus)$/i.test(name)
}

function playRemote(row) {
  const path = row.path || row.name
  if (!path) return
  // 走后端代理流；播放器侧按项目既有 webdav 约定
  player.play?.({
    id: `webdav:${sourceId.value}:${path}`,
    title: row.name || path.split('/').pop(),
    artist: '',
    album: '',
    webdav_path: path,
    library_source_id: sourceId.value,
    source: 'webdav',
  })
  message.success('已发送到播放器')
}

const columns = [
  {
    title: '名称',
    key: 'name',
    ellipsis: { tooltip: true },
    render(row) {
      const name = row.name || row.path || ''
      if (row.is_dir || row.type === 'dir' || row.isdir) {
        return h(
          NButton,
          { text: true, type: 'primary', onClick: () => navigateTo(row.path || name) },
          { default: () => `📁 ${name}` }
        )
      }
      return name
    },
  },
  {
    title: '类型',
    key: 'type',
    width: 90,
    render(row) {
      const dir = row.is_dir || row.type === 'dir' || row.isdir
      return h(NTag, { size: 'small', type: dir ? 'info' : 'default' }, { default: () => (dir ? '目录' : '文件') })
    },
  },
  {
    title: '大小',
    key: 'size',
    width: 100,
    render(row) {
      const n = Number(row.size || 0)
      if (!n) return '-'
      if (n < 1024) return `${n} B`
      if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
      return `${(n / 1024 / 1024).toFixed(1)} MB`
    },
  },
  {
    title: '操作',
    key: 'actions',
    width: 100,
    render(row) {
      const dir = row.is_dir || row.type === 'dir' || row.isdir
      if (dir) return null
      if (!isAudio(row.name || row.path || '')) return null
      return h(
        NButton,
        { size: 'tiny', onClick: () => playRemote(row) },
        { default: () => '播放' }
      )
    },
  },
]

watch(sourceId, () => {
  currentPath.value = ''
  loadList()
})

onMounted(() => {
  loadList()
})
</script>
