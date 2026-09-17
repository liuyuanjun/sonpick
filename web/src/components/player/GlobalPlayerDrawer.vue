<template>
  <transition name="gp-drawer">
    <div
      v-if="player.fullPlayerOpen"
      ref="rootRef"
      class="gp-drawer"
      :class="{ 'is-dark': themeStore.isDark }"
      :style="accentStyle"
      role="dialog"
      aria-modal="true"
      aria-label="正在播放"
      tabindex="-1"
      @keydown="onTabKeydown"
    >
      <div class="gp-drawer-stage">
        <div class="gp-stage-main">
          <player-panel />
        </div>

        <transition name="gp-queue">
          <aside v-if="player.showQueue" class="gp-queue">
            <player-queue />
          </aside>
        </transition>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import PlayerPanel from '@/components/player/PlayerPanel.vue'
import PlayerQueue from '@/components/player/PlayerQueue.vue'
import { usePlayerStore } from '@/stores/player'
import { useThemeStore } from '@/stores/theme'
import { extractAccentFromImage } from '@/utils/color'

// 全局大播放器抽屉：桌面与移动端均为视口全覆盖浮层（沉浸式接管，不再保留侧边栏）。
// 它是 PlayerPanel / PlayerQueue 的唯一宿主——历史上这两个组件在 PlayerView 与 LayoutView
// 各挂了一份，导致移动端同时渲染两份面板、两份队列，这里收敛为单一实例。
const player = usePlayerStore()
const themeStore = useThemeStore()

const rootRef = ref(null)
const accent = ref(null)
let lastActiveElement = null

const accentStyle = computed(() => {
  // 无封面时的强调色：暗色用品牌 400，亮色用品牌 700（与 tokens 主色一致）
  const fallback = themeStore.isDark ? { r: 52, g: 211, b: 153 } : { r: 4, g: 120, b: 87 }
  const { r, g, b } = accent.value || fallback
  const dark = themeStore.isDark
  return {
    '--cover-accent': `rgb(${r}, ${g}, ${b})`,
    '--cover-accent-glow': `rgba(${r}, ${g}, ${b}, ${dark ? 0.18 : 0.13})`,
    '--cover-accent-wash': `rgba(${r}, ${g}, ${b}, ${dark ? 0.18 : 0.12})`,
    '--cover-accent-wash-soft': `rgba(${r}, ${g}, ${b}, ${dark ? 0.10 : 0.08})`,
  }
})

watch(
  () => player.cover,
  async (url) => {
    accent.value = null
    if (!url) return
    accent.value = await extractAccentFromImage(url)
  },
  { immediate: true },
)

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

function focusableNodes() {
  if (!rootRef.value) return []
  return Array.from(rootRef.value.querySelectorAll(FOCUSABLE)).filter(
    (el) => el.offsetParent !== null || el === document.activeElement,
  )
}

// 焦点闭环：抽屉内 Tab 不逃逸到底层页面
function onTabKeydown(e) {
  if (e.key !== 'Tab') return
  const nodes = focusableNodes()
  if (!nodes.length) return
  const first = nodes[0]
  const last = nodes[nodes.length - 1]
  const active = document.activeElement
  if (!rootRef.value?.contains(active)) {
    e.preventDefault()
    first.focus()
    return
  }
  if (e.shiftKey && active === first) {
    e.preventDefault()
    last.focus()
  } else if (!e.shiftKey && active === last) {
    e.preventDefault()
    first.focus()
  }
}

// 最上层弹窗（刮削信息 / 获取歌词 / 整理路径）打开时，Esc 应由它先处理
function hasNestedOverlay() {
  return !!document.querySelector('.n-modal, .n-dialog, .n-drawer')
}

function onEscKeydown(e) {
  if (e.key !== 'Escape') return
  if (!player.fullPlayerOpen) return
  if (hasNestedOverlay()) return
  player.fullPlayerOpen = false
}

function syncOverlayState(open) {
  const html = document.documentElement
  if (open) {
    lastActiveElement = document.activeElement
    html.classList.add('sp-overlay-open')
    nextTick(() => rootRef.value?.focus())
  } else {
    html.classList.remove('sp-overlay-open')
    if (lastActiveElement && typeof lastActiveElement.focus === 'function') {
      lastActiveElement.focus()
    }
    lastActiveElement = null
  }
}

watch(() => player.fullPlayerOpen, syncOverlayState)

onMounted(() => {
  document.addEventListener('keydown', onEscKeydown)
  if (player.fullPlayerOpen) syncOverlayState(true)
})

onUnmounted(() => {
  document.removeEventListener('keydown', onEscKeydown)
  document.documentElement.classList.remove('sp-overlay-open')
})
</script>

<style scoped>
.gp-drawer {
  position: fixed;
  inset: 0;
  /* AGENTS.md §5.5：全屏播放器覆盖层用 1400 带（低于 Naive 弹层 2000，弹层须能盖在其上） */
  z-index: 1400;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--sp-ui-body);
  color: var(--sp-ui-text-1);
  outline: none;
}
.gp-drawer-stage {
  position: relative;
  flex: 1 1 auto;
  display: flex;
  flex-direction: row;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  background:
    radial-gradient(52% 78% at 12% 50%, var(--cover-accent-wash), rgba(0, 0, 0, 0) 72%),
    radial-gradient(46% 70% at 88% 42%, var(--cover-accent-wash-soft), rgba(0, 0, 0, 0) 70%),
    var(--sp-ui-body);
}
.gp-stage-main {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.gp-queue {
  width: 280px;
  flex: 0 0 280px;
  border-left: 1px solid var(--sp-ui-border);
  min-height: 0;
  overflow: hidden;
  background: var(--sp-ui-card);
  color: var(--sp-ui-text-1);
}

.gp-drawer-enter-active,
.gp-drawer-leave-active {
  transition: transform 0.3s cubic-bezier(0.25, 1, 0.5, 1), opacity 0.3s ease;
}
.gp-drawer-enter-from,
.gp-drawer-leave-to {
  transform: translateY(100%);
  opacity: 0;
}
.gp-queue-enter-active,
.gp-queue-leave-active {
  transition: width 0.18s ease, opacity 0.18s ease, flex-basis 0.18s ease;
}
.gp-queue-enter-from,
.gp-queue-leave-to {
  width: 0 !important;
  flex-basis: 0 !important;
  opacity: 0;
  border-left-width: 0;
}

/* 移动端：队列改为抽屉内覆盖层 */
@media (max-width: 768px) {
  .gp-queue {
    position: absolute;
    inset: 0;
    width: auto;
    flex: none;
    z-index: 3;
    border-left: none;
  }
  .gp-queue-enter-active,
  .gp-queue-leave-active {
    transition: transform 0.18s ease, opacity 0.18s ease;
  }
  .gp-queue-enter-from,
  .gp-queue-leave-to {
    width: auto !important;
    flex-basis: auto !important;
    transform: translateY(14px);
    border-left-width: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .gp-drawer-enter-active,
  .gp-drawer-leave-active,
  .gp-queue-enter-active,
  .gp-queue-leave-active {
    transition: none;
  }
}
</style>
