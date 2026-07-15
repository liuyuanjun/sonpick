<template>
  <n-config-provider :theme="themeStore.isDark ? darkTheme : lightTheme">
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
