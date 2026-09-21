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
        <n-tab-pane name="playlist" tab="歌单链接">
          <playlist-import />
        </n-tab-pane>
      </n-tabs>
    </n-card>

    <n-card class="help-card">
      <template #header>
        <div class="help-header">
          <span>曲库目录与命名规范</span>
          <n-button quaternary size="small" @click="showHelp = !showHelp">
            {{ showHelp ? '收起' : '展开' }}
          </n-button>
        </div>
      </template>

      <!--
        默认收起。这段规范说明是「参考文档」，不是每次下载都要读的操作指引；
        常驻展开会在操作页占用约 1/3 屏高，把下载区挤到上面（实测问题）。
        收起态的文案已自解释，需要查规范的场景才展开。
      -->
      <n-collapse-transition :show="showHelp">
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
      </n-collapse-transition>
    </n-card>
  </n-space>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SearchDownload from '@/components/download/SearchDownload.vue'
import ImportDownload from '@/components/download/ImportDownload.vue'
import PlaylistImport from '@/components/download/PlaylistImport.vue'
import { useIsMobile } from '@/composables/useIsMobile'

const route = useRoute()
const router = useRouter()
const isMobile = useIsMobile()
const activeTab = ref(['search', 'import', 'playlist'].includes(route.query.tab) ? route.query.tab : 'search')
/** 命名规范说明默认收起，见模板注释 */
const showHelp = ref(false)

const layoutSample = `艺术家/
  artist.jpg
  专辑/
    cover.jpg
    歌名.flac
    歌名.lrc`

watch(activeTab, (v) => {
  router.replace({ path: '/download', query: v === 'search' ? {} : { tab: v } })
})
</script>

<style scoped>
.layout-help {
  line-height: 1.6;
  font-size: var(--sp-fs-small);
}
.layout-sample {
  margin: 0;
  padding: 10px 12px;
  border-radius: var(--sp-radius-sm);
  background: rgba(128, 128, 128, 0.12);
  font-size: var(--sp-fs-caption);
  line-height: 1.5;
  overflow-x: auto;
}
.layout-list {
  margin: 0;
  padding-left: 1.2em;
  font-size: var(--sp-fs-small);
  line-height: 1.7;
}
.layout-list code,
.layout-help code {
  font-size: var(--sp-fs-caption);
}

.help-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-space-3);
  font-size: var(--sp-fs-h3);
  font-weight: var(--sp-fw-bold);
}

@media (max-width: 768px) {
  .main-card :deep(.n-card__content) {
    padding-top: 12px;
  }
  .download-tabs :deep(.n-tabs-nav) {
    padding: 3px;
    border: 1px solid var(--sp-ui-border);
    border-radius: var(--sp-radius-md);
    background: color-mix(in srgb, var(--sp-ui-body) 78%, var(--sp-ui-primary) 5%);
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
