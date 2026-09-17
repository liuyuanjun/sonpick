<template>
  <div class="stage-body">
    <!-- cover-only -->
    <div
      v-if="view === 'cover'"
      key="cover"
      class="cover-stage"
      @click="$emit('update:view', 'blend')"
    >
      <div class="vinyl-frame">
        <div class="vinyl" :class="{ spinning: playing }">
          <div class="vinyl-ring"></div>
          <div class="vinyl-ring thin"></div>
          <img
            v-if="cover && !coverBroken"
            :src="cover"
            class="vinyl-cover"
            alt="cover"
            @error="coverBroken = true"
            @load="coverBroken = false"
          />
          <div v-else class="vinyl-cover placeholder">
            <n-icon size="42"><musical-notes /></n-icon>
          </div>
          <div class="vinyl-hole"></div>
        </div>
      </div>
      <div class="tap-hint">点击切换 · 歌词叠层</div>
    </div>

    <!-- blend: blurred vinyl under lyrics -->
    <div v-else-if="view === 'blend'" key="blend" class="blend-stage">
      <div class="blend-bg" aria-hidden="true">
        <div class="vinyl-frame dim">
          <div class="vinyl" :class="{ spinning: playing }">
            <div class="vinyl-ring"></div>
            <div class="vinyl-ring thin"></div>
            <img
              v-if="cover && !coverBroken"
              :src="cover"
              class="vinyl-cover"
              alt=""
              @error="coverBroken = true"
            />
            <div v-else class="vinyl-cover placeholder">
              <n-icon size="42"><musical-notes /></n-icon>
            </div>
            <div class="vinyl-hole"></div>
          </div>
        </div>
        <div class="blend-veil"></div>
      </div>
      <div class="blend-lyrics">
        <lyrics-view
          :lines="lines"
          :active-index="activeIndex"
          :font-size="fontSize"
          :immersive="true"
          :empty-title="emptyTitle"
          :empty-description="emptyDescription"
          @seek="$emit('seek', $event)"
        />
      </div>
    </div>

    <!-- lyrics-only -->
    <div v-else key="lyrics" class="lyrics-stage">
      <lyrics-view
        :lines="lines"
        :active-index="activeIndex"
        :font-size="fontSize"
        :immersive="true"
        :empty-title="emptyTitle"
        :empty-description="emptyDescription"
        @seek="$emit('seek', $event)"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { NIcon } from 'naive-ui'
import { MusicalNotes } from '@vicons/ionicons5'
import LyricsView from '@/components/player/LyricsView.vue'

// 舞台视图（黑胶 / 叠层 / 纯歌词）。纯展示组件：不读 store，靠 props 驱动，
// 封面主色、播放进度等由 PlayerPanel 统一编排。
const props = defineProps({
  view: { type: String, default: 'cover' },
  cover: { type: String, default: '' },
  playing: { type: Boolean, default: false },
  lines: { type: Array, default: () => [] },
  activeIndex: { type: Number, default: -1 },
  fontSize: { type: Number, default: 18 },
  // 该歌曲是否已标记为纯音乐，决定空态文案
  instrumental: { type: Boolean, default: false },
})

defineEmits(['update:view', 'seek'])

const coverBroken = ref(false)

const emptyTitle = computed(() => (props.instrumental ? '纯音乐' : '暂无歌词'))
const emptyDescription = computed(() =>
  props.instrumental ? '该歌曲已标记为纯音乐' : '可点击上方获取歌词',
)

watch(
  () => props.cover,
  () => {
    coverBroken.value = false
  },
)
</script>

<style scoped>
.stage-body {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  position: relative;
  z-index: 1;
}

/* ---------- vinyl geometry ---------- */
.cover-stage {
  flex: 1;
  min-height: 0;
  position: relative;
  overflow: hidden;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 8px 14px;
  box-sizing: border-box;
}
.vinyl-frame {
  width: min(92%, 360px);
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  filter: var(--vinyl-shadow);
}
@supports (width: 1cqh) {
  .stage-body {
    container-type: size;
  }
  .cover-stage .vinyl-frame {
    width: min(94cqw, 88cqh, 380px);
  }
  .blend-stage .vinyl-frame {
    width: min(100cqw, 100cqh, 520px);
  }
}
.vinyl {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  position: relative;
  background:
    radial-gradient(circle at 35% 30%, rgba(255, 255, 255, 0.08), transparent 40%),
    repeating-radial-gradient(circle at center, var(--vinyl-bg-a) 0 2px, var(--vinyl-bg-b) 2px 4px);
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.05),
    inset 0 0 40px rgba(0, 0, 0, 0.45);
}
.player-panel.light .vinyl {
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.7),
    inset 0 0 30px rgba(255, 255, 255, 0.35),
    0 1px 0 rgba(255, 255, 255, 0.6);
}
.vinyl.spinning {
  animation: spin 18s linear infinite;
}
.vinyl-ring {
  position: absolute;
  inset: 7%;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.05);
  box-shadow: inset 0 0 0 14px rgba(255, 255, 255, 0.015);
  pointer-events: none;
}
.player-panel.light .vinyl-ring {
  border-color: rgba(18, 22, 30, 0.05);
  box-shadow: inset 0 0 0 14px rgba(255, 255, 255, 0.25);
}
.vinyl-ring.thin {
  inset: 16%;
  border-color: rgba(255, 255, 255, 0.04);
  box-shadow: none;
}
.player-panel.light .vinyl-ring.thin {
  border-color: rgba(18, 22, 30, 0.05);
}
.vinyl-cover {
  position: absolute;
  inset: 16.666%;
  width: 66.666%;
  height: 66.666%;
  margin: auto;
  border-radius: 50%;
  object-fit: cover;
  background: var(--cover-bg);
  box-shadow:
    0 0 0 3px rgba(0, 0, 0, 0.38),
    0 12px 30px rgba(0, 0, 0, 0.34);
}
.player-panel.light .vinyl-cover {
  box-shadow:
    0 0 0 2px rgba(255, 255, 255, 0.85),
    0 8px 18px rgba(20, 30, 50, 0.12);
}
.vinyl-cover.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--fg-3);
  left: 16.666%;
  right: 16.666%;
  top: 16.666%;
  bottom: 16.666%;
  width: auto;
  height: auto;
}
.vinyl-hole {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 6.5%;
  height: 6.5%;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  background: radial-gradient(circle at 35% 35%, #3a3a3a, #0a0a0a 70%);
  box-shadow: 0 0 0 2px rgba(0, 0, 0, 0.5);
  z-index: 2;
}
.player-panel.light .vinyl-hole {
  background: radial-gradient(circle at 35% 35%, #cfd5df, #8b93a3 70%);
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.7);
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* ---------- blend stage ---------- */
.blend-stage {
  flex: 1;
  min-height: 0;
  position: relative;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.blend-bg {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  padding: clamp(4px, 2cqh, 16px) clamp(0px, 1.5cqw, 12px) 0 0;
  pointer-events: none;
  z-index: 0;
  box-sizing: border-box;
}
.blend-stage .vinyl-frame {
  filter: saturate(1.14) brightness(0.92);
  opacity: 0.88;
  transform: translateX(14%) scale(1.08);
}
.player-panel.light .blend-stage .vinyl-frame {
  filter: saturate(1.04) brightness(1.04);
  opacity: 0.58;
}
.blend-veil {
  position: absolute;
  inset: 0;
  background: var(--blend-veil);
}
.blend-lyrics {
  position: relative;
  z-index: 1;
  flex: 1;
  min-height: 0;
  width: min(68%, 520px);
  display: flex;
  flex-direction: column;
  padding: clamp(8px, 2.6cqh, 22px) 0 0 clamp(8px, 3.5cqw, 28px);
  box-sizing: border-box;
}
.blend-lyrics :deep(.lyrics) {
  flex: 1;
  min-height: 0;
  padding-left: 0;
  padding-right: clamp(10px, 2cqw, 22px);
  background: transparent;
  scrollbar-width: none;
  -ms-overflow-style: none;
}
.blend-lyrics :deep(.lyrics::-webkit-scrollbar) {
  display: none;
}
/* stronger text legibility over blurred vinyl */
.blend-lyrics :deep(.line) {
  text-shadow: 0 1px 10px rgba(0, 0, 0, 0.35);
}
.player-panel.light .blend-lyrics :deep(.line) {
  text-shadow: 0 1px 8px rgba(255, 255, 255, 0.65);
}
.blend-lyrics :deep(.line.active) {
  text-shadow: 0 0 18px rgba(255, 255, 255, 0.28), 0 2px 12px rgba(0, 0, 0, 0.35);
}
.player-panel.light .blend-lyrics :deep(.line.active) {
  text-shadow: 0 1px 10px rgba(255, 255, 255, 0.8);
}

.lyrics-stage {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 4px 0 0;
}
.lyrics-stage :deep(.lyrics) {
  flex: 1;
  min-height: 0;
}

.tap-hint {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 10px;
  text-align: center;
  font-size: 11px;
  color: var(--fg-4);
  letter-spacing: 0.02em;
  pointer-events: none;
}

@media (max-width: 1100px) {
  .cover-stage .vinyl-frame {
    width: min(92%, 320px);
  }
  .blend-lyrics {
    width: min(72%, 500px);
  }
}

/* 宽屏（>1100px）：叠层视图改为「黑胶左、歌词右」居中双栏。
   窄屏设计把黑胶当作右缘背景装饰（translateX 14% 切半 + 低透明度），
   宽屏下违和；双栏让黑胶成为正式布局元素。 */
@media (min-width: 1101px) {
  .blend-stage {
    flex-direction: row;
    align-items: center;
    justify-content: center;
    gap: clamp(36px, 5vw, 80px);
    padding: 0 24px 14px;
    box-sizing: border-box;
  }
  .blend-bg {
    position: relative;
    inset: auto;
    flex: 0 0 auto;
    padding: 0;
  }
  .blend-stage .vinyl-frame {
    transform: none;
    opacity: 1;
    filter: var(--vinyl-shadow);
    width: min(92%, 340px);
    width: min(340px, 64cqh);
  }
  .player-panel.light .blend-stage .vinyl-frame {
    opacity: 1;
    filter: var(--vinyl-shadow);
  }
  .blend-veil {
    display: none;
  }
  .blend-lyrics {
    flex: 0 1 auto;
    width: min(520px, 46%);
    height: 100%;
    padding: 0;
    justify-content: center;
  }
  .blend-lyrics :deep(.lyrics) {
    flex: 1;
    min-height: 0;
    padding-right: 8px;
  }
  /* 封面视图的黑胶在宽屏也放大一档 */
  .cover-stage .vinyl-frame {
    width: min(92%, 460px);
    width: min(94cqw, 82cqh, 480px);
  }
}

@media (max-width: 720px) {
  .blend-bg {
    justify-content: center;
    opacity: 0.72;
  }
  .blend-stage .vinyl-frame {
    transform: translateX(18%) scale(1.02);
  }
  .blend-lyrics {
    width: 82%;
  }
}

@media (max-width: 768px) {
  .tap-hint {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .vinyl.spinning {
    animation: none;
  }
}
</style>
