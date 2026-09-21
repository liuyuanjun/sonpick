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
  font-size: var(--sp-fs-micro);
  color: var(--fg-3);
  font-variant-numeric: tabular-nums;
}
.seek .t:last-child {
  text-align: right;
}
/* 注意两件事：
   1) class="rail" 落在 n-slider 的根元素上，变量写在这里（写成 .rail .n-slider 不匹配）。
   2) Naive 把滑杆的**颜色类变量写在元素的 inline style 上**（几何变量不是），
      普通类选择器覆盖不掉，颜色必须 !important。 */
.rail {
  --n-rail-height: 4px;
  --n-handle-size: 11px;
  --n-rail-color: var(--rail) !important;
  --n-rail-color-hover: var(--rail) !important;
  --n-fill-color: var(--accent, var(--sp-ui-primary)) !important;
  --n-fill-color-hover: var(--accent, var(--sp-ui-primary)) !important;
  --n-handle-color: #fff !important;
}
.chip {
  flex: none;
  font-size: var(--sp-fs-micro);
  letter-spacing: 0.03em;
  color: var(--accent, var(--sp-ui-primary));
  border: 1px solid color-mix(in srgb, var(--accent, var(--sp-ui-primary)) 40%, transparent);
  border-radius: var(--sp-radius-xs);
  padding: 1px 6px;
}
</style>
