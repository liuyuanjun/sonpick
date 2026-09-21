<template>
  <div class="art-wrap" :class="{ record }">
    <!-- 组合唱片（封面皮肤）：清晰可读的盘面，直径 = 封面 × 1.3，缓慢自转 -->
    <div v-if="record" class="disc" :class="{ spin: playing }" aria-hidden="true"></div>
    <!-- 干净的封面（叠层卡）：柔和光晕 + 两道细环 -->
    <template v-else>
      <div class="halo" aria-hidden="true"></div>
      <div class="ring r2" aria-hidden="true"></div>
      <div class="ring" aria-hidden="true"></div>
    </template>
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

// 封面主体。两种形态：
//   record=true （叠层卡 / 封面皮肤）：方形封面 + 后方一张**清晰可读的沟槽唱片**
//     （盘面直径 = 封面 × --disc-ratio，默认 1.3）+ accent 播放弧。播放时盘面缓慢自转，封面不动。
//   record=false（历史形态）：方形封面 + 柔和光晕 + 两道细环 + accent 播放弧
// 尺寸纯 CSS：本组件占满父级宽度的正方形（aspect-ratio），父级用 width/clamp/cqh 控制大小。
// 注意：盘面是**相对本组件宽度**出血的，父级必须为这段出血留出空间，
// 否则盘面会压住相邻内容（叠层卡曾因此压住歌曲名行，见 PlayerSkin 的 .c-art）。
const props = defineProps({
  cover: { type: String, default: '' },
  playing: { type: Boolean, default: false },
  record: { type: Boolean, default: false },
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

/* ---- 组合唱片（封面皮肤） ---- */
.disc {
  position: absolute;
  /* 盘面直径 = 封面 × --disc-ratio（默认 1.3 → 封面四边各露出 15% 的盘面）。
     比例由外层皮肤注入（叠层卡要用它反算「盘面 = 卡宽」时的封面尺寸），
     两处必须同源，所以只在这里给兜底值。 */
  inset: calc((1 - var(--disc-ratio, 1.3)) * 50%);
  border-radius: var(--sp-radius-circle);
  /* 外投影留在这一层（不自转），沟槽/高光/内阴影画在 .disc::before 上（自转）。
     box-shadow 与 filter 都在元素自身坐标系里绘制，挂在自转层上会跟着转 ——
     实测 0°→90° 时投影从下方转到左方（亮色下肉眼可见）。 */
  box-shadow: 0 28px 64px rgba(0, 0, 0, 0.6);
  pointer-events: none;
}
.disc::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: var(--sp-radius-circle);
  background:
    conic-gradient(from 205deg at 50% 50%, rgba(255, 255, 255, 0.16), rgba(255, 255, 255, 0) 62deg, rgba(255, 255, 255, 0) 296deg, rgba(255, 255, 255, 0.12) 360deg),
    repeating-radial-gradient(circle at center, #1a1b20 0 1.5px, #0c0d10 1.5px 3px);
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.1),
    inset 0 0 70px rgba(0, 0, 0, 0.45);
}
.disc.spin::before {
  animation: spin 22s linear infinite;
}
.player-panel.light .disc {
  box-shadow: 0 20px 44px rgba(20, 30, 50, 0.18);
}
.player-panel.light .disc::before {
  background:
    conic-gradient(from 205deg at 50% 50%, rgba(255, 255, 255, 0.95), rgba(255, 255, 255, 0) 62deg, rgba(255, 255, 255, 0) 296deg, rgba(255, 255, 255, 0.7)),
    repeating-radial-gradient(circle at center, #eaedf4 0 1.5px, #d2d8e4 1.5px 3px);
  box-shadow: inset 0 0 0 1px rgba(18, 22, 30, 0.08);
}

/* ---- 干净封面（叠层卡） ---- */
.halo {
  position: absolute;
  inset: -9%;
  border-radius: var(--sp-radius-circle);
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
  border-radius: var(--sp-radius-circle);
  border: 1px solid rgba(255, 255, 255, 0.09);
  pointer-events: none;
}
.ring.r2 {
  inset: -10.5%;
  border-color: rgba(255, 255, 255, 0.05);
}
.player-panel.light .ring { border-color: rgba(18, 22, 30, 0.10); }
.player-panel.light .ring.r2 { border-color: rgba(18, 22, 30, 0.06); }

/* ---- 播放弧（正在播放的指示） ---- */
.arc {
  position: absolute;
  inset: -4.5%;
  width: 109%;
  height: 109%;
  animation: spin 13s linear infinite;
  pointer-events: none;
}
.art-wrap.record .arc {
  /* 组合唱片时，弧落在盘缘 */
  inset: -16.5%;
  width: 133%;
  height: 133%;
}
.arc circle {
  fill: none;
  stroke: var(--accent, var(--sp-ui-primary));
  stroke-width: 0.7;
  stroke-linecap: round;
  stroke-dasharray: 26 282;
  opacity: 0.9;
}
.art-wrap.record .arc circle {
  stroke-width: 0.5;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ---- 封面本体 ---- */
.art {
  position: relative;
  width: 100%;
  height: 100%;
  border-radius: var(--sp-radius-xl);
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
  font-size: var(--sp-icon-2xl);
  display: grid;
  place-items: center;
}
.sheen {
  position: absolute;
  inset: 0;
  border-radius: var(--sp-radius-xl);
  pointer-events: none;
  background: linear-gradient(115deg, rgba(255, 255, 255, 0.16) 0%, rgba(255, 255, 255, 0) 32%);
}
.player-panel.light .sheen {
  background: linear-gradient(115deg, rgba(255, 255, 255, 0.55) 0%, rgba(255, 255, 255, 0) 40%);
}
@media (prefers-reduced-motion: reduce) {
  .arc, .disc.spin::before { animation: none; }
}
</style>
