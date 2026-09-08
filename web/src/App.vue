<template>
  <n-config-provider
    :theme="themeStore.naiveTheme"
    :theme-overrides="themeStore.naiveOverrides"
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
import { useThemeStore } from '@/stores/theme'

// 颜色一律由 @/theme/tokens 派生：
// naiveOverrides 驱动 Naive 组件，--sp-ui-* CSS 变量由 store 注入到 :root 供业务样式消费。
// 禁止在本文件写死任何颜色（历史 bug：写死暗色 overrides 导致明亮模式失效）。
const themeStore = useThemeStore()
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
