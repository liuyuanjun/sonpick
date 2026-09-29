<template>
  <n-layout has-sider position="absolute" style="min-height: 100vh">
    <sp-sidebar
      v-if="!isMobile"
      v-model:collapsed="collapsed"
      :groups="navGroups"
      :active-key="activeKey"
      hotkey
      @navigate="onMenu"
    >
      <template #header="{ collapsed: folded }">
        <div class="logo" :class="{ collapsed: folded }">
          <img src="/brand/logo-mark-sm.png" alt="拾音" class="logo-mark" />
          <span class="logo-text sp-collapse-fade">拾音 Sonpick</span>
        </div>
      </template>

      <!-- 左下功能区：任务中心（高频常驻）+ 主题切换 + 用户入口 + 折叠开关。
           曲库 / 日志 / 设置已上移为导航「系统」组，这里不再保留系统管理下拉 -->
      <template #footer="{ collapsed: folded }">
        <div class="sider-footer" :class="{ collapsed: folded }">
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
            :options="userOptions"
            @select="onUserSelect"
          >
            <n-button quaternary circle aria-label="用户">
              <template #icon>
                <n-icon><person-circle-outline /></n-icon>
              </template>
            </n-button>
          </n-dropdown>
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
            {{ collapseHint }}
          </n-tooltip>
        </div>
      </template>
    </sp-sidebar>

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
  MusicalNotes,
  TimeOutline,
  CompassOutline,
} from '@vicons/ionicons5'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import { useIsMobile } from '@/composables/useIsMobile'
import { usePlayerStore } from '@/stores/player'
import GlobalPlayer from '@/components/GlobalPlayer.vue'
import TaskCenter from '@/components/TaskCenter.vue'
import GlobalPlayerDrawer from '@/components/player/GlobalPlayerDrawer.vue'
import ChangePasswordModal from '@/components/ChangePasswordModal.vue'
import SpSidebar from '@/components/nav/SpSidebar.vue'

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

/**
 * 导航树：分组 + 二级。
 * 把「我的音乐」六项收成 收藏 / 发现 两个二级组，是为了给侧边栏腾出容纳新入口的余量
 * （曲库 / 日志 / 设置已经上收进「系统」组），同时把两类不同的心智分开。
 * 父项的 key 只是分组标识，不参与路由 —— 点父项只展开，不跳转（叶子项才导航）。
 * icon 传组件本身，尺寸由 SpSidebar 按 token 控制，不再各处套一层 NIcon。
 */
const navGroups = [
  {
    key: 'music',
    label: '音乐',
    items: [
      { label: '概览', key: '/', icon: HomeOutline },
      { label: '下载', key: '/download', icon: CloudDownloadOutline },
      {
        label: '收藏',
        key: 'collection',
        icon: HeartOutline,
        children: [
          { label: '喜欢', key: '/player/favorites', icon: ListOutline },
          { label: '歌单', key: '/player/playlists', icon: ListOutline },
          { label: '歌曲', key: '/player/songs', icon: MusicalNotes },
        ],
      },
      {
        label: '发现',
        key: 'discover',
        icon: CompassOutline,
        children: [
          { label: '歌手', key: '/player/artists', icon: PersonOutline },
          { label: '专辑', key: '/player/albums', icon: DiscOutline },
          { label: '最近', key: '/player/history', icon: TimeOutline },
        ],
      },
    ],
  },
  {
    key: 'system',
    label: '系统',
    items: [
      { label: '曲库', key: '/library', icon: LibraryOutline },
      { label: '操作日志', key: '/logs', icon: DocumentTextOutline },
      { label: '设置', key: '/settings', icon: SettingsOutline },
    ],
  },
]

const userOptions = [
  { label: '修改密码', key: 'change-password', icon: () => h(NIcon, null, { default: () => h(KeyOutline) }) },
  { label: '退出登录', key: 'logout', icon: () => h(NIcon, null, { default: () => h(LogOutOutline) }) },
]

const collapseHint = computed(() => {
  const isMac = /Mac|iPhone|iPad/.test(navigator.userAgent)
  return `${collapsed.value ? '展开' : '收起'}侧边栏（${isMac ? '⌘B' : 'Ctrl+B'}）`
})

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
  flex: 0 0 auto;
  width: 28px;
  height: 28px;
  border-radius: var(--sp-radius-sm);
  display: block;
}
.logo-text {
  font-weight: var(--sp-fw-bold);
  font-size: var(--sp-fs-h3);
  white-space: nowrap;
}
/* 左下功能区：展开态横向一排（折叠开关靠右），折叠态竖向堆叠居中。
   由 SpSidebar 的 flex 列容器托底，不再绝对定位贴底，也就不再需要给菜单留 padding 规避遮挡 */
.sider-footer {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 8px 14px calc(10px + env(safe-area-inset-bottom, 0px));
  border-top: 1px solid v-bind('themeVars.borderColor');
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
.header {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--sp-layout-page-pad-x-mobile);
}
.content {
  padding: var(--sp-layout-page-pad-y) var(--sp-layout-page-pad-x) 24px;
  /* 内容限宽：1280 内容 + 两侧边距；超宽屏时左对齐（贴侧栏），右侧留白 */
  max-width: calc(var(--sp-layout-content-max) + 2 * var(--sp-layout-page-pad-x));
  /*
    sticky 穿透：n-layout-content 自身的 overflow:hidden 与其内部滚动容器的
    overflow-y:auto 会把内部 sticky 元素（列表分页栏吸附底部、表头吸附顶部）的
    滚动上下文截断在这里——而这个容器高度随内容增长、本身从不滚动，于是吸附失效。
    改为 visible 让 sticky 相对真正滚动的外层 n-layout 容器生效；
    该容器本就不产生滚动，此改动不改变任何页面的实际滚动行为。
  */
  overflow: visible;
}
.content > :deep(.n-layout-scroll-container) {
  overflow: visible;
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
