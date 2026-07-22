<template>
  <n-space vertical size="large" style="width: 100%" class="download-page" :class="{ mobile: isMobile }">
    <n-card :title="isMobile ? undefined : '下载'" class="main-card">
      <n-tabs
        v-model:value="activeTab"
        :type="isMobile ? 'segment' : 'line'"
        animated
        class="download-tabs"
      >
        <n-tab-pane name="search" tab="搜索下载">
          <search-download />
        </n-tab-pane>
        <n-tab-pane name="import" tab="导入歌单">
          <import-download />
        </n-tab-pane>
      </n-tabs>
    </n-card>

    <n-card title="曲库目录与命名规范" class="help-card">
      <n-space vertical size="small">
        <n-text depth="3" class="layout-help">
          推荐布局（与常见播放器 / NAS 曲库一致）：
        </n-text>
        <pre class="layout-sample">{{ layoutSample }}</pre>
        <ul class="layout-list">
          <li>歌曲文件：<code>艺术家/专辑/歌名.ext</code></li>
          <li>歌词：与音频同目录、同名 <code>歌名.lrc</code>（也可 <code>.txt</code>）</li>
          <li>专辑封面：专辑目录下优先 <code>cover.jpg</code>（兼认 folder / front / AlbumArt）</li>
          <li>艺术家图：艺术家目录下 <code>artist.jpg</code>（兼认 folder.jpg）</li>
        </ul>
        <n-text depth="3" class="layout-help">
          元数据读取顺序：① 内嵌标签/封面/歌词 → ② 目录侧车 → ③ 库内已保存路径 → ④ 网络补全（可选）。
          Favorite、Downloads 等收藏夹目录不会被识别为艺术家。
          新下载会自动按「艺术家/专辑」落盘；旧库请到「歌曲源」对对应源执行「整理」（先预览再确认）与「刮削」补全元数据。
        </n-text>
      </n-space>
    </n-card>
  </n-space>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SearchDownload from '@/components/download/SearchDownload.vue'
import ImportDownload from '@/components/download/ImportDownload.vue'
import { useIsMobile } from '@/composables/useIsMobile'

const route = useRoute()
const router = useRouter()
const isMobile = useIsMobile()
const activeTab = ref(route.query.tab === 'import' ? 'import' : 'search')

const layoutSample = `艺术家/
  artist.jpg
  专辑/
    cover.jpg
    歌名.flac
    歌名.lrc`

watch(activeTab, (v) => {
  router.replace({ path: '/download', query: v === 'import' ? { tab: 'import' } : {} })
})
</script>

<style scoped>
.layout-help {
  line-height: 1.6;
  font-size: 13px;
}
.layout-sample {
  margin: 0;
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(128, 128, 128, 0.12);
  font-size: 12px;
  line-height: 1.5;
  overflow-x: auto;
}
.layout-list {
  margin: 0;
  padding-left: 1.2em;
  font-size: 13px;
  line-height: 1.7;
}
.layout-list code,
.layout-help code {
  font-size: 12px;
}
@media (max-width: 768px) {
  .main-card :deep(.n-card__content) {
    padding-top: 12px;
  }
  .download-tabs :deep(.n-tabs-nav) {
    padding: 3px;
    border: 1px solid var(--n-border-color);
    border-radius: 10px;
    background: color-mix(in srgb, var(--n-body-color) 78%, var(--n-primary-color) 5%);
  }
  .download-tabs :deep(.n-tabs-tab) {
    flex: 1;
    justify-content: center;
  }
  .download-tabs :deep(.n-tab-pane) {
    padding-top: 14px;
  }
  .help-card :deep(.n-card-header) {
    padding-bottom: 8px;
  }
  .layout-list {
    padding-left: 1.1em;
  }
}
</style>
