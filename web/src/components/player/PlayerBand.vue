<template>
  <div class="band">
    <player-seek />
    <div class="band-main">
      <player-meta />
      <player-transport :size="50" />
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
  padding: 8px 26px 14px;
  display: grid;
  gap: 8px;
  flex: none;
  position: relative;
  z-index: 2;
}
.band-main {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: 16px;
  min-height: 52px;
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
