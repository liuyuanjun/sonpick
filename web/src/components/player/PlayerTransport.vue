<template>
  <div class="tp">
    <n-tooltip>
      <template #trigger>
        <n-button quaternary circle class="tp-btn" :disabled="!player.current" aria-label="上一曲" @click="player.prev()">
          <n-icon :size="22"><play-skip-back /></n-icon>
        </n-button>
      </template>
      上一曲
    </n-tooltip>
    <n-button type="primary" circle class="tp-play" :style="{ width: `${size}px`, height: `${size}px` }" :disabled="!player.current" aria-label="播放/暂停" @click="player.togglePlay()">
      <n-icon :size="Math.round(size * 0.5)" :class="{ 'is-play': !player.playing }">
        <pause v-if="player.playing" />
        <play v-else />
      </n-icon>
    </n-button>
    <n-tooltip>
      <template #trigger>
        <n-button quaternary circle class="tp-btn" :disabled="!player.current" aria-label="下一曲" @click="player.next()">
          <n-icon :size="22"><play-skip-forward /></n-icon>
        </n-button>
      </template>
      下一曲
    </n-tooltip>
  </div>
</template>

<script setup>
import { NButton, NIcon, NTooltip } from 'naive-ui'
import { Pause, Play, PlaySkipBack, PlaySkipForward } from '@vicons/ionicons5'
import { usePlayerStore } from '@/stores/player'

// 核心传输键（上一曲 / 播放 / 下一曲），卡片与沉浸式控制带共用。
defineProps({ size: { type: Number, default: 44 } })
const player = usePlayerStore()
</script>

<style scoped>
.tp {
  display: flex;
  align-items: center;
  gap: 8px;
}
.tp-btn {
  color: var(--fg);
}
.tp-play {
  /* 把 Naive 各交互态的颜色都钉到 --play-bg/--play-fg，避免 hover/focus 闪回品牌绿 */
  --n-color: var(--play-bg);
  --n-color-hover: var(--play-bg);
  --n-color-pressed: var(--play-bg);
  --n-color-focus: var(--play-bg);
  --n-text-color: var(--play-fg);
  --n-text-color-hover: var(--play-fg);
  --n-text-color-pressed: var(--play-fg);
  --n-text-color-focus: var(--play-fg);
  --n-border: 0 solid transparent;
  --n-border-hover: 0 solid transparent;
  --n-border-pressed: 0 solid transparent;
  --n-border-focus: 0 solid transparent;
  --n-ripple-color: transparent;
  background: var(--play-bg);
  color: var(--play-fg);
  box-shadow: 0 10px 26px rgba(0, 0, 0, 0.3);
}
/* Naive 的 n-button 用内部两个 span 画描边（primary 类型下是品牌绿），
   组件上的 border 覆盖管不到它们 —— 不显式灭掉就会在圆上留一圈绿边（看起来还毛糙）。 */
.tp-play :deep(.n-button__border),
.tp-play :deep(.n-button__state-border) {
  display: none;
}
.tp-play :deep(.n-icon) {
  color: var(--play-fg);
}
/* 播放三角的光学重心偏左，往右轻推一点才是"看起来居中"（暂停的双竖条对称，不用推） */
.tp-play :deep(.n-icon.is-play) {
  transform: translateX(2px);
}
</style>
