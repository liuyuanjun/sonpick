<template>
  <n-space vertical size="large" style="width: 100%">
    <n-grid cols="1 s:2 m:4" responsive="screen" :x-gap="12" :y-gap="12">
      <n-gi>
        <n-card class="stat-card" size="small">
          <n-text depth="3">歌曲总数</n-text>
          <div class="stat-num">{{ stats.song_count || 0 }}</div>
        </n-card>
      </n-gi>
      <n-gi>
        <n-card class="stat-card" size="small">
          <n-text depth="3">艺术家 / 专辑</n-text>
          <div class="stat-num">{{ stats.artist_count || 0 }} / {{ stats.album_count || 0 }}</div>
        </n-card>
      </n-gi>
      <n-gi>
        <n-card class="stat-card" size="small">
          <n-text depth="3">收藏 / 歌单</n-text>
          <div class="stat-num">{{ stats.favorite_count || 0 }} / {{ stats.playlist_count || 0 }}</div>
        </n-card>
      </n-gi>
      <n-gi>
        <n-card class="stat-card" size="small">
          <n-text depth="3">任务 pending / running</n-text>
          <div class="stat-num">{{ tasks.pending || 0 }} / {{ tasks.running || 0 }}</div>
        </n-card>
      </n-gi>
    </n-grid>

    <n-grid cols="1 m:2" responsive="screen" :x-gap="12" :y-gap="12">
      <n-gi>
        <n-card title="元信息完整度" size="small">
          <n-space vertical>
            <div>
              <div class="meta-row"><span>时长</span><span>{{ pct(meta.duration_pct) }}</span></div>
              <n-progress type="line" :percentage="pctNum(meta.duration_pct)" :show-indicator="false" />
            </div>
            <div>
              <div class="meta-row"><span>封面</span><span>{{ pct(meta.cover_pct) }}</span></div>
              <n-progress type="line" :percentage="pctNum(meta.cover_pct)" status="success" :show-indicator="false" />
            </div>
            <div>
              <div class="meta-row"><span>歌词</span><span>{{ pct(meta.lyrics_pct) }}</span></div>
              <n-progress type="line" :percentage="pctNum(meta.lyrics_pct)" status="info" :show-indicator="false" />
            </div>
          </n-space>
        </n-card>
      </n-gi>
      <n-gi>
        <n-card title="源统计" size="small">
          <n-empty v-if="!(stats.sources || []).length" description="暂无歌曲源" />
          <n-space v-else vertical>
            <div v-for="s in stats.sources" :key="s.id" class="source-row">
              <n-space align="center">
                <n-tag size="small" :type="s.type === 'webdav' ? 'info' : 'success'">{{ s.type === 'webdav' ? 'WebDAV' : '本地' }}</n-tag>
                <n-text strong>{{ s.name }}</n-text>
                <n-tag v-if="s.is_default_upload" size="small" type="warning">默认上传</n-tag>
              </n-space>
              <n-text depth="3">{{ s.song_count || 0 }} 首 · {{ statusLabel(s.connection_status) }}</n-text>
            </div>
          </n-space>
        </n-card>
      </n-gi>
    </n-grid>

    <n-card title="快捷入口" size="small">
      <n-space>
        <n-button type="primary" @click="$router.push('/download')">去下载</n-button>
        <n-button type="success" @click="$router.push('/player')">打开播放器</n-button>
        <n-button type="info" @click="$router.push('/sources')">管理歌曲源</n-button>
        <n-button @click="$router.push('/library')">浏览曲库</n-button>
      </n-space>
    </n-card>
  </n-space>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { fetchLibraryStats } from '@/api/music'

const message = useMessage()
const stats = ref({
  song_count: 0,
  artist_count: 0,
  album_count: 0,
  favorite_count: 0,
  playlist_count: 0,
  meta_completeness: {},
  sources: [],
  tasks: {},
})

const meta = computed(() => stats.value.meta_completeness || {})
const tasks = computed(() => stats.value.tasks || {})

function pctNum(v) {
  const n = Number(v || 0)
  if (n <= 1) return Math.round(n * 100)
  return Math.round(n)
}

function pct(v) {
  return `${pctNum(v)}%`
}

function statusLabel(s) {
  return ({ ok: '连通正常', failed: '连通失败', not_configured: '未配置', unknown: '未知' })[s] || s || '未知'
}

async function load() {
  try {
    const res = await fetchLibraryStats()
    stats.value = res.data || stats.value
  } catch (err) {
    message.error(err.response?.data?.detail || '加载概览失败')
  }
}

onMounted(load)
</script>

<style scoped>
.stat-card {
  min-height: 96px;
}
.stat-num {
  margin-top: 8px;
  font-size: 28px;
  font-weight: 700;
  letter-spacing: 0.5px;
}
.meta-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
}
.source-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid rgba(128, 128, 128, 0.15);
}
.source-row:last-child {
  border-bottom: none;
}
</style>
