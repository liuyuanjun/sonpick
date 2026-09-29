/**
 * 跟随胶囊的位移投影 —— 零依赖手写 FLIP。
 *
 * 两个使用方：`components/nav/SpSidebar.vue`（纵向菜单胶囊，axis 'y'）
 * 与 `components/SpPillTabs.vue`（横向页内胶囊 tab，axis 'x'）。
 *
 * ══ 为什么不是「算索引 × 行高」══
 * 目标尺寸不唯一（一级项 36 / 二级项 32 / 每个 tab 宽度还各不相同），
 * 分组标题与子菜单又会动态撑开，用几何常数推算必须额外维护一套映射，
 * 任何一处漏改就整体错位。矩形差值法只问两个问题：
 * 胶囊此刻在哪、目标此刻在哪 —— 永远是对的。
 *
 * ══ 两条硬约束（顺序错了就出鬼）══
 * 1. **先取「当前视觉矩形」作为起点，再改样式**。动画进行中 `getBoundingClientRect()`
 *    返回的就是插值后的位置；顺序反了起点会变成上一次的目标，快速划动时胶囊乱飞。
 * 2. 一律「取消上一个动画 → 立刻写 inline 目标值 → 从捕获的起点起播新动画」。
 *    先写 inline 再播，动画结束时不会有回弹；取消后立刻被 inline 接管，中途改目标不闪。
 *
 * 本模块不引 Vue，只吃 DOM —— 便于在原型页与组件之间共用同一份实现。
 */

/** 从元素作用域里读一个 CSS 变量（token 是唯一真相源，不在这里写死数值） */
function readVar(el, name, fallback) {
  const value = getComputedStyle(el).getPropertyValue(name).trim()
  return value || fallback
}

function readMs(el, name, fallback) {
  const n = parseFloat(readVar(el, name, ''))
  return Number.isFinite(n) ? n : fallback
}

function prefersReducedMotion() {
  return typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches
}

export function createFlowingPill(el, container, options = {}) {
  /**
   * 轴向决定「谁来定尺寸」：
   *   'y'（默认，侧边栏菜单）— 只定纵向位移与高度；**横向交给 CSS** 的 left/right，
   *        侧边栏变宽变窄时胶囊自动跟随，不用 JS 追宽度。
   *   'x'（页内胶囊 tab）— 位置与尺寸**全部**由 JS 从目标矩形取，
   *        因为每个 tab 的宽度都不同，胶囊必须同时改 x 与 width（高度同理）。
   */
  const axis = options.axis === 'x' ? 'x' : 'y'
  let running = null

  /** 目标相对容器的偏移（容器自身的边框要扣掉，绝对定位的原点是 padding box） */
  function offsetOf(node) {
    const c = container.getBoundingClientRect()
    const r = node.getBoundingClientRect()
    return {
      x: r.left - c.left - container.clientLeft,
      y: r.top - c.top - container.clientTop,
      w: r.width,
      h: r.height,
    }
  }

  /**
   * 一个矩形 → 该轴上要写的样式。
   * - 'y'：只写纵向位移与高度。**横向刻意不写 width** —— 那是由 CSS 的 left/right 决定的，
   *   侧边栏变宽变窄时胶囊自动跟随；一旦写了 width 就会跟 CSS 打架。
   * - 'x'：位置与尺寸整份都由 JS 接管（每个 tab 宽度不同），所以 x 与 y 都要写 ——
   *   容器有内边距时（如 tab 轨道 padding 4px），只写 x 会让胶囊纵向差一个内边距。
   */
  function shapeOf(m) {
    return axis === 'x'
      ? { transform: `translate3d(${m.x}px, ${m.y}px, 0)`, width: `${m.w}px`, height: `${m.h}px` }
      : { transform: `translate3d(0, ${m.y}px, 0)`, height: `${m.h}px` }
  }

  function paint(shape) {
    el.style.transform = shape.transform
    el.style.height = shape.height
    if (shape.width !== undefined) el.style.width = shape.width
  }

  /** 该轴上的「延展量」。为 0 说明胶囊还没落过位（初始尺寸 0），没有可插值的起点 */
  function extentOf(m) {
    return axis === 'x' ? m.w : m.h
  }

  function place(target, animate) {
    if (!el || !target || !target.isConnected) return

    const from = offsetOf(el)          // ← 必须在动样式之前
    const to = offsetOf(target)

    if (running) running.cancel()
    running = null

    paint(shapeOf(to))

    if (!animate || extentOf(from) === 0 || prefersReducedMotion()) return

    const anim = el.animate([shapeOf(from), shapeOf(to)], {
      duration: readMs(container, '--sp-dur-glide', 380),
      easing: readVar(container, '--sp-ease-glide', 'cubic-bezier(.32, .72, 0, 1)'),
    })
    running = anim
    // cancel() 会让 finished reject，必须接住，否则控制台留一堆 unhandled rejection
    anim.finished.then(() => { if (running === anim) running = null }).catch(() => {})
  }

  /** 有动画在飞。位置追踪逻辑靠它避让，否则会把滑移动画「钉」在中途 */
  function busy() {
    return running !== null
  }

  return { place, busy }
}
