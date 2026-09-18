<template>
  <div class="art-wrap">
    <div class="halo" aria-hidden="true"></div>
    <div class="ring r2" aria-hidden="true"></div>
    <div class="ring" aria-hidden="true"></div>
    <svg v-if="playing" class="arc" viewBox="0 0 100 100" aria-hidden="true">
      <circle cx="50" cy="50" r="48" />
    </svg>
    <img
      v-if="cover && !broken"
      class="art"
      :src="cover"
      alt="cover"
      @error="broken = true"
      @load="broken = false"
    />
    <div v-else class="art placeholder">
      <span class="ph-ic"><n-icon><musical-notes /></n-icon></span>
    </div>
    <div class="sheen" aria-hidden="true"></div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { NIcon } from 'naive-ui'
import { MusicalNotes } from '@vicons/ionicons5'

// 封面主体：方形封面（不裁圆）+ 后方圆盘轮廓（细环）+ 一道 accent 播放弧。
// CSS 在 ~400px 直径上画不出可读的沟槽（会是一块黑泥），所以唱片只用「轮廓 + 一道弧」表达；
// 播放时只有那道弧缓慢转动，画不动。
// 尺寸纯 CSS：本组件占满父级宽度的正方形（aspect-ratio），父级用 width/clamp/cqw 控制大小。
const props = defineProps({
  cover: { type: String, default: '' },
  playing: { type: Boolean, default: false },
})
const broken = ref(false)
watch(
  () => props.cover,
  () => { broken.value = false },
)
</script>

<style scoped>
.art-wrap {
  position: relative;
  width: 100%;
  aspect-ratio: 1;
}
.halo {
  position: absolute;
  inset: -9%;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.52);
  filter: blur(9px);
  pointer-events: none;
}
.player-panel.light .halo {
  background: rgba(20, 30, 50, 0.13);
}
.ring {
  position: absolute;
  inset: -5.5%;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.09);
  pointer-events: none;
}
.ring.r2 {
  inset: -10.5%;
  border-color: rgba(255, 255, 255, 0.05);
}
.player-panel.light .ring { border-color: rgba(18, 22, 30, 0.10); }
.player-panel.light .ring.r2 { border-color: rgba(18, 22, 30, 0.06); }
.arc {
  position: absolute;
  inset: -4.5%;
  width: 109%;
  height: 109%;
  animation: spin 13s linear infinite;
  pointer-events: none;
}
.arc circle {
  fill: none;
  stroke: var(--accent, var(--sp-ui-primary));
  stroke-width: 0.7;
  stroke-linecap: round;
  stroke-dasharray: 26 282;
  opacity: 0.9;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.art {
  position: relative;
  width: 100%;
  height: 100%;
  border-radius: 16px;
  object-fit: cover;
  display: block;
  box-shadow:
    0 26px 60px rgba(0, 0, 0, 0.6),
    0 10px 32px color-mix(in srgb, var(--accent, var(--sp-ui-primary)) 10%, transparent),
    inset 0 0 0 1px rgba(255, 255, 255, 0.11);
}
.player-panel.light .art {
  box-shadow:
    0 22px 44px rgba(20, 30, 50, 0.2),
    inset 0 0 0 1px rgba(18, 22, 30, 0.06);
}
.art.placeholder {
  display: grid;
  place-items: center;
  background: var(--cover-bg, #2a2a2a);
  color: var(--fg-3);
}
.player-panel.light .art.placeholder {
  background: var(--cover-bg, #eef1f6);
}
.ph-ic {
  font-size: 40px;
  display: grid;
  place-items: center;
}
.sheen {
  position: absolute;
  inset: 0;
  border-radius: 16px;
  pointer-events: none;
  background: linear-gradient(115deg, rgba(255, 255, 255, 0.16) 0%, rgba(255, 255, 255, 0) 32%);
}
.player-panel.light .sheen {
  background: linear-gradient(115deg, rgba(255, 255, 255, 0.55) 0%, rgba(255, 255, 255, 0) 40%);
}
@media (prefers-reduced-motion: reduce) {
  .arc { animation: none; }
}
</style>
