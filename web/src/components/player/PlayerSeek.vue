<template>
  <div class="seek">
    <span class="t">{{ formatClock(player.currentTime) }}</span>
    <n-slider
      class="rail"
      :value="pct"
      :step="0.1"
      :tooltip="false"
      :disabled="!player.duration"
      aria-label="播放进度"
      @update:value="onSeek"
    />
    <span v-if="chip" class="chip">{{ chip }}</span>
    <span class="t">{{ formatClock(player.duration) }}</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { NSlider } from 'naive-ui'
import { usePlayerStore } from '@/stores/player'
import { formatClock } from '@/utils/format'
import { formatLabel } from '@/utils/media'

// 进度行：时间内联两端，中间放当前格式的标签（借飞牛：进度行中间放格式）。
// 拖动 → 通过 sonpick-seek 全局事件让真正的 <audio> 去 seek（与 GlobalPlayer 同源）。
const player = usePlayerStore()

const pct = computed(() => (player.duration ? (player.currentTime / player.duration) * 100 : 0))
const chip = computed(() => {
  const fmt = player.current?.preferred_version?.format
  return fmt ? formatLabel(fmt, '') : ''
})

function onSeek(value) {
  const duration = Number(player.duration)
  if (!Number.isFinite(duration) || duration <= 0) return
  const percent = Math.min(100, Math.max(0, Number(value) || 0))
  window.dispatchEvent(new CustomEvent('sonpick-seek', { detail: (percent / 100) * duration }))
}
</script>

<style scoped>
.seek {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr) auto 42px;
  align-items: center;
  gap: 10px;
}
.seek .t {
  font-size: 11.5px;
  color: var(--fg-3);
  font-variant-numeric: tabular-nums;
}
.seek .t:last-child {
  text-align: right;
}
.rail :deep(.n-slider) {
  --n-rail-height: 4px;
  --n-rail-color: var(--rail);
  --n-rail-color-hover: var(--rail);
  --n-fill-color: var(--accent, var(--sp-ui-primary));
  --n-fill-color-hover: var(--accent, var(--sp-ui-primary));
  --n-handle-color: #fff;
  --n-handle-size: 11px;
}
.chip {
  flex: none;
  font-size: 10.5px;
  letter-spacing: 0.03em;
  color: var(--accent, var(--sp-ui-primary));
  border: 1px solid color-mix(in srgb, var(--accent, var(--sp-ui-primary)) 40%, transparent);
  border-radius: 5px;
  padding: 1px 6px;
}
</style>
