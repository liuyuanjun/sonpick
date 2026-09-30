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
import { computed, h, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NIcon, useMessage, useThemeVars } from 'naive-ui'
import {
  Home as HomeOutline,
  CloudDownload as CloudDownloadOutline,
  Books as LibraryOutline,
  PlayerPlay as PlayCircleOutline,
  FileText as DocumentTextOutline,
  Settings as SettingsOutline,
  Moon,
  Sun as Sunny,
  Logout as LogOutOutline,
  Key as KeyOutline,
  Check as CheckmarkOutline,
  ChevronLeft as ChevronBack,
  ChevronRight as ChevronForward,
  Heart as HeartOutline,
  List as ListOutline,
  UserCircle as PersonCircleOutline,
  Clock as TimeOutline,
} from '@vicons/tabler'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import { usePlaylistsStore } from '@/stores/playlists'
import { useSettingsStore } from '@/stores/settings'
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
const playlistsStore = usePlaylistsStore()
const settingsStore = useSettingsStore()
// Naive UI 不会全局注入 --n-* 变量，直接用主题变量才能区分激活态
const themeVars = useThemeVars()

// 侧边栏「歌单」子菜单要列前 5 个歌单；播放阈值也只有这里有全局的加载时机。
// 两个都用 ensure()：幂等、失败静默（拉不到不该让导航或播放报错）
onMounted(() => {
  playlistsStore.ensure()
  settingsStore.ensure()
})

// 移动端底部 Tab
const tabs = [
  { label: '概览', key: '/', icon: HomeOutline },
  { label: '播放器', key: '/player', icon: PlayCircleOutline },
  { label: '下载', key: '/download', icon: CloudDownloadOutline },
  { label: '曲源', key: '/library', icon: LibraryOutline },
  { label: '设置', key: '/settings', icon: SettingsOutline },
]

const routeTitle = computed(() => {
  const titles = {
    Dashboard: '概览',
    Download: '下载',
    Library: '曲源',
    Sources: '曲源',
    Logs: '日志',
    Settings: '设置',
    PlaylistManage: '管理歌单',
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
 * 父项（歌单 / 曲库）的 key 只是分组标识，不参与路由 —— 点父项只展开、不跳转。
 * 例外：「歌单」的 key 直接用 /player/playlists，这样落到歌单网格页（没带 ?pl=）时
 * 高亮能通过 `findTargetEl` 的父项回退落在它身上（见 SpSidebar）。
 * 子项不配 icon：二级项在 UI 上统一渲染成小圆点，配了也用不上。
 *
 * 「歌单」的子菜单是**纯动态数据**：手动排序后的前 5 个歌单，没有静态命令项
 * （「管理歌单」入口在歌单区页面头部，v0.15.2-rc13 起 —— 数据与命令不混在一列，
 * 且移动端没有侧边栏，命令入口必须在页面里才可达）。
 * 顺序由「管理歌单」页的拖拽决定，所以这里读的是 playlists store 的缓存。
 * 一个歌单都没有时不挂 children：父项退化成普通链接，点它直接进歌单区。
 */
const navGroups = computed(() => [
  {
    key: 'music',
    label: '音乐',
    items: [
      { label: '概览', key: '/', icon: HomeOutline },
      { label: '喜欢', key: '/player/favorites', icon: HeartOutline },
      { label: '最近', key: '/player/history', icon: TimeOutline },
      {
        label: '歌单',
        key: '/player/playlists',
        icon: ListOutline,
        children: playlistsStore.forSidebar.length
          ? playlistsStore.forSidebar.map((pl) => ({
              label: pl.name,
              key: `/player/playlists?pl=${pl.id}`,
            }))
          : undefined,
      },
      {
        label: '曲库',
        key: 'player-library',
        icon: LibraryOutline,
        children: [
          { label: '歌曲', key: '/player/songs' },
          { label: '歌手', key: '/player/artists' },
          { label: '专辑', key: '/player/albums' },
        ],
      },
      { label: '下载', key: '/download', icon: CloudDownloadOutline },
    ],
  },
  {
    key: 'system',
    label: '系统',
    items: [
      // 「曲源」= 现在的曲库页（那里管媒体源），只是导航换了叫法；
      // 「曲库」这个名字让给了音乐组里按 歌曲/歌手/专辑 浏览的入口
      { label: '曲源', key: '/library', icon: LibraryOutline },
      { label: '日志', key: '/logs', icon: DocumentTextOutline },
      { label: '设置', key: '/settings', icon: SettingsOutline },
    ],
  },
])

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
  // 「管理歌单」是歌单区的子页面（入口在歌单区页头），高亮落在「歌单」父项上
  if (p.startsWith('/playlists/manage')) return '/player/playlists'
  if (p.startsWith('/playlists')) return p
  if (p.startsWith('/download') || p.startsWith('/search') || p.startsWith('/import')) return '/download'
  if (p.startsWith('/library') || p.startsWith('/sources') || p.startsWith('/webdav')) return '/library'
  if (p.startsWith('/player')) {
    const sec = route.params.section
    const base = sec ? `/player/${sec}` : '/player/favorites'
    // 歌单深链：把 ?pl= 一并带进 activeKey，侧边栏子菜单项才能被标成当前项。
    // 不带 pl 时落到 /player/playlists，由 SpSidebar 回退高亮到「歌单」父项
    if (sec === 'playlists' && route.query.pl) return `${base}?pl=${route.query.pl}`
    return base
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
