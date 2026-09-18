<template>
  <div class="pu">
    <template v-for="c in show" :key="c">
      <!-- 音质优先 -->
      <n-tooltip v-if="c === 'quality'">
        <template #trigger>
          <n-button
            quaternary circle size="small" class="pu-btn quality"
            :class="{ on: player.losslessPreferred }"
            aria-label="音质优先"
            @click="player.toggleLosslessPreferred()"
          >
            <template #icon>
              <n-icon :size="15">
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
          <n-button quaternary circle size="small" class="pu-btn" :aria-label="player.modeLabel" @click="player.toggleMode()">
            <n-icon :size="17">
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
        <n-button quaternary circle size="small" class="pu-btn" :aria-label="player.muted ? '取消静音' : '静音'" @click="player.toggleMute()">
          <n-icon :size="17">
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
          <n-button quaternary circle size="small" class="pu-btn queue" :aria-label="queueLabel" @click="player.showQueue = !player.showQueue">
            <n-icon :size="17"><list-outline /></n-icon>
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
  DiamondOutline, FlashOutline, ListOutline, Reload, Repeat, Shuffle, VolumeHigh, VolumeMute,
} from '@vicons/ionicons5'
import { usePlayerStore } from '@/stores/player'

// 播放器的修饰/工具控制簇（音质 / 模式 / 音量 / 队列），卡片与沉浸式控制带共用。
// show 决定渲染哪几个、以及它们的顺序；compact 时音量只留图标（窄屏）。
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
  gap: 6px;
}
.pu-btn {
  color: var(--fg-2);
}
.quality.on {
  color: var(--accent, var(--sp-ui-primary)) !important;
}
.pu-vol {
  display: flex;
  align-items: center;
  gap: 4px;
}
/* class="pu-slider" 落在 n-slider 根元素上；Naive 把滑杆颜色变量写在 inline style 上，
   覆盖必须 !important。音量与进度统一用封面主题色，播放状态只有一种颜色语言。 */
.pu-vol .pu-slider {
  width: 92px;
  --n-rail-height: 3px;
  --n-handle-size: 10px;
  --n-rail-color: var(--rail-soft) !important;
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
  min-width: 14px;
  height: 14px;
  padding: 0 3px;
  border-radius: 999px;
  background: var(--accent, var(--sp-ui-primary));
  color: #fff;
  font-size: 9px;
  line-height: 14px;
  font-weight: 700;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.28);
  box-sizing: border-box;
}
</style>
