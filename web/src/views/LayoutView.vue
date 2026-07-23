<template>
  <n-layout has-sider position="absolute" style="min-height: 100vh">
    <n-layout-sider
      v-if="!isMobile"
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
        <n-space align="center">
          <task-center />
          <n-tooltip>
            <template #trigger>
              <n-button quaternary circle aria-label="切换主题" @click="themeStore.toggle()">
                <template #icon>
                  <n-icon>
                    <moon v-if="themeStore.isDark" />
                    <sunny v-else />
                  </n-icon>
                </template>
              </n-button>
            </template>
            切换主题
          </n-tooltip>
          <n-tooltip>
            <template #trigger>
              <n-button quaternary circle aria-label="修改密码" @click="showPasswordModal = true">
                <template #icon>
                  <n-icon><key-outline /></n-icon>
                </template>
              </n-button>
            </template>
            修改密码
          </n-tooltip>
          <n-tooltip>
            <template #trigger>
              <n-button quaternary circle aria-label="退出登录" @click="logout">
                <template #icon>
                  <n-icon><log-out-outline /></n-icon>
                </template>
              </n-button>
            </template>
            退出登录
          </n-tooltip>
        </n-space>
      </n-layout-header>

      <n-layout-content class="content" :class="{ 'player-content': activeKey === '/player', 'has-mini-player': player.showPlayer && !!player.current }">
        <router-view />
      </n-layout-content>

      <n-layout-footer v-show="player.showPlayer && player.current" bordered class="footer">
        <global-player />
      </n-layout-footer>

      <nav v-if="isMobile" class="mobile-tabs">
        <div
          v-for="t in tabs"
          :key="t.key"
          class="tab"
          :class="{ active: activeKey === t.key }"
          @click="onMenu(t.key)"
        >
          <n-icon size="20"><component :is="t.icon" /></n-icon>
          <span>{{ t.label }}</span>
        </div>
      </nav>
    </n-layout>
  </n-layout>

  <n-modal v-model:show="showPasswordModal" preset="dialog" title="修改密码" positive-text="确认修改" negative-text="取消" :loading="changingPassword" @positive-click="handleChangePassword">
    <n-space vertical>
      <n-input v-model:value="pwdForm.old" type="password" show-password-on="click" placeholder="当前密码" />
      <n-input v-model:value="pwdForm.new" type="password" show-password-on="click" placeholder="新密码（至少 6 位）" />
      <n-input v-model:value="pwdForm.confirm" type="password" show-password-on="click" placeholder="再次输入新密码" />
    </n-space>
  </n-modal>
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
} from '@vicons/ionicons5'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import { useIsMobile } from '@/composables/useIsMobile'
import { usePlayerStore } from '@/stores/player'
import GlobalPlayer from '@/components/GlobalPlayer.vue'
import TaskCenter from '@/components/TaskCenter.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const themeStore = useThemeStore()
const message = useMessage()
const collapsed = ref(false)
const isMobile = useIsMobile()
const player = usePlayerStore()
// Naive UI 不会全局注入 --n-* 变量，直接用主题变量才能区分激活态
const themeVars = useThemeVars()

// 移动端底部 Tab（日志入口暂不收进 Tab，可从设置页/直链访问）
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

const showPasswordModal = ref(false)
const changingPassword = ref(false)
const pwdForm = ref({ old: '', new: '', confirm: '' })

async function handleChangePassword() {
  if (!pwdForm.value.old || !pwdForm.value.new) {
    message.warning('请填写完整')
    return false
  }
  if (pwdForm.value.new.length < 6) {
    message.warning('新密码至少 6 位')
    return false
  }
  if (pwdForm.value.new !== pwdForm.value.confirm) {
    message.warning('两次新密码不一致')
    return false
  }
  changingPassword.value = true
  try {
    await auth.changePassword(pwdForm.value.old, pwdForm.value.new)
    message.success('密码已修改')
    pwdForm.value = { old: '', new: '', confirm: '' }
  } catch (err) {
    message.error(err.response?.data?.detail || '修改失败')
    changingPassword.value = false
    return false
  } finally {
    changingPassword.value = false
  }
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
  padding: 16px 20px 24px;
}
.content.has-mini-player {
  padding-bottom: 96px;
}
.content.player-content {
  padding: 0;
}
.content.player-content.has-mini-player {
  padding-bottom: 84px;
}
.footer {
  position: sticky;
  bottom: 0;
  z-index: 20;
  padding: 0;
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
  font-size: 11px;
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
  .header {
    padding: 0 12px;
  }
  .content {
    padding: 12px 12px calc(52px + env(safe-area-inset-bottom, 0px) + 12px);
  }
  .content.has-mini-player {
    padding-bottom: calc(60px + 52px + env(safe-area-inset-bottom, 0px) + 12px);
  }
  .content.player-content {
    padding: 0 0 calc(52px + env(safe-area-inset-bottom, 0px));
  }
  .content.player-content.has-mini-player {
    padding-bottom: calc(60px + 52px + env(safe-area-inset-bottom, 0px));
  }
}
</style>
