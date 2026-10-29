<template>
  <div class="pu">
    <template v-for="c in show" :key="c">
      <!-- 音质优先 -->
      <n-tooltip v-if="c === 'quality'">
        <template #trigger>
          <n-button
            quaternary circle class="pu-btn pp-round-btn quality"
            :class="{ on: player.losslessPreferred }"
            aria-label="音质优先"
            @click="player.toggleLosslessPreferred()"
          >
            <template #icon>
              <n-icon class="pu-ico pu-ico--opt">
                <diamond-outline v-if="player.losslessPreferred" />
                <flash-outline v-else />
              </n-icon>
            </template>
          </n-button>
        </template>
        {{ player.losslessPreferred ? '无损优先：优先 FLAC' : '速度优先：优先 MP3，缺失时自动回退' }}
      </n-tooltip>
      <!-- 播放模式 -->
      <n-tooltip v-else-if="c === 'mode'">
        <template #trigger>
          <n-button quaternary circle class="pu-btn pp-round-btn" :aria-label="player.modeLabel" @click="player.toggleMode()">
            <n-icon class="pu-ico">
              <shuffle v-if="player.mode === 'shuffle'" />
              <repeat v-else-if="player.mode === 'loop'" />
              <reload v-else-if="player.mode === 'single'" />
              <list-outline v-else />
            </n-icon>
          </n-button>
        </template>
        {{ player.modeLabel }}
      </n-tooltip>
      <!-- 音量 -->
      <div v-else-if="c === 'volume'" class="pu-vol">
        <n-button
          quaternary circle class="pu-btn pp-round-btn"
          :class="{ on: player.muted }"
          :aria-label="player.muted ? '取消静音' : '静音'"
          @click="player.toggleMute()"
        >
          <n-icon class="pu-ico">
            <volume-mute v-if="player.muted || player.volume === 0" />
            <volume-high v-else />
          </n-icon>
        </n-button>
        <n-slider
          v-if="!compact"
          class="pu-slider"
          :value="player.muted ? 0 : player.volume * 100"
          :step="1"
          :tooltip="false"
          aria-label="音量"
          @update:value="(v) => player.setVolume(v / 100)"
        />
      </div>
      <!-- 队列 -->
      <n-tooltip v-else-if="c === 'queue'">
        <template #trigger>
          <n-button
            quaternary circle class="pu-btn pp-round-btn queue"
            :class="{ on: player.showQueue }"
            :aria-label="queueLabel"
            :aria-pressed="player.showQueue"
            @click="player.showQueue = !player.showQueue"
          >
            <n-icon class="pu-ico"><list-outline /></n-icon>
            <span v-if="player.queue?.length" class="queue-count">{{ player.queue.length }}</span>
          </n-button>
        </template>
        {{ queueLabel }}
      </n-tooltip>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { NButton, NIcon, NSlider, NTooltip } from 'naive-ui'
import {
  Diamond as DiamondOutline,
  Bolt as FlashOutline,
  List as ListOutline,
  Refresh as Reload,
  Repeat,
  ArrowsShuffle as Shuffle,
  Volume as VolumeHigh,
} from '@vicons/tabler'
import VolumeMute from '@/components/icons/VolumeOffIcon.vue'
import { usePlayerStore } from '@/stores/player'

// 播放器的修饰/工具控制簇（音质 / 模式 / 音量 / 队列），卡片与沉浸式控制带共用。
// show 决定渲染哪几个、以及它们的顺序；compact 时音量只留图标（窄屏）。
// 尺寸一律继承 PlayerPanel 的 --pp-*（按钮 36 / 图标 20），这里不再出现任何 px 图标值。
const props = defineProps({
  show: { type: Array, default: () => ['quality', 'mode', 'volume', 'queue'] },
  compact: { type: Boolean, default: false },
})
const player = usePlayerStore()
const queueLabel = computed(() => `队列 ${player.queue?.length || 0}`)
</script>

<style scoped>
.pu {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}
/* 让右侧工具簇可以收缩：卡片里它必须让出空间给音量滑杆，
   否则整行会溢出卡片（实测 scrollWidth 372 > 352，队列按钮压出卡片边缘） */
.pu-vol {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}
.pu-btn {
  color: var(--fg-2);
}
.pu-btn:hover {
  color: var(--fg);
}
.pu-btn.on {
  color: var(--accent, var(--sp-ui-primary)) !important;
}
.quality.on {
  color: var(--accent, var(--sp-ui-primary)) !important;
  background: color-mix(in srgb, var(--accent, var(--sp-ui-primary)) 12%, transparent) !important;
}
/* 图标：一档 20（--pp-ico）；闪电/钻石细线小墨量，同尺寸下显小 → +1px 光学补偿，
   图标槽宽同步 +1，否则 1px 溢出会让图标左右各偏半像素（与胶囊的 .gp-ico--optical 同规则） */
.pu-ico {
  font-size: var(--pp-ico) !important;
}
.pu-ico--opt {
  font-size: calc(var(--pp-ico) + 1px) !important;
}
.quality {
  --n-icon-size: calc(var(--pp-ico) + 1px) !important;
}
/* class="pu-slider" 落在 n-slider 根元素上；Naive 把滑杆颜色变量写在 inline style 上，
   覆盖必须 !important。音量与进度统一用封面主题色，播放状态只有一种颜色语言。
   几何（轨道 4 / 手柄 11）与 PlayerSeek 的进度条同规格。 */
.pu-slider {
  /* 基准 92（沉浸带宽裕时就是 92），卡片里空间不足时优先收缩到 44，按钮不缩 */
  width: auto;
  flex: 1 1 92px;
  max-width: 92px;
  min-width: 44px;
  --n-rail-height: 4px !important;
  --n-handle-size: 11px !important;
  --n-rail-color: var(--rail-soft) !important;
  --n-rail-color-hover: var(--rail-soft) !important;
  --n-fill-color: var(--accent, var(--sp-ui-primary)) !important;
  --n-fill-color-hover: var(--accent, var(--sp-ui-primary)) !important;
  --n-handle-color: #fff !important;
}
.queue {
  position: relative;
}
.queue-count {
  position: absolute;
  right: -2px;
  bottom: -1px;
  min-width: 15px;
  height: 15px;
  padding: 0 4px;
  border-radius: var(--sp-radius-pill);
  background: var(--accent, var(--sp-ui-primary));
  color: var(--play-fg, #fff);
  font-size: var(--sp-fs-micro);
  line-height: 15px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.28);
  box-sizing: border-box;
}
</style>
