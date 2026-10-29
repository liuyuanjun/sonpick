<template>
  <div class="band">
    <player-seek />
    <div class="band-main">
      <!-- 移动端不显示迷你封面：整屏背景就是这张封面，再放一张 46px 缩略图只会挤掉歌名 -->
      <player-meta :show-cover="!isMobile" />
      <player-transport />
      <player-utils :compact="isMobile" />
    </div>
  </div>
</template>

<script setup>
import PlayerMeta from '@/components/player/PlayerMeta.vue'
import PlayerSeek from '@/components/player/PlayerSeek.vue'
import PlayerTransport from '@/components/player/PlayerTransport.vue'
import PlayerUtils from '@/components/player/PlayerUtils.vue'
import { useIsMobile } from '@/composables/useIsMobile'

// 沉浸式皮肤（唱片 / 纯歌词 / 纯封面）共用的底部控制带：
// 进度独占一行 + [正在播放 · 喜欢/歌单] [传输] [音质·模式·音量·队列]。
const isMobile = useIsMobile()
</script>

<style scoped>
.band {
  /* 左右 26 与顶栏的视觉左缘（图标 28）对齐；上下留白按 48px 播放键重新分配 */
  padding: 10px 26px 16px;
  display: grid;
  gap: 10px;
  flex: none;
  position: relative;
  z-index: 2;
}
.band-main {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: 16px;
  /* 与播放键同高：三栏在 48px 的行高里垂直居中，传输键不再比两侧高出一截 */
  min-height: var(--pp-play, 48px);
}
.band-main > :first-child {
  justify-self: start;
  max-width: 100%;
  min-width: 0;
}
.band-main > :last-child {
  justify-self: end;
}
@media (max-width: 768px) {
  .band {
    padding: 6px 16px calc(12px + env(safe-area-inset-bottom, 0px));
  }
  .band-main {
    grid-template-columns: minmax(0, 1fr) auto;
  }
  .band-main > :last-child {
    display: none;
  }
}
</style>
