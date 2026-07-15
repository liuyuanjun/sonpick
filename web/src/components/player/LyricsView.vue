<template>
  <div
    class="lyrics"
    :class="{ immersive, light: !isDark }"
    :style="rootStyle"
    ref="box"
    @wheel="onUserScroll"
    @touchstart="onUserScroll"
  >
    <div v-if="!lines.length" class="empty">
      <div class="empty-title">暂无歌词</div>
      <div class="empty-sub">播放带 LRC 的歌曲后会在这里滚动高亮</div>
    </div>
    <template v-else>
      <div class="pad" aria-hidden="true"></div>
      <div
        v-for="(line, idx) in lines"
        :key="`${idx}-${line.time}`"
        class="line"
        :class="{ active: idx === activeIndex, near: Math.abs(idx - activeIndex) === 1 }"
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
})
defineEmits(['seek'])

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
.line.near {
  color: var(--lyric-near);
}
.line.active {
  color: var(--lyric-active);
  font-weight: 700;
  font-size: var(--lyric-active-size, 21px);
  transform: scale(1.03);
  text-shadow: var(--lyric-shadow);
}
</style>
