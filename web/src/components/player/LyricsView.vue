<template>
  <div
    class="lyrics"
    :class="{ immersive, light: !isDark, 'align-left': alignLeft }"
    :style="rootStyle"
    ref="box"
    @wheel="onUserScroll"
    @touchstart="onUserScroll"
  >
    <div v-if="!lines.length" class="empty">
      <div class="empty-title">{{ emptyTitle }}</div>
      <div class="empty-sub">{{ emptyDescription }}</div>
    </div>
    <template v-else>
      <div class="pad" aria-hidden="true"></div>
      <div
        v-for="(line, idx) in lines"
        :key="`${idx}-${line.time}`"
        class="line"
        :class="lineClass(idx)"
        :ref="(el) => setLineRef(el, idx)"
        @click="$emit('seek', line.time)"
      >
        {{ line.text || ' ' }}
      </div>
      <div class="pad" aria-hidden="true"></div>
    </template>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useThemeStore } from '@/stores/theme'

const props = defineProps({
  lines: { type: Array, default: () => [] },
  activeIndex: { type: Number, default: -1 },
  immersive: { type: Boolean, default: false },
  fontSize: { type: Number, default: 18 },
  emptyTitle: { type: String, default: '暂无歌词' },
  emptyDescription: { type: String, default: '播放带 LRC 的歌曲后会在这里滚动高亮' },
  // 左对齐（唱片皮肤用，歌词贴着左栏）；默认居中
  alignLeft: { type: Boolean, default: false },
})
defineEmits(['seek'])

// 焦点衰减：当前行提亮放大，邻行按距离变暗（替代原来"非当前行统一 0.42、相邻 0.58"的平铺）
function lineClass(idx) {
  if (idx === props.activeIndex) return 'active'
  if (props.activeIndex < 0) return ''
  const d = Math.abs(idx - props.activeIndex)
  if (d === 1) return 'd1'
  if (d === 2) return 'd2'
  if (d === 3) return 'd3'
  return 'd4'
}

const themeStore = useThemeStore()
const isDark = computed(() => themeStore.isDark)
const box = ref(null)
const lineRefs = ref([])
let userScrolling = false
let resumeTimer = 0

const rootStyle = computed(() => {
  const base = Math.max(14, Math.min(28, Number(props.fontSize) || 18))
  return {
    '--lyric-font-size': `${base}px`,
    '--lyric-active-size': `${base + 3}px`,
  }
})

function setLineRef(el, idx) {
  if (el) lineRefs.value[idx] = el
  else delete lineRefs.value[idx]
}

function onUserScroll() {
  userScrolling = true
  if (resumeTimer) window.clearTimeout(resumeTimer)
  resumeTimer = window.setTimeout(() => {
    userScrolling = false
    scrollToActive(props.activeIndex, true)
  }, 2500)
}

function scrollToActive(idx, force = false) {
  if (idx == null || idx < 0) return
  if (userScrolling && !force) return
  const el = lineRefs.value[idx]
  const root = box.value
  if (!el || !root) return

  try {
    el.scrollIntoView({ block: 'center', behavior: force ? 'auto' : 'smooth', inline: 'nearest' })
    return
  } catch (_) {
    // fallback below
  }
  const top = el.offsetTop - root.clientHeight / 2 + el.clientHeight / 2
  root.scrollTo({ top: Math.max(0, top), behavior: force ? 'auto' : 'smooth' })
}

watch(
  () => props.activeIndex,
  async (idx) => {
    await nextTick()
    scrollToActive(idx)
  },
)

watch(
  () => [props.lines, props.fontSize],
  async () => {
    lineRefs.value = []
    await nextTick()
    scrollToActive(props.activeIndex, true)
  },
)

onBeforeUnmount(() => {
  if (resumeTimer) window.clearTimeout(resumeTimer)
})
</script>

<style scoped>
.lyrics {
  height: 100%;
  min-height: 0;
  overflow: auto;
  padding: 0 14px;
  text-align: center;
  scroll-behavior: smooth;
  box-sizing: border-box;
  /* 沉浸式歌词自动滚动居中，不显示滚动条（滚轮仍可手动滚） */
  scrollbar-width: none;
  -ms-overflow-style: none;
  mask-image: linear-gradient(to bottom, transparent 0%, #000 12%, #000 88%, transparent 100%);
  -webkit-mask-image: linear-gradient(to bottom, transparent 0%, #000 12%, #000 88%, transparent 100%);
  --lyric-fg: rgba(255, 255, 255, 0.42);
  --lyric-near: rgba(255, 255, 255, 0.58);
  --lyric-hover: rgba(255, 255, 255, 0.72);
  --lyric-active: #fff;
  --lyric-empty: rgba(255, 255, 255, 0.55);
  --lyric-empty-title: rgba(255, 255, 255, 0.78);
  --lyric-empty-sub: rgba(255, 255, 255, 0.42);
  --lyric-shadow: 0 0 18px rgba(255, 255, 255, 0.28);
}
.lyrics.light {
  --lyric-fg: rgba(18, 22, 30, 0.42);
  --lyric-near: rgba(18, 22, 30, 0.62);
  --lyric-hover: rgba(18, 22, 30, 0.78);
  --lyric-active: rgba(18, 22, 30, 0.95);
  --lyric-empty: rgba(18, 22, 30, 0.48);
  --lyric-empty-title: rgba(18, 22, 30, 0.82);
  --lyric-empty-sub: rgba(18, 22, 30, 0.42);
  --lyric-shadow: 0 0 0 transparent;
}
.lyrics.immersive {
  padding: 0 18px;
}
.lyrics::-webkit-scrollbar {
  width: 0;
  height: 0;
  display: none;
}
.pad {
  height: 34%;
  min-height: 72px;
  pointer-events: none;
}
.empty {
  height: 100%;
  min-height: 160px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--lyric-empty);
}
.empty-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--lyric-empty-title);
}
.empty-sub {
  font-size: 12px;
  color: var(--lyric-empty-sub);
}
.line {
  padding: 10px 8px;
  font-size: var(--lyric-font-size, 18px);
  line-height: 1.55;
  color: var(--lyric-fg);
  transition: color 0.22s ease, transform 0.22s ease, opacity 0.22s ease, text-shadow 0.22s ease, font-size 0.18s ease;
  cursor: pointer;
  user-select: none;
  border-radius: 10px;
}
.line:hover {
  color: var(--lyric-hover);
}
/* 焦点衰减：按与当前行的距离分层变暗 */
.line.d1 { opacity: 0.62; }
.line.d2 { opacity: 0.42; }
.line.d3 { opacity: 0.26; }
.line.d4 { opacity: 0.16; }
.line.active {
  color: var(--lyric-active);
  font-weight: 700;
  font-size: var(--lyric-active-size, 21px);
  transform: scale(1.03);
  text-shadow: var(--lyric-shadow), 0 0 26px var(--accent, rgba(255, 255, 255, 0.28));
}
.lyrics.align-left {
  text-align: left;
}
.lyrics.align-left .line {
  text-align: left;
}
</style>
