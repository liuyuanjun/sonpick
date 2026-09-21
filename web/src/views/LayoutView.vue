<template>
  <n-layout has-sider position="absolute" style="min-height: 100vh">
    <n-layout-sider
      v-if="!isMobile"
      bordered
      collapse-mode="width"
      :collapsed-width="64"
      :width="220"
      :collapsed="collapsed"
      @collapse="collapsed = true"
      @expand="collapsed = false"
    >
      <div class="logo" :class="{ collapsed }">
        <img src="/brand/logo-mark-sm.png" alt="拾音" class="logo-mark" />
        <span v-if="!collapsed" class="logo-text">拾音 Sonpick</span>
      </div>
      <n-menu
        :collapsed="collapsed"
        :collapsed-width="64"
        :collapsed-icon-size="22"
        :options="menuOptions"
        :value="activeKey"
        @update:value="onMenu"
      />
      <!-- 左下功能区：任务中心（高频常驻）+ 主题切换 + 设置入口 + 用户入口 + 折叠开关。
           设置（曲库/日志/设置）与用户（改密码/退出）分两个图标：语义两类，各自一步直达 -->
      <div class="sider-footer" :class="{ collapsed }">
        <task-center />
        <n-dropdown trigger="click" :options="themeOptions" :value="themeStore.mode" @select="themeStore.setMode($event)">
          <n-button quaternary circle aria-label="主题模式">
            <template #icon>
              <n-icon>
                <moon v-if="themeStore.isDark" />
                <sunny v-else />
              </n-icon>
            </template>
          </n-button>
        </n-dropdown>
        <n-dropdown
          trigger="click"
          placement="top-start"
          :options="settingsOptions"
          @select="onMenu"
        >
          <n-button quaternary circle aria-label="系统管理">
            <template #icon>
              <n-icon><settings-outline /></n-icon>
            </template>
          </n-button>
        </n-dropdown>
        <n-dropdown
          trigger="click"
          placement="top-start"
          :options="userOptions"
          @select="onUserSelect"
        >
          <n-button quaternary circle aria-label="用户">
            <template #icon>
              <n-icon><person-circle-outline /></n-icon>
            </template>
          </n-button>
        </n-dropdown>
        <!-- 折叠开关收进左下功能区（替代 Naive 默认底边 trigger，避免与功能条争抢底缘） -->
        <n-tooltip>
          <template #trigger>
            <n-button
              quaternary
              circle
              :aria-label="collapsed ? '展开侧边栏' : '收起侧边栏'"
              @click="collapsed = !collapsed"
            >
              <template #icon>
                <n-icon>
                  <chevron-forward v-if="collapsed" />
                  <chevron-back v-else />
                </n-icon>
              </template>
            </n-button>
          </template>
          {{ collapsed ? '展开侧边栏' : '收起侧边栏' }}
        </n-tooltip>
      </div>
    </n-layout-sider>

    <n-layout>
      <!-- 移动端极简顶栏：仅保留页面标题与任务中心（下载进度需在任意页面可见） -->
      <n-layout-header v-if="isMobile" bordered class="header">
        <div class="header-left">
          <n-text strong>{{ routeTitle }}</n-text>
        </div>
        <task-center />
      </n-layout-header>

      <n-layout-content class="content" :class="{ 'has-mini-player': player.showPlayer && !!player.current }">
        <router-view />
      </n-layout-content>

      <nav v-if="isMobile" class="mobile-tabs">
        <div
          v-for="t in tabs"
          :key="t.key"
          class="tab"
          :class="{ active: isTabActive(t) }"
          @click="onMenu(t.key)"
        >
          <n-icon size="20"><component :is="t.icon" /></n-icon>
          <span>{{ t.label }}</span>
        </div>
      </nav>

      <!-- 全局大播放器抽屉：PlayerPanel / PlayerQueue 的唯一宿主 -->
      <global-player-drawer />
    </n-layout>
  </n-layout>

  <global-player />

  <change-password-modal v-model:show="showPasswordModal" />
</template>

<script setup>
import { computed, h, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NIcon, useMessage, useThemeVars } from 'naive-ui'
import {
  MusicalNotes,
  HomeOutline,
  CloudDownloadOutline,
  LibraryOutline,
  PlayCircleOutline,
  DocumentTextOutline,
  SettingsOutline,
  Moon,
  Sunny,
  LogOutOutline,
  KeyOutline,
  CheckmarkOutline,
  ChevronBack,
  ChevronForward,
  HeartOutline,
  ListOutline,
  PersonOutline,
  PersonCircleOutline,
  DiscOutline,
  TimeOutline,
} from '@vicons/ionicons5'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import { useIsMobile } from '@/composables/useIsMobile'
import { usePlayerStore } from '@/stores/player'
import GlobalPlayer from '@/components/GlobalPlayer.vue'
import TaskCenter from '@/components/TaskCenter.vue'
import GlobalPlayerDrawer from '@/components/player/GlobalPlayerDrawer.vue'
import ChangePasswordModal from '@/components/ChangePasswordModal.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const themeStore = useThemeStore()

// 主题三态：跟随系统 / 明亮 / 暗色。当前项在菜单里打勾
const THEME_MODES = [
  { key: 'system', label: '跟随系统' },
  { key: 'light', label: '明亮模式' },
  { key: 'dark', label: '暗色模式' },
]
const themeOptions = computed(() =>
  THEME_MODES.map((item) => ({
    key: item.key,
    label: item.label,
    render: () =>
      h('div', { style: 'display:flex;align-items:center;gap:8px;min-width:132px' }, [
        h('span', { style: 'flex:1' }, item.label),
        themeStore.mode === item.key
          ? h(NIcon, { size: 16, color: 'var(--sp-ui-primary)' }, { default: () => h(CheckmarkOutline) })
          : null,
      ]),
  })),
)
const message = useMessage()
const collapsed = ref(false)
const isMobile = useIsMobile()
const player = usePlayerStore()
// Naive UI 不会全局注入 --n-* 变量，直接用主题变量才能区分激活态
const themeVars = useThemeVars()

// 移动端底部 Tab
const tabs = [
  { label: '概览', key: '/', icon: HomeOutline },
  { label: '播放器', key: '/player', icon: PlayCircleOutline },
  { label: '下载', key: '/download', icon: CloudDownloadOutline },
  { label: '曲库', key: '/library', icon: LibraryOutline },
  { label: '设置', key: '/settings', icon: SettingsOutline },
]

const routeTitle = computed(() => {
  const titles = {
    Dashboard: '概览',
    Download: '下载',
    Library: '曲库',
    Sources: '曲库',
    Logs: '操作日志',
    Settings: '设置',
  }
  if (route.name === 'Player') {
    const sec = route.params.section || 'favorites'
    const secTitles = {
      favorites: '喜欢',
      playlists: '歌单',
      artists: '歌手',
      albums: '专辑',
      songs: '歌曲',
      history: '最近'
    }
    return secTitles[sec] || '播放器'
  }
  return titles[route.name] || '拾音'
})

function icon(comp) {
  return () => h(NIcon, null, { default: () => h(comp) })
}

// 扁平菜单：概览置顶作为首页，随后是我的音乐与下载；
// 曲库 / 日志 / 设置等低频系统入口收进左下账户抽屉，不再分区
const menuOptions = [
  { label: '概览', key: '/', icon: icon(HomeOutline) },
  { label: '喜欢', key: '/player/favorites', icon: icon(HeartOutline) },
  { label: '歌单', key: '/player/playlists', icon: icon(ListOutline) },
  { label: '歌手', key: '/player/artists', icon: icon(PersonOutline) },
  { label: '专辑', key: '/player/albums', icon: icon(DiscOutline) },
  { label: '歌曲', key: '/player/songs', icon: icon(MusicalNotes) },
  { label: '最近', key: '/player/history', icon: icon(TimeOutline) },
  { label: '下载', key: '/download', icon: icon(CloudDownloadOutline) },
]

const settingsOptions = [
  { label: '曲库', key: '/library', icon: icon(LibraryOutline) },
  { label: '操作日志', key: '/logs', icon: icon(DocumentTextOutline) },
  { label: '设置', key: '/settings', icon: icon(SettingsOutline) },
]

const userOptions = [
  { label: '修改密码', key: 'change-password', icon: icon(KeyOutline) },
  { label: '退出登录', key: 'logout', icon: icon(LogOutOutline) },
]

const activeKey = computed(() => {
  const p = route.path
  if (p.startsWith('/download') || p.startsWith('/search') || p.startsWith('/import')) return '/download'
  if (p.startsWith('/library') || p.startsWith('/sources') || p.startsWith('/webdav')) return '/library'
  if (p.startsWith('/player')) {
    const sec = route.params.section
    return sec ? `/player/${sec}` : '/player/favorites'
  }
  if (p.startsWith('/logs')) return '/logs'
  if (p.startsWith('/settings')) return '/settings'
  return '/'
})

// 移动端底部 Tab 的激活判定：播放器下的二级 section（/player/songs 等）也算播放器 Tab
function isTabActive(tab) {
  if (tab.key === '/player') return activeKey.value.startsWith('/player')
  return activeKey.value === tab.key
}

function onMenu(key) {
  router.push(key)
}

const showPasswordModal = ref(false)

function onUserSelect(key) {
  if (key === 'change-password') {
    showPasswordModal.value = true
    return
  }
  if (key === 'logout') {
    auth.logout()
    message.success('已退出')
    router.push('/login')
  }
}
</script>

<style scoped>
.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 16px 12px;
}
.logo.collapsed {
  justify-content: center;
  padding: 18px 0 12px;
}
.logo-mark {
  width: 28px;
  height: 28px;
  border-radius: var(--sp-radius-sm);
  display: block;
}
.logo-text {
  font-weight: 700;
  font-size: var(--sp-fs-h3);
}
/* 左下功能区：贴底常驻，展开态横向一排（折叠开关靠右），折叠态纵向堆叠居中 */
.sider-footer {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 8px 14px calc(10px + env(safe-area-inset-bottom, 0px));
  border-top: 1px solid v-bind('themeVars.borderColor');
  background: v-bind('themeVars.cardColor');
}
.sider-footer > :last-child {
  margin-left: auto;
}
.sider-footer.collapsed {
  flex-direction: column;
  gap: 4px;
  padding: 8px 0 10px;
}
.sider-footer.collapsed > :last-child {
  margin-left: 0;
  margin-top: 4px;
}
/* 功能条绝对定位贴底，给菜单底部留出对应空间避免遮挡末项 */
:deep(.n-menu) {
  padding-bottom: 54px;
}
:deep(.n-menu.n-menu--collapsed) {
  padding-bottom: 196px;
}
.header {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--sp-layout-page-pad-x-mobile);
}
.content {
  padding: var(--sp-layout-page-pad-y) var(--sp-layout-page-pad-x) 24px;
  /* 内容限宽居中：1280 内容 + 两侧边距一起居中；仅在 >1500px 大屏触发 */
  max-width: calc(var(--sp-layout-content-max) + 2 * var(--sp-layout-page-pad-x));
  margin: 0 auto;
}
/* 悬浮播放胶囊浮在内容之上，为其预留底部空间；几何统一由 :root 的 --gp-* 变量驱动 */
.content.has-mini-player {
  padding-bottom: var(--gp-reserve);
}
.mobile-tabs {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 1100;
  display: flex;
  height: calc(52px + env(safe-area-inset-bottom, 0px));
  padding-bottom: env(safe-area-inset-bottom, 0px);
  box-sizing: border-box;
  background: color-mix(in srgb, v-bind('themeVars.cardColor') 92%, transparent);
  border-top: 1px solid v-bind('themeVars.borderColor');
  backdrop-filter: blur(14px);
}
.tab {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  font-size: var(--sp-fs-micro);
  color: v-bind('themeVars.textColor3');
  cursor: pointer;
  user-select: none;
}
.tab.active {
  color: v-bind('themeVars.primaryColor');
  font-weight: 600;
  background: color-mix(in srgb, v-bind('themeVars.primaryColor') 10%, transparent);
}

@media (max-width: 768px) {
  .content {
    padding: var(--sp-layout-page-pad-y-mobile) var(--sp-layout-page-pad-x-mobile) calc(52px + env(safe-area-inset-bottom, 0px) + 12px);
  }
  .content.has-mini-player {
    padding-bottom: var(--gp-reserve);
  }
}
</style>
