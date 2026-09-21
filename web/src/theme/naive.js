/**
 * Sonpick 拾音 · Naive UI 适配层
 *
 * 职责单一：把 `theme/tokens.js` 的设计 Token 翻译成 Naive UI 的 `themeOverrides`。
 * 这里是 token 体系的两个出口之一（另一个是 buildCssVars 注入的 CSS 变量）。
 *
 * ══ 为什么这个文件是必须的（不是可选的优化）══
 * Naive UI 的 `common` 自带一套与 Sonpick 规范冲突的默认值，实测泄漏到全站：
 *   borderRadius: '3px'        → 曲库页 61 个元素、日志/设置各 22 个元素渲染成 3px 直角
 *   borderRadiusSmall: '2px'
 *   fontWeightStrong: '500'    → 与规范的 600 冲突
 *   fontFamily: 'v-sans, …'    → 声明了 Inter 却永不生效，且部分节点回落成 Arial
 *   heightMedium: '34px'       → 与「触控目标 ≥36px」冲突
 *   Empty.iconSizeMedium: 40px → 空状态图标脱离排版尺度
 * **业务 CSS 无法覆盖这些默认值**（Naive 把它们写在元素 inline style 上），
 * 所以圆角/字号/字重这类维度必须在这里一次性收口，而不是逐个组件打补丁。
 *
 * ══ 覆盖 key 的来源 ══
 * 下方每个 key 均已在 `node_modules/naive-ui/es/<组件>/styles/light.mjs` 中核实存在。
 * Naive 会静默忽略未知 key —— 因此**新增覆盖项时务必先核实 key 名**，
 * 否则会写出「看着改了、实际没生效」的假修复。
 */

import { FONT, TYPE, RADIUS, LAYOUT, MOTION, SHADOW, buildCommonColors } from './tokens'

const px = (n) => `${n}px`

export function buildNaiveOverrides(isDark) {
  const key = isDark ? 'dark' : 'light'
  const colors = buildCommonColors(isDark)

  return {
    common: {
      ...colors,

      // ── 字体：Inter 必须真正落到 font-family 上
      fontFamily: FONT.ui,
      fontFamilyMono: FONT.mono,
      fontWeight: String(TYPE.body.weight),
      fontWeightStrong: String(TYPE.strong.weight),

      // ── 圆角：Naive 默认 3px / 2px 是全站「廉价感」的头号来源
      borderRadius: px(RADIUS.md),
      borderRadiusSmall: px(RADIUS.sm),

      // ── 字号：对齐 Type Scale，杜绝 13.3333px 这类 UA 默认值渗出
      fontSize: px(TYPE.body.size),
      fontSizeMini: px(TYPE.micro.size),
      fontSizeTiny: px(TYPE.caption.size),
      fontSizeSmall: px(TYPE.small.size),
      fontSizeMedium: px(TYPE.body.size),
      fontSizeLarge: px(TYPE.h3.size),
      fontSizeHuge: px(TYPE.h3.size),
      lineHeight: String(TYPE.body.lineHeight),

      // ── 控件高度：落地「触控目标 ≥36px」（Naive 默认 34px 偏小）
      heightMini: '20px',
      heightTiny: '26px',
      heightSmall: '32px',
      heightMedium: px(LAYOUT.touchTargetMin),
      heightLarge: '40px',
      heightHuge: '46px',

      // ── 阴影
      boxShadow1: SHADOW[key].xs,
      boxShadow2: SHADOW[key].md,
      boxShadow3: SHADOW[key].xl,

      // ── 动效缓动
      cubicBezierEaseInOut: MOTION.easeStandard,
      cubicBezierEaseOut: MOTION.easeEnter,
      cubicBezierEaseIn: MOTION.easeExit,
    },

    // ── 逐组件圆角收口（只列真实存在 borderRadius 的组件；不存在者无需设置）
    Button: {
      borderRadiusTiny: px(RADIUS.sm),
      borderRadiusSmall: px(RADIUS.sm),
      borderRadiusMedium: px(RADIUS.md),
      borderRadiusLarge: px(RADIUS.md),
      fontWeight: String(TYPE.strong.weight),
      fontWeightStrong: String(TYPE.strong.weight),
      heightMedium: px(LAYOUT.touchTargetMin),
    },
    Card: { borderRadius: px(RADIUS.lg) },
    Input: { borderRadius: px(RADIUS.md) },
    DataTable: {
      borderRadius: px(RADIUS.lg),
      thFontWeight: String(TYPE.strong.weight),
      fontSizeSmall: px(TYPE.caption.size),
      fontSizeMedium: px(TYPE.small.size),
      fontSizeLarge: px(TYPE.body.size),
    },
    Tag: { borderRadius: px(RADIUS.sm), borderRadiusSmall: px(RADIUS.xs) },
    Menu: { borderRadius: px(RADIUS.sm) },
    Dropdown: { borderRadius: px(RADIUS.md) },
    Drawer: { borderRadius: px(RADIUS.xl) },
    Dialog: { borderRadius: px(RADIUS.xl) },
    Pagination: { borderRadius: px(RADIUS.sm) },
    Tooltip: { borderRadius: px(RADIUS.sm) },
    Popover: { borderRadius: px(RADIUS.md) },
    Switch: { borderRadius: px(RADIUS.pill) },
    Tabs: { borderRadius: px(RADIUS.md) },
    Alert: { borderRadius: px(RADIUS.md) },
    Breadcrumb: { borderRadius: px(RADIUS.xs) },
    Checkbox: { borderRadius: px(RADIUS.xs), borderRadiusSmall: px(RADIUS.xs) },
    Radio: { borderRadius: RADIUS.circle },
    List: { borderRadius: px(RADIUS.lg) },

    // 下拉选择：Naive 把它拆成两个内部组件，圆角必须分别下发
    Select: {
      peers: {
        InternalSelection: { borderRadius: px(RADIUS.md) },
        InternalSelectMenu: { borderRadius: px(RADIUS.md) },
      },
    },

    // 空状态：统一由 components/StateEmpty.vue 接管，这里只压掉 Naive 的默认色与超尺寸图标
    Empty: {
      iconColor: `color-mix(in srgb, ${colors.textColorBase} ${isDark ? 18 : 16}%, transparent)`,
      textColor: colors.textColor3,
    },
  }
}
