<template>
  <n-config-provider
    :theme="themeStore.isDark ? darkTheme : lightTheme"
    :theme-overrides="themeOverrides"
  >
    <n-loading-bar-provider>
      <n-dialog-provider>
        <n-message-provider>
          <n-layout class="app-layout" position="absolute">
            <router-view />
          </n-layout>
        </n-message-provider>
      </n-dialog-provider>
    </n-loading-bar-provider>
  </n-config-provider>
</template>

<script setup>
import { onMounted } from 'vue'
import { darkTheme, lightTheme } from 'naive-ui'
import { useThemeStore } from '@/stores/theme'

const themeStore = useThemeStore()
onMounted(() => {
  themeStore.init()
})

// 品牌色覆盖：青绿 #10B981 主色 + 蓝紫 #6366F1 辅色，与 web/public/brand/ 保持一致
const themeOverrides = {
  common: {
    primaryColor: '#10B981',
    primaryColorHover: '#34D399',
    primaryColorPressed: '#059669',
    primaryColorSuppl: '#34D399',
    infoColor: '#6366F1',
    infoColorHover: '#818CF8',
    infoColorPressed: '#4F46E5',
    infoColorSuppl: '#818CF8',
    successColor: '#10B981',
    warningColor: '#F59E0B',
    errorColor: '#EF4444',
    bodyColor: '#0B0C10',
    cardColor: '#14161C',
    borderColor: '#23262F',
    textColorBase: '#ECEEF2',
    textColor1: '#ECEEF2',
    textColor2: '#B6BECB',
    textColor3: '#8B95A5',
  },
}
</script>

<style>
html, body, #app {
  height: 100%;
  margin: 0;
  padding: 0;
}
.app-layout {
  min-height: 100vh;
}
</style>
