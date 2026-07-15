<template>
  <n-layout has-sider position="absolute" style="min-height: 100vh">
    <n-layout-sider
      bordered
      collapse-mode="width"
      :collapsed-width="64"
      :width="220"
      :collapsed="collapsed"
      show-trigger
      @collapse="collapsed = true"
      @expand="collapsed = false"
    >
      <div class="logo">
        <n-icon size="28" color="#18a058">
          <musical-notes />
        </n-icon>
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
    </n-layout-sider>

    <n-layout>
      <n-layout-header bordered class="header">
        <div class="header-left">
          <n-text strong>{{ routeTitle }}</n-text>
        </div>
        <n-space>
          <n-button quaternary circle @click="themeStore.toggle()">
            <template #icon>
              <n-icon>
                <moon v-if="themeStore.isDark" />
                <sunny v-else />
              </n-icon>
            </template>
          </n-button>
          <n-button quaternary @click="logout">退出</n-button>
        </n-space>
      </n-layout-header>

      <n-layout-content class="content" :class="{ 'player-content': activeKey === '/player' }" :native-scrollbar="false">
        <router-view />
      </n-layout-content>

      <n-layout-footer bordered class="footer">
        <global-player />
      </n-layout-footer>
    </n-layout>
  </n-layout>
</template>

<script setup>
import { computed, h, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NIcon, useMessage } from 'naive-ui'
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
} from '@vicons/ionicons5'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import GlobalPlayer from '@/components/GlobalPlayer.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const themeStore = useThemeStore()
const message = useMessage()
const collapsed = ref(false)

const routeTitle = computed(() => {
  const titles = {
    Dashboard: '概览',
    Download: '下载',
    Library: '曲库',
    Player: '播放器',
    Sources: '曲库',
    Logs: '操作日志',
    Settings: '设置',
  }
  return titles[route.name] || '拾音'
})

function icon(comp) {
  return () => h(NIcon, null, { default: () => h(comp) })
}

const menuOptions = [
  { label: '概览', key: '/', icon: icon(HomeOutline) },
  { label: '播放器', key: '/player', icon: icon(PlayCircleOutline) },
  { label: '下载', key: '/download', icon: icon(CloudDownloadOutline) },
  { label: '曲库', key: '/library', icon: icon(LibraryOutline) },
  { label: '日志', key: '/logs', icon: icon(DocumentTextOutline) },
  { label: '设置', key: '/settings', icon: icon(SettingsOutline) },
]

const activeKey = computed(() => {
  const p = route.path
  if (p.startsWith('/download') || p.startsWith('/search') || p.startsWith('/import')) return '/download'
  if (p.startsWith('/library') || p.startsWith('/sources') || p.startsWith('/webdav')) return '/library'
  if (p.startsWith('/player')) return '/player'
  if (p.startsWith('/logs')) return '/logs'
  if (p.startsWith('/settings')) return '/settings'
  return '/'
})

function onMenu(key) {
  router.push(key)
}

function logout() {
  auth.logout()
  message.success('已退出')
  router.push('/login')
}
</script>

<style scoped>
.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 16px 12px;
}
.logo-text {
  font-weight: 700;
  font-size: 16px;
}
.header {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
}
.content {
  padding: 16px 20px 96px;
}
.content.player-content {
  padding: 0 0 84px;
}
.content.player-content {
  padding: 0 0 84px;
}
.footer {
  position: sticky;
  bottom: 0;
  z-index: 20;
  padding: 0;
}
</style>
