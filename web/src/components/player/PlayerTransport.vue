<template>
  <div class="tp">
    <n-tooltip>
      <template #trigger>
        <n-button quaternary circle class="tp-btn pp-round-btn" :disabled="!player.current" aria-label="上一曲" @click="player.prev()">
          <n-icon class="tp-ico tp-ico--nav"><play-skip-back /></n-icon>
        </n-button>
      </template>
      上一曲
    </n-tooltip>
    <n-button type="primary" circle class="tp-play" :disabled="!player.current" aria-label="播放/暂停" @click="player.togglePlay()">
      <n-icon class="tp-ico tp-ico--play" :class="{ 'is-play': !player.playing }">
        <pause v-if="player.playing" />
        <play v-else />
      </n-icon>
    </n-button>
    <n-tooltip>
      <template #trigger>
        <n-button quaternary circle class="tp-btn pp-round-btn" :disabled="!player.current" aria-label="下一曲" @click="player.next()">
          <n-icon class="tp-ico tp-ico--nav"><play-skip-forward /></n-icon>
        </n-button>
      </template>
      下一曲
    </n-tooltip>
  </div>
</template>

<script setup>
import { NButton, NIcon, NTooltip } from 'naive-ui'
import {
  PlayerPause as Pause,
  PlayerPlay as Play,
  PlayerSkipBack as PlaySkipBack,
  PlayerSkipForward as PlaySkipForward,
} from '@vicons/tabler'
import { usePlayerStore } from '@/stores/player'

// 核心传输键（上一曲 / 播放 / 下一曲），卡片与沉浸式控制带共用。
// **尺寸不接收 prop**：播放键直径来自 PlayerPanel 的 --pp-play（48），
// 卡片曾传 46、沉浸带传 50，同一个按钮两种直径；侧键 36 与图标 24 / 0.55 同样走那套变量。
const player = usePlayerStore()
</script>

<style scoped>
.tp {
  display: flex;
  align-items: center;
  gap: 6px;
}
.tp-btn {
  color: var(--fg);
  transition: color var(--sp-dur-fast) var(--sp-ease-standard);
}
.tp-btn:hover {
  color: var(--fg);
}
/* 图标两档：侧键 24（ICON.lg）、播放键 = 直径 × 0.55（48 → 26） */
.tp-ico {
  font-size: var(--pp-ico-nav) !important;
}
.tp-ico--play {
  font-size: var(--pp-ico-play) !important;
}
.tp-play {
  /* 把 Naive 各交互态的颜色都钉到 --play-bg/--play-fg，避免 hover/focus 闪回品牌绿。
     注意必须 !important：n-button 把颜色**与尺寸**变量写在元素 inline style 上（Button.mjs 的 cssVars → style），
     类选择器（哪怕带 scoped 属性、优先级更高）也压不过 inline 声明 ——
     少了 !important 就会出现"静息态跟随封面主色、hover 变回品牌绿"的割裂。 */
  --n-width: var(--pp-play) !important;
  --n-height: var(--pp-play) !important;
  --n-icon-size: var(--pp-ico-play) !important;
  background: var(--play-bg) !important;
  color: var(--play-fg) !important;
  --n-color: var(--play-bg) !important;
  --n-color-hover: var(--play-bg) !important;
  --n-color-pressed: var(--play-bg) !important;
  --n-color-focus: var(--play-bg) !important;
  --n-text-color: var(--play-fg) !important;
  --n-text-color-hover: var(--play-fg) !important;
  --n-text-color-pressed: var(--play-fg) !important;
  --n-text-color-focus: var(--play-fg) !important;
  --n-border: 0 solid transparent;
  --n-border-hover: 0 solid transparent;
  --n-border-pressed: 0 solid transparent;
  --n-border-focus: 0 solid transparent;
  /* 点击波纹也吃 --n-ripple-color（同为 inline style），少了 !important 按下时会闪一圈品牌绿 */
  --n-ripple-color: transparent !important;
  /* 投影取自身主色做光晕（原来是无差别 rgba(0,0,0,.3)，浅色下像一块脏影子） */
  box-shadow:
    0 1px 2px rgba(15, 23, 42, 0.16),
    0 10px 26px -6px color-mix(in srgb, var(--play-bg) 46%, transparent);
  transition:
    transform var(--sp-dur-fast) var(--sp-ease-enter),
    box-shadow var(--sp-dur-fast) var(--sp-ease-standard);
}
.tp-play:hover {
  transform: translateY(-1px);
  box-shadow:
    0 1px 2px rgba(15, 23, 42, 0.18),
    0 14px 30px -6px color-mix(in srgb, var(--play-bg) 54%, transparent);
}
.tp-play:active {
  transform: translateY(0) scale(0.97);
}
.tp-play:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--play-bg) 72%, var(--fg));
  outline-offset: 3px;
}
/* Naive 的 n-button 用内部两个 span 画描边（primary 类型下是品牌绿），
   组件上的 border 覆盖管不到它们 —— 不显式灭掉就会在圆上留一圈绿边（看起来还毛糙）。 */
.tp-play :deep(.n-button__border),
.tp-play :deep(.n-button__state-border) {
  display: none;
}
.tp-play :deep(.n-button__content) {
  color: var(--play-fg);
}
.tp-play :deep(.n-icon) {
  color: var(--play-fg);
}
/* 播放三角的光学重心偏左，往右轻推一点才是"看起来居中"（暂停的双竖条对称，不用推） */
.tp-play :deep(.n-icon.is-play) {
  transform: translateX(2px);
}
@media (prefers-reduced-motion: reduce) {
  .tp-play,
  .tp-play:hover,
  .tp-play:active {
    transition: none;
    transform: none;
  }
}
</style>
