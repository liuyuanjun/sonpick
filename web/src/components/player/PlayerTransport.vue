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
      <n-icon :size="Math.round(size * 0.42)"><pause v-if="player.playing" /><play v-else /></n-icon>
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
  background: var(--play-bg) !important;
  color: var(--play-fg) !important;
  border: none !important;
  box-shadow: 0 10px 26px rgba(0, 0, 0, 0.32);
}
.tp-play :deep(.n-icon) {
  color: var(--play-fg);
}
</style>
