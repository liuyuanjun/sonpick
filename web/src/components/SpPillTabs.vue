<template>
  <div class="sp-pill-tabs">
    <div ref="trackEl" class="sp-pill-tabs-track" role="tablist" :aria-label="ariaLabel">
      <div ref="thumbEl" class="sp-pill-tabs-thumb" aria-hidden="true" />

      <button
        v-for="item in items"
        :key="item.key"
        :ref="(el) => setTabEl(item.key, el)"
        :id="tabDomId(item.key)"
        class="sp-pill-tab"
        type="button"
        role="tab"
        :aria-selected="item.key === value"
        :aria-controls="panelId || undefined"
        :tabindex="item.key === value ? undefined : -1"
        @click="select(item.key)"
        @keydown="onKeydown"
      >
        <span class="sp-pill-tab-label">
          <span v-if="item.icon" class="sp-pill-tab-ico" aria-hidden="true"><component :is="item.icon" /></span>
          {{ item.label }}
        </span>
        <!--
          反色副本：胶囊滑到哪，这层「on-primary 色」的文字就从哪被擦出来。
          没有它的话，胶囊还在路上时新标签已经是主色文字、而底色也还是主色 —— 白底白字，看不见。
          副本同样参与居中，所以必须 padding/gap 继承，否则会和正本差一个内边距。
        -->
        <span class="sp-pill-tab-label sp-pill-tab-label-inverse" aria-hidden="true">
          <span v-if="item.icon" class="sp-pill-tab-ico" aria-hidden="true"><component :is="item.icon" /></span>
          {{ item.label }}
        </span>
      </button>
    </div>
  </div>
</template>

<script>
// 模块作用域：序号必须在实例之间共享，否则每个实例都拿到同一个 id 前缀
let uidSeq = 0
</script>

<script setup>
/**
 * 页内胶囊 tab（beUI `motion/tabs` 的 Vue 落地，只做 pill 变体）。
 *
 * ══ 两个动效层，缺一不可 ══
 * 1. **胶囊位移**：单个绝对定位元素，用 utils/flowingPill.js 从目标 tab 的矩形投影过去
 *    （x 与 width 一起变，因为每个 tab 宽度不同）。`prefers-reduced-motion` 降级为瞬置。
 * 2. **标签文字反色擦除**：每个 tab 里放一份 on-primary 色的文字副本，用 `clip-path: inset()`
 *    裁到胶囊当前的矩形上。胶囊在动，所以这份裁切必须**逐帧同步** ——
 *    也就是下面 `runClipSync()` 那段 rAF；只在点击那一帧算一次的话，会看到
 *    「药丸滑过去了、字还是暗的」。
 *
 * ══ 两个刻意的取舍 ══
 * - **选中态不加粗**：加粗会改变该 tab 的宽度 → 每切一次 tab 整条都重排、胶囊目标也漂移。
 *   所以新旧标签的字重保持一致，靠反色副本负责「选中感」。
 * - **不用 ARIA menu 模式**（那是侧边栏的做法）；tab 就该用 tablist/tab/tabpanel，
 *   方向键在 tablist 内切换是这套模式的标配。
 *
 * 受控组件：必须用 `v-model:value` 绑定（全站约定 Naive 风格的 `value` / `update:value`，不用 `modelValue`），
 * 位移由 `value` 的变化驱动（不自行维护选中态）。
 */
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { createFlowingPill } from '@/utils/flowingPill'

const props = defineProps({
  /** 当前选中的 tab key */
  value: { type: String, required: true },
  /** [{ key, label, icon? }]，icon 传组件本身，尺寸由本组件按 token 控制 */
  items: { type: Array, required: true },
  /** tablist 的无障碍名称 */
  ariaLabel: { type: String, default: '页内导航' },
  /** 给了就用它拼 tab 的 id：`${idPrefix}-tab-${key}`，供外部 panel 的 aria-labelledby 引用 */
  idPrefix: { type: String, default: '' },
  /** 面板 id，会写到每个 tab 的 aria-controls（本组件不渲染面板） */
  panelId: { type: String, default: '' },
})

const emit = defineEmits(['update:value'])

// 实例级唯一前缀。不用 useId()：它要 Vue 3.5+，本项目锁定在 3.4；序号在模块作用域（见上方 <script>）
const uid = `sp-tabs-${(uidSeq += 1)}`

const trackEl = ref(null)
const thumbEl = ref(null)
const tabEls = new Map()

/** 反色副本的静态几何：只随尺寸/字体变化，不随胶囊动画变化，因此量一次缓存 */
let labelBoxes = []
let mover = null
let resizeObserver = null
let clipRaf = 0

function tabDomId(key) {
  return props.idPrefix ? `${props.idPrefix}-tab-${key}` : `${uid}-tab-${key}`
}

function setTabEl(key, el) {
  if (el) tabEls.set(key, el)
  else tabEls.delete(key)
}

/* ── 选择 ─────────────────────────────────────────────────── */

function select(key, focus = false) {
  if (key !== props.value) emit('update:value', key)
  if (focus) nextTick(() => tabEls.get(key)?.focus())
}

function onKeydown(event) {
  const keys = props.items.map((item) => item.key)
  const index = keys.indexOf(props.value)
  let next = null
  if (event.key === 'ArrowRight') next = keys[(index + 1) % keys.length]
  else if (event.key === 'ArrowLeft') next = keys[(index - 1 + keys.length) % keys.length]
  else if (event.key === 'Home') next = keys[0]
  else if (event.key === 'End') next = keys[keys.length - 1]
  if (!next) return
  event.preventDefault()
  select(next, true)
}

/* ── 胶囊 + 反色擦除 ──────────────────────────────────────── */

function measureLabels() {
  if (!trackEl.value) return
  labelBoxes = Array.from(trackEl.value.querySelectorAll('.sp-pill-tab-label-inverse')).map((el) => {
    // clip-path 只影响绘制与命中，不影响布局盒，所以这里量到的是**未被裁切**的完整矩形
    const rect = el.getBoundingClientRect()
    return { el, left: rect.left, width: rect.width }
  })
}

function syncClips() {
  if (!labelBoxes.length || !thumbEl.value) return
  const thumb = thumbEl.value.getBoundingClientRect()
  // 先把所有几何读完再统一写样式：读写交错会逼浏览器反复 flush 布局
  const clips = labelBoxes.map(({ left, width }) => {
    const insetLeft = Math.max(0, Math.min(width, thumb.left - left))
    const insetRight = Math.max(0, Math.min(width, left + width - thumb.right))
    return insetLeft + insetRight >= width ? 'inset(0 100% 0 0)' : `inset(0 ${insetRight}px 0 ${insetLeft}px)`
  })
  clips.forEach((clip, index) => {
    const el = labelBoxes[index].el
    if (el.style.clipPath !== clip) el.style.clipPath = clip
  })
}

/** 跟胶囊动画同生命周期地同步裁切；动画一停就自己退出，不做常驻 rAF */
function runClipSync() {
  if (clipRaf) return
  syncClips()                                  // 瞬置 / 降级时，这一下就是终态
  const tick = () => {
    syncClips()
    clipRaf = mover?.busy() ? requestAnimationFrame(tick) : 0
  }
  clipRaf = requestAnimationFrame(tick)
}

function moveTo(key, animate) {
  const target = tabEls.get(key)
  if (!target || !mover) return
  mover.place(target, animate)
  runClipSync()
}

/** 尺寸变了（窗口缩放、断点切换、字体加载）：重新量静态几何，再瞬时对位 */
function onGeometryChange() {
  measureLabels()
  const target = tabEls.get(props.value)
  if (target && mover) mover.place(target, false)
  syncClips()
}

watch(() => props.value, (key) => moveTo(key, true))

watch(() => props.items, () => {
  nextTick(onGeometryChange)
})

onMounted(async () => {
  await nextTick()
  if (!thumbEl.value || !trackEl.value) return
  mover = createFlowingPill(thumbEl.value, trackEl.value, { axis: 'x' })
  onGeometryChange()
  resizeObserver = new ResizeObserver(onGeometryChange)
  resizeObserver.observe(trackEl.value)
  document.fonts?.ready?.then(onGeometryChange)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  if (clipRaf) cancelAnimationFrame(clipRaf)
  clipRaf = 0
})
</script>

<style scoped>
.sp-pill-tabs {
  display: inline-flex;
  max-width: 100%;
}

.sp-pill-tabs-track {
  position: relative;   /* 胶囊与反色副本的包含块 */
  display: inline-flex;
  align-items: center;
  gap: var(--sp-space-1);
  padding: var(--sp-space-1);
  border: 1px solid var(--sp-ui-border);
  border-radius: var(--sp-radius-pill);
  background: var(--sp-ui-card);
}

/* 胶囊：位置与尺寸全部由 JS 写，横向不再交给 CSS（每个 tab 宽度不同） */
.sp-pill-tabs-thumb {
  position: absolute;
  top: 0;
  left: 0;
  z-index: 0;
  width: 0;
  height: 0;
  border-radius: var(--sp-radius-pill);
  background: var(--sp-ui-primary);
  will-change: transform;
}

.sp-pill-tab {
  position: relative;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--sp-space-2);
  height: var(--sp-pill-tab-h);
  padding: 0 14px;
  border: 0;
  border-radius: var(--sp-radius-pill);
  background: none;
  color: var(--sp-ui-text-2);
  font-size: var(--sp-fs-body);
  font-weight: var(--sp-fw-medium);
  white-space: nowrap;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transition: color var(--sp-dur-fast) var(--sp-ease-enter);
}
.sp-pill-tab:hover { color: var(--sp-ui-text-1) }
.sp-pill-tab:active { transform: scale(0.98) }

.sp-pill-tab-label {
  display: inline-flex;
  align-items: center;
  gap: inherit;
}

.sp-pill-tab-label-inverse {
  position: absolute;
  inset: 0;
  justify-content: center;
  /* 与正本同框居中：副本铺满 padding box，所以要把内边距与间距一起继承回来 */
  padding: inherit;
  color: var(--sp-ui-on-primary);
  /* 初始全裁掉；由 syncClips() 按胶囊位置放开 */
  clip-path: inset(0 100% 0 0);
  pointer-events: none;
}

.sp-pill-tab-ico {
  display: grid;
  place-items: center;
  font-size: var(--sp-icon-sm);
}

@media (max-width: 768px) {
  .sp-pill-tabs,
  .sp-pill-tabs-track { display: flex; width: 100% }
  .sp-pill-tab {
    flex: 1 1 0;
    min-width: 0;
    padding: 0 var(--sp-space-2);
    font-size: var(--sp-fs-small);
  }
  /* 窄屏塞不下「图标 + 文字」，图标让位给文字 */
  .sp-pill-tab-ico { display: none }
}
</style>
