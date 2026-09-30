<template>
  <aside
    class="sp-sider"
    :data-collapsed="collapsed"
    aria-label="主导航栏"
  >
    <div class="sp-sider-clip">
      <div v-if="$slots.header" class="sp-sider-head">
        <slot name="header" :collapsed="collapsed" />
      </div>

      <nav
        ref="navEl"
        class="sp-nav"
        aria-label="主导航"
        @mouseover="onPointerOver"
        @mouseleave="onPointerLeave"
        @focusin="onFocusIn"
        @focusout="onFocusOut"
        @keydown="onKeydown"
      >
        <!-- 胶囊层：两个独立胶囊。激活胶囊常驻当前项，悬停胶囊只在指针/焦点进入菜单后出现 -->
        <div class="sp-pill-layer" aria-hidden="true">
          <div ref="pillActiveEl" class="sp-pill sp-pill-active" />
          <div ref="pillHoverEl" class="sp-pill sp-pill-hover" :data-on="hoverOn" />
        </div>

        <div v-for="(group, gi) in groups" :key="group.key || gi" class="sp-group">
          <div
            v-if="group.label"
            class="sp-group-label sp-collapse-fade"
            :aria-hidden="collapsed || undefined"
          >
            {{ group.label }}
          </div>

          <ul class="sp-menu">
            <li
              v-for="item in group.items"
              :key="item.key"
              class="sp-item"
              :data-open="isOpen(item) ? 'true' : 'false'"
            >
              <n-tooltip :disabled="!collapsed" placement="right" :delay="180">
                <template #trigger>
                  <!-- 父项用 <button>（点它只展开，不导航），叶子用 <a>（可右键新标签打开） -->
                  <component
                    :is="item.children ? 'button' : 'a'"
                    class="sp-item-btn"
                    :type="item.children ? 'button' : undefined"
                    :href="item.children ? undefined : item.key"
                    :data-key="item.children ? undefined : item.key"
                    :data-parent="item.children ? item.key : undefined"
                    :aria-label="item.label"
                    :aria-current="!item.children && item.key === activeKey ? 'page' : undefined"
                    :aria-expanded="item.children ? isOpen(item) : undefined"
                    @click="onItemClick($event, item)"
                  >
                    <span class="sp-ico" aria-hidden="true">
                      <component :is="item.icon" />
                    </span>
                    <span class="sp-item-label sp-collapse-fade">{{ item.label }}</span>
                    <span v-if="item.children" class="sp-item-chev sp-collapse-fade" aria-hidden="true">
                      <chevron-forward />
                    </span>
                  </component>
                </template>
                {{ item.label }}
              </n-tooltip>

              <!--
                子菜单：高度 0 ↔ 自然高 + overflow:hidden，本身就是「自上而下的擦除」。
                收起时必须 inert：否则视觉上没了，Tab 仍能走进去（clip 不影响焦点顺序）。
                注意 inert 是「存在即生效」的布尔属性，:inert="false" 会渲染成 inert="false"
                反而打开它 —— 所以关闭态传 true、展开态传 undefined 让它被移除。
              -->
              <ul
                v-if="item.children"
                class="sp-sub"
                :data-key="item.key"
                :data-open="isOpen(item) ? 'true' : 'false'"
                :inert="isOpen(item) ? undefined : true"
              >
                <li v-for="(child, ci) in item.children" :key="child.key">
                  <a
                    class="sp-sub-btn"
                    :href="child.key"
                    :data-key="child.key"
                    :aria-label="child.label"
                    :aria-current="child.key === activeKey ? 'page' : undefined"
                    :style="{ '--i': ci, '--rev': item.children.length - 1 - ci }"
                    @click="onItemClick($event, child)"
                  >
                    <span class="sp-item-label">{{ child.label }}</span>
                  </a>
                </li>
              </ul>
            </li>
          </ul>
        </div>
      </nav>

      <div v-if="$slots.footer" class="sp-sider-foot">
        <slot name="footer" :collapsed="collapsed" />
      </div>
    </div>

    <!-- 接缝热区：点侧边栏外缘即可收起/展开 -->
    <button
      class="sp-rail"
      type="button"
      :aria-label="collapsed ? '展开侧边栏' : '收起侧边栏'"
      title="收起 / 展开侧边栏"
      @click="toggle"
    />
  </aside>
</template>

<script setup>
/**
 * 侧边栏导航（分组 + 二级菜单 + 跟随胶囊 + 图标轨折叠）。
 *
 * ══ 为什么不是 n-menu ══
 * Naive 的菜单高亮是「逐项开关」：hover 到哪一项，只有那一项变色，跨项移动没有任何位移信息。
 * 本项目要的是「高亮块在项与项之间游过去」，这需要共享布局投影 —— 见 components/nav/flowingPill.js。
 * Naive 菜单内部结构也不给插槽去承载一个跨项的浮动层，硬做只能靠覆盖 .n-menu-item 的私有类，
 * 比自研更脆。
 *
 * ══ 无障碍口径（刻意不用 ARIA menu 模式）══
 * 侧边栏导航的正确语义是「链接列表」（nav > ul > li > a），主路径是 Tab。
 * WAI-ARIA 的 menu/menuitem 模式要求方向键成为唯一导航手段、Tab 只进出整个菜单一次，
 * 那会让「想直接从侧边栏 Tab 到内容区」变得别扭。因此这里保留链接语义 + Tab，
 * 方向键只作为**增强**（↓↑ 相邻项、→ 展开/进子项、← 收起/回父项、Esc 收起本组）。
 *
 * props/emits 完全无 store 依赖，便于单独挂到原型页或测试台下实测。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ChevronForward } from '@vicons/ionicons5'
import { createFlowingPill } from '@/utils/flowingPill'

const props = defineProps({
  /** [{ key?, label, items: [{ key, label, icon, children? }] }] */
  groups: { type: Array, required: true },
  /** 当前激活项的路由 key（与 item.key 比对） */
  activeKey: { type: String, default: '' },
  /** 桌面端折叠成图标轨 */
  collapsed: { type: Boolean, default: false },
  /** 是否启用 ⌘B / Ctrl+B 快捷键 */
  hotkey: { type: Boolean, default: false },
})

const emit = defineEmits(['navigate', 'update:collapsed'])

const navEl = ref(null)
const pillActiveEl = ref(null)
const pillHoverEl = ref(null)
const hoverOn = ref(false)
/** 全部父项 key（有 children 的项） */
function parentKeys() {
  return props.groups.flatMap((group) => group.items).filter((item) => item.children).map((item) => item.key)
}

/** 展开的父项 key。默认全部展开（v0.15.2-rc11 起）；各组独立开合，
    不做手风琴 —— 默认全开的场景下「开一组就关掉另一组」是不可预期的 */
const openKeys = ref(parentKeys())

let activePill = null
let hoverPill = null

/* ── 查询与状态 ───────────────────────────────────────────── */

const allItems = computed(() => props.groups.flatMap((group) => group.items))

function parentOf(key) {
  return allItems.value.find((item) => item.children?.some((child) => child.key === key))
}

function isOpen(item) {
  return !!item.children && openKeys.value.includes(item.key)
}

function findLeafEl(key) {
  return navEl.value?.querySelector(`.sp-item-btn[data-key="${key}"], .sp-sub-btn[data-key="${key}"]`) || null
}

function findTargetEl(key) {
  // 1) 叶子项：精确命中
  const leaf = findLeafEl(key)
  if (leaf) return leaf
  // 2) 父项自己的 key（如「歌单」组的分组 key）：父项没有 data-key，
  //    但它的 key 就在 data-parent 上。用于「落到分组首页、没选中任何子项」的场景
  //    （例：/player/playlists 没带 ?pl=，子项都对不上，高亮该落在父项上）
  const own = navEl.value?.querySelector(`.sp-item-btn[data-parent="${key}"]`)
  if (own) return own
  // 3) 二级项在父项未展开时不可见，胶囊退回到父项上，避免高亮块落在折叠区里
  const parent = parentOf(key)
  return parent ? navEl.value?.querySelector(`.sp-item-btn[data-parent="${parent.key}"]`) || null : null
}

/* ── 胶囊 ─────────────────────────────────────────────────── */

function syncActive(animate) {
  const el = findTargetEl(props.activeKey)
  if (el) activePill?.place(el, animate)
}

function showHover(el, animate) {
  // 悬停/聚焦的正是当前项时不再叠第二层底：两层叠一起只会显得脏
  if (el.dataset.key && el.dataset.key === props.activeKey) return hideHover()
  if (!hoverOn.value) {
    hoverOn.value = true
    hoverPill?.place(el, false)   // 现身那一帧不滑，避免从上一个位置「飞」过来
    return
  }
  hoverPill?.place(el, animate)
}

function hideHover() {
  hoverOn.value = false
}

function onPointerOver(event) {
  const el = event.target.closest?.('.sp-item-btn, .sp-sub-btn')
  if (el) showHover(el, true)
}

function onPointerLeave() {
  hideHover()
}

function onFocusIn(event) {
  const el = event.target.closest?.('.sp-item-btn, .sp-sub-btn')
  if (el) showHover(el, true)
}

function onFocusOut(event) {
  if (!navEl.value?.contains(event.relatedTarget)) hideHover()
}

/* ── 位置追踪 ─────────────────────────────────────────────────
   胶囊的 y 依赖「目标项此刻在哪」，以下情况必须重新对位：
     1) 侧边栏宽度形变 → 容器尺寸在变，ResizeObserver 会逐帧触发
     2) 子菜单开合 → 容器尺寸没变，但下方的项在整体位移，RO 不触发，只能盯一段 rAF
     3) 窗口缩放 / 字体加载完成（行高微调）
   正在滑移的胶囊要跳过，否则追踪会把滑移动画钉在中途。 */
let trackUntil = 0
let trackRaf = 0

function refresh() {
  if (!activePill?.busy()) syncActive(false)
  if (!hoverOn.value || hoverPill?.busy()) return
  const hovered = navEl.value?.querySelector('.sp-item-btn:hover, .sp-sub-btn:hover')
  if (hovered) hoverPill.place(hovered, false)
}

function trackFor(ms) {
  trackUntil = Math.max(trackUntil, performance.now() + ms)
  if (trackRaf) return
  const tick = () => {
    refresh()
    trackRaf = performance.now() < trackUntil ? requestAnimationFrame(tick) : 0
  }
  trackRaf = requestAnimationFrame(tick)
}

/* ── 子菜单 ───────────────────────────────────────────────── */

async function setOpen(item, open) {
  // 各组独立开合：只在数组里增删自己的 key，不动别的组
  if (open) {
    if (!openKeys.value.includes(item.key)) openKeys.value = [...openKeys.value, item.key]
  } else {
    openKeys.value = openKeys.value.filter((key) => key !== item.key)
  }
  await nextTick()
  trackFor(280)
}

function syncSubHeights() {
  if (!navEl.value) return
  navEl.value.querySelectorAll('.sp-sub').forEach((ul) => {
    const open = ul.dataset.open === 'true'
    // 挂载初始化用：展开的钉到内容自然高（动画结束由 transitionend 换成 auto），
    // 收起的一开始就是 CSS 的 height:0，不用碰
    if (open) ul.style.height = `${ul.scrollHeight}px`
  })
}

/* 展开动画一结束就把高度换成 auto：歌单子菜单是动态数据（异步加载/增删），
   钉死像素高会把后到的子项裁掉（rc11 回归：默认展开后「管理歌单」被裁没）。
   收起时 openKeys watcher 会重新钉回像素值做过渡，不需要在这里管。 */
function onSubTransitionEnd(event) {
  const ul = event.target
  if (event.propertyName !== 'height' || !ul.classList?.contains('sp-sub')) return
  if (ul.dataset.open === 'true') ul.style.height = 'auto'
}

function onItemClick(event, item) {
  if (item.children) {
    event.preventDefault()
    const willOpen = !isOpen(item)
    // 图标轨里放不下子菜单：点父项 = 顺手把侧边栏展开
    if (willOpen && props.collapsed) emit('update:collapsed', false)
    setOpen(item, willOpen)
    return
  }
  // href 只作语义兜底（右键新标签可开），跳转交给父级 router
  event.preventDefault()
  emit('navigate', item.key)
}

/* ── 折叠 ─────────────────────────────────────────────────── */

function toggle() {
  emit('update:collapsed', !props.collapsed)
}

function onHotkey(event) {
  if (event.key?.toLowerCase() !== 'b' || !(event.metaKey || event.ctrlKey)) return
  // 输入框/可编辑区里的 ⌘B 是「加粗」，不能被侧边栏抢走
  const target = event.target
  if (target instanceof HTMLElement
    && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))) return
  event.preventDefault()
  toggle()
}

/* ── 键盘增强 ─────────────────────────────────────────────── */

function visibleButtons() {
  if (!navEl.value) return []
  // 只收展开子菜单里的项：关闭的 sub 在 DOM 里但 inert，不该进 Tab/方向键序列
  return Array.from(
    navEl.value.querySelectorAll('.sp-item-btn, .sp-sub[data-open="true"] .sp-sub-btn'),
  )
}

function onKeydown(event) {
  const current = event.target.closest?.('.sp-item-btn, .sp-sub-btn')
  if (!current) return
  const list = visibleButtons()
  const index = list.indexOf(current)
  const isSub = current.classList.contains('sp-sub-btn')
  const itemEl = current.closest('.sp-item')
  const item = isSub
    ? parentOf(current.dataset.key)
    : allItems.value.find((it) => it.key === current.dataset.parent || it.key === current.dataset.key)

  switch (event.key) {
    case 'ArrowDown':
    case 'ArrowUp': {
      event.preventDefault()
      const step = event.key === 'ArrowDown' ? 1 : -1
      list[(index + step + list.length) % list.length]?.focus()
      break
    }
    case 'Home':
    case 'End': {
      event.preventDefault()
      list[event.key === 'Home' ? 0 : list.length - 1]?.focus()
      break
    }
    case 'ArrowRight': {
      if (isSub) return
      event.preventDefault()
      if (!item?.children) return
      if (isOpen(item)) {
        navEl.value.querySelector('.sp-sub[data-open="true"] .sp-sub-btn')?.focus()
      } else {
        setOpen(item, true).then(() => trackFor(0))
      }
      break
    }
    case 'ArrowLeft': {
      event.preventDefault()
      if (isSub) {
        itemEl?.querySelector('.sp-item-btn')?.focus()
      } else if (item?.children && isOpen(item)) {
        setOpen(item, false)
      }
      break
    }
    case 'Escape': {
      if (!item?.children || !isOpen(item)) return
      event.preventDefault()
      setOpen(item, false)
      current.focus()
      break
    }
    default:
  }
}

/* ── 生命周期 ─────────────────────────────────────────────── */

let resizeObserver = null

onMounted(() => {
  if (!navEl.value || !pillActiveEl.value || !pillHoverEl.value) return
  // 坐标基准必须是 .sp-nav：它才是胶囊的包含块（position:relative 的 padding box）。
  // 传外层 .sp-sider 会把头部高度算进 y，整块高亮下移一个头部的距离。
  // 顺带 token 也从同一个元素读 —— 自定义属性从 :root 继承，取得到。
  activePill = createFlowingPill(pillActiveEl.value, navEl.value)
  hoverPill = createFlowingPill(pillHoverEl.value, navEl.value)

  syncActive(false)
  syncSubHeights()

  resizeObserver = new ResizeObserver(() => { if (!trackRaf) refresh() })
  resizeObserver.observe(navEl.value)
  navEl.value.addEventListener('transitionend', onSubTransitionEnd)
  window.addEventListener('resize', onWindowResize)
  if (props.hotkey) window.addEventListener('keydown', onHotkey)
  // 字体加载完再对一次位：字重变化会让行高微调，胶囊会错半像素
  document.fonts?.ready?.then(() => { if (activePill) syncActive(false) })
})

function onWindowResize() {
  trackFor(320)
}

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  navEl.value?.removeEventListener('transitionend', onSubTransitionEnd)
  window.removeEventListener('resize', onWindowResize)
  window.removeEventListener('keydown', onHotkey)
  if (trackRaf) cancelAnimationFrame(trackRaf)
  trackRaf = 0
})

/* 路由变化：激活胶囊滑到新项；顺便把激活项所在的父组展开 */
watch(() => props.activeKey, (key) => {
  const parent = parentOf(key)
  let opened = false
  if (parent && !props.collapsed && !isOpen(parent)) {
    // 只补开「激活项所在的父组」，不动其他组的当前开合状态
    openKeys.value = [...openKeys.value, parent.key]
    opened = true
  }
  nextTick(() => {
    syncActive(true)
    // 刚展开的父组会把下方整体推移，胶囊得跟着走完这段位移
    if (opened) trackFor(560)
  })
}, { immediate: true })

watch(() => props.collapsed, (value) => {
  // 图标轨里放不下子菜单，折叠时一律收起
  if (value) openKeys.value = []
  // 从图标轨展开回来：恢复「默认全开」，与初始挂载口径一致
  else openKeys.value = parentKeys()
  nextTick(() => trackFor(readMorphMs() + 60))
})

/* flush:'post' —— 等 DOM 反映新的 data-open 之后再量高度，否则量到的是上一态。
   只动「开合状态发生变化」的组：展开稳态是 height:auto（见 onSubTransitionEnd），
   没变的组若被钉回像素值，之后内容增长又会被裁。 */
watch(openKeys, (now, prev) => {
  if (!navEl.value) return
  const opened = new Set(now)
  const before = new Set(prev)
  navEl.value.querySelectorAll('.sp-sub').forEach((ul) => {
    const isOpen = opened.has(ul.dataset.key)
    if (isOpen === before.has(ul.dataset.key)) return
    // 两个方向都先钉到内容自然高：展开从 0 长过去、收起从 auto 定格（auto → 0 不过渡，
    // 必须先钉像素值再强制 reflow），随后展开侧由 transitionend 换 auto、收起侧落 0
    ul.style.height = `${ul.scrollHeight}px`
    if (!isOpen) {
      void ul.offsetHeight
      ul.style.height = '0px'
    }
  })
}, { deep: true, flush: 'post' })

/* 歌单子项是动态数据（异步加载/增删）：数量变化会推移下方所有项，
   高度由 auto 自适应，但胶囊位置要重新对 */
const subSizeSig = computed(() =>
  props.groups.flatMap((group) => group.items).map((item) => item.children?.length ?? 0).join(','),
)
watch(subSizeSig, () => trackFor(300), { flush: 'post' })

function readMorphMs() {
  const raw = getComputedStyle(document.documentElement).getPropertyValue('--sp-dur-morph')
  const n = parseFloat(raw)
  return Number.isFinite(n) ? n : 320
}
</script>

<style scoped>
/* ══ 外壳：宽度形变不裁剪（轨道热区要探出去），裁剪交给内层 ══ */
.sp-sider {
  position: sticky;
  top: 0;
  z-index: 1;
  flex: 0 0 auto;
  width: var(--sp-sider-w);
  height: 100vh;
  transition: width var(--sp-dur-morph) var(--sp-ease-glide);
  /*
    折叠时文字层「让位」的统一开关：只在这里算一次，内部元素与父级插槽内容共用。
    用 CSS 变量而不是 :slotted()，是因为插槽内容编译在父级作用域，
    子组件的 scoped 选择器够不到它，而自定义属性天然沿 DOM 继承。
  */
  --sp-fade-opacity: 1;
  --sp-fade-shift: 0px;
  --sp-fade-dur: var(--sp-dur-base);
  --sp-fade-delay: var(--sp-dur-label-delay);
}
.sp-sider[data-collapsed='true'] {
  width: var(--sp-sider-rail-w);
  --sp-fade-opacity: 0;
  --sp-fade-shift: -4px;
  --sp-fade-dur: var(--sp-dur-fast);
  --sp-fade-delay: 0ms;
}

.sp-sider-clip {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  background: var(--sp-ui-card);
  border-right: 1px solid var(--sp-ui-border);
}

.sp-sider-head { flex: 0 0 auto }
.sp-sider-foot { flex: 0 0 auto }

/* ══ 导航：胶囊的包含块。它同时是滚动容器，于是胶囊随内容一起滚 ══ */
.sp-nav {
  position: relative;
  flex: 1 1 auto;
  min-height: 0;
  padding: 2px var(--sp-sider-pad) 8px;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.sp-pill-layer {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
}

.sp-pill {
  position: absolute;
  top: 0;
  /* 横向不做 JS 动画：left/right 跟随侧边栏宽度自动伸缩，折叠时天然与形变同步 */
  left: var(--sp-sider-pad);
  right: var(--sp-sider-pad);
  height: 0;
  border-radius: var(--sp-radius-md);
  will-change: transform;
}
/* 底色直接用全站既有的「激活叠加层 / 悬停叠加层」token，不另造 alpha 数值：
   两个胶囊的浓淡关系（激活实、悬停淡）与 Naive 下拉项一致，明暗两套自动跟随。
   `opacity` 因此空出来专管悬停胶囊的淡入淡出，不会和底色打架。 */
.sp-pill-active { background: var(--sp-ui-primary-soft) }
.sp-pill-hover {
  background: var(--sp-ui-hover);
  opacity: 0;
  transition: opacity var(--sp-dur-fast) var(--sp-ease-enter);
}
.sp-pill-hover[data-on='true'] { opacity: 1 }

.sp-group { display: flex; flex-direction: column }

.sp-group-label {
  display: flex;
  align-items: center;
  height: var(--sp-sider-group-label-h);
  padding: 0 10px;
  font-size: var(--sp-fs-micro);
  font-weight: var(--sp-fw-medium);
  letter-spacing: 0.06em;
  color: var(--sp-ui-text-3);
}

.sp-menu {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.sp-item { position: relative }

/* 一级项：图标固定贴 padding-left，于是「折叠时 paddingLeft = (轨道宽 − 图标宽)/2」
   就等于图标居中 —— 不依赖后面还有几个元素、各自多宽。 */
.sp-item-btn {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  height: var(--sp-sider-item-h);
  padding: 0 10px;
  overflow: hidden;
  border: 0;
  border-radius: var(--sp-radius-md);
  background: none;
  color: var(--sp-ui-text-2);
  font-size: var(--sp-fs-body);
  font-weight: var(--sp-fw-medium);
  text-align: left;
  text-decoration: none;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transition:
    color var(--sp-dur-fast) var(--sp-ease-enter),
    transform var(--sp-dur-fast) var(--sp-ease-enter),
    padding var(--sp-dur-morph) var(--sp-ease-glide);
}
.sp-sider[data-collapsed='true'] .sp-item-btn { padding-left: 16px; padding-right: 0 }
.sp-item-btn:hover,
.sp-item-btn:focus-visible { color: var(--sp-ui-text-1) }
.sp-item-btn:active { transform: scale(0.98) }
.sp-item-btn[aria-current='page'] { color: var(--sp-ui-primary) }

.sp-ico {
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  width: var(--sp-icon-md);
  height: var(--sp-icon-md);
  /* @vicons 图标按 1em 取值，字号即图标尺寸 —— 于是尺寸也走 token，不必给组件传 :size */
  font-size: var(--sp-icon-md);
}
.sp-ico :deep(svg) { display: block }

.sp-item-label {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.sp-item-chev {
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  width: 16px;
  font-size: 14px;
  color: var(--sp-ui-text-3);
  transition: transform var(--sp-dur-base) var(--sp-ease-glide);
}
.sp-item[data-open='true'] .sp-item-chev { transform: rotate(90deg) }

/* ══ 二级菜单 ══ */
.sp-sub {
  margin: 0 0 0 20px;
  padding: 0 0 0 12px;
  height: 0;
  overflow: hidden;
  list-style: none;
  border-left: 1px solid var(--sp-ui-border);
  transition: height var(--sp-dur-base) var(--sp-ease-glide);
}

.sp-sub-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  height: var(--sp-sider-sub-item-h);
  padding: 0 10px;
  border-radius: var(--sp-radius-sm);
  color: var(--sp-ui-text-3);
  font-size: var(--sp-fs-small);
  text-decoration: none;
  opacity: 0;
  transform: translateY(-6px);
  filter: blur(var(--sp-sub-blur));
  -webkit-tap-highlight-color: transparent;
  /* 错峰延迟只挂在「入场三件套」上，颜色单独走 0 延迟 ——
     否则鼠标一划过去，hover 变色也要等 i×45ms，手感发黏 */
  transition:
    opacity var(--sp-dur-base) var(--sp-ease-enter) var(--d, 0ms),
    transform var(--sp-dur-base) var(--sp-ease-enter) var(--d, 0ms),
    filter var(--sp-dur-base) var(--sp-ease-enter) var(--d, 0ms),
    color var(--sp-dur-fast) var(--sp-ease-enter) 0ms;
}
/* 展开：正序、慢步长（--i）；收起：倒序、快步长（--rev）—— 退比进快，不留拖尾。
   --i / --rev 由模板按子项下标给出，延迟在 CSS 里算，JS 不碰。 */
.sp-sub[data-open='true'] .sp-sub-btn { --d: calc(var(--i, 0) * var(--sp-dur-stagger)) }
.sp-sub[data-open='false'] .sp-sub-btn { --d: calc(var(--rev, 0) * var(--sp-dur-stagger-out)) }

.sp-sub[data-open='true'] .sp-sub-btn { opacity: 1; transform: none; filter: blur(0) }
.sp-sub-btn:hover,
.sp-sub-btn:focus-visible { color: var(--sp-ui-text-1) }
.sp-sub-btn[aria-current='page'] {
  color: var(--sp-ui-primary);
  font-weight: var(--sp-fw-semibold);
}

/* ══ 接缝热区 ══ */
.sp-rail {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 20;
  width: 10px;
  padding: 0;
  border: 0;
  background: none;
  cursor: pointer;
}
.sp-rail::after {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: 50%;
  width: 1px;
  background: transparent;
  transition: background var(--sp-dur-fast) var(--sp-ease-enter);
}
.sp-rail:hover::after,
.sp-rail:focus-visible::after { background: var(--sp-ui-border) }
</style>
