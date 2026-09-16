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

/*
  悬浮播放胶囊的几何单一真相源：GlobalPlayer 的定位、各页面底部留白、
  播放器页高度计算全部从这里取值，避免四处硬编码漂移。
*/
:root {
  --gp-bar-height: 84px;
  --gp-bar-gap: 24px;
  --gp-bottom-offset: 0px;
  --gp-reserve: calc(var(--gp-bar-height) + var(--gp-bar-gap) + var(--gp-bottom-offset) + 16px);
}
@media (max-width: 768px) {
  :root {
    --gp-bar-height: 60px;
    --gp-bar-gap: 10px;
    /* 移动端底部还有 52px 固定 Tab 栏与安全区 */
    --gp-bottom-offset: calc(52px + env(safe-area-inset-bottom, 0px));
  }
}

/* 大播放器抽屉打开时锁死底层滚动，避免滚动穿透到底层页面 */
html.sp-overlay-open,
html.sp-overlay-open body {
  overflow: hidden;
}
html.sp-overlay-open .n-layout-scroll-container {
  overflow: hidden !important;
}
</style>
