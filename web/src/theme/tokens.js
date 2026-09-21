/**
 * Sonpick 拾音 · 设计 Token 单一真相源
 *
 * ══ 唯一权威 ══
 * 全站任何颜色、字号、字重、圆角、间距、阴影、动效、层级，只允许从本文件派生。
 * 禁止在组件里写死数值。派生出的两份产物：
 *   1. `buildCssVars(isDark)` → 注入 `:root` 的 CSS 变量（业务样式消费，命名 `--sp-*`）
 *   2. `theme/naive.js` 的 `buildNaiveOverrides(isDark)` → Naive UI 的 themeOverrides
 *
 * ══ 为什么必须是「一份数据、两个出口」══
 * 实测教训：Naive 组件自带默认圆角（实测泄漏出 3px / 22px / 34px），业务 CSS 再怎么改都压不住。
 * 因此圆角/字号/控件高度这些维度**必须同时走 themeOverrides 与 CSS 变量两条路**，
 * 否则会出现「自己写的卡片是 12px、Naive 的卡片是 3px」这类分裂。
 *
 * ══ 变量定义在 documentElement 而非容器上 ══
 * 这样被 teleport 到 body 的 modal / drawer / popover 才取得到。
 * 反过来说：**浮层内的样式只允许引用 `:root` 变量**，不得引用挂载点局部变量。
 *
 * ══ 颜色纪律 ══
 * 明亮模式的主色/语义色做了对比度降级（见 BRAND.light 注释），
 * 保证白底 + 白字 / 彩色文字满足 WCAG AA 4.5:1。改动色值必须重新校验对比度。
 */

// ══════════════════════════════════════════════════════════════════════════
// 1 · 字体族
// ══════════════════════════════════════════════════════════════════════════
/**
 * 西文与数字：Inter（自托管 latin 子集，5 个字重共约 120KB，见 styles/fonts.css）。
 * 中文：系统 CJK 栈。理由——中文 webfont 体积以 MB 计，与 NAS 自托管 / 离线可用场景冲突；
 * 而各平台系统 CJK 字体（PingFang SC / 微软雅黑 / Noto Sans CJK）观感均达标。
 * 若日后要自托管中文，装 `@fontsource/noto-sans-sc` 并在 styles/fonts.css 追加即可，
 * 无需改动本文件——中文字体位已预留在栈内。
 */
export const FONT = {
  ui: '"Inter", "PingFang SC", "Noto Sans SC", "Noto Sans CJK SC", "Microsoft YaHei", system-ui, -apple-system, sans-serif',
  mono: '"SF Mono", "JetBrains Mono", ui-monospace, Menlo, Consolas, monospace',
}

/** 数字等宽：时长 / 体积 / 进度 / 时间列必须 font-variant-numeric: tabular-nums */
export const NUMERIC_FEATURE = '"tnum" 1, "cv01" 1'

// ══════════════════════════════════════════════════════════════════════════
// 2 · 排版 Type Scale
// ══════════════════════════════════════════════════════════════════════════
/**
 * 字重纪律：只允许 400 / 500 / 600 / 700 / 800。
 * 历史教训：概览页曾出现 650 / 720 / 760 / 780（7 处声明、影响 32 个文字元素），
 * 造成「非标字重比标准字重还多」（32 : 16），层级信号完全失效。
 *
 * 字号纪律：正文下限 13px。12px 只用于标签 / 元信息 / 角标，不得承载正文。
 *
 * 响应式：display / h1 / h2 带 `mobile` 值，作为 ≤768px 的降级档位。
 * 移动端降级是**尺度的一部分**，不要把它当成违规值另写一个 px。
 */
export const TYPE = {
  display: { size: 32, mobile: 28, weight: 800, lineHeight: 1.15, tracking: '-0.01em', use: '登录品牌名、空状态大标题' },
  h1: { size: 28, mobile: 24, weight: 700, lineHeight: 1.2, tracking: '-0.01em', use: '页面 Hero 标题' },
  h2: { size: 22, mobile: 18, weight: 700, lineHeight: 1.25, tracking: '0', use: '区块大标题、KPI 数值' },
  h3: { size: 16, weight: 700, lineHeight: 1.3, tracking: '0', use: '面板标题' },
  body: { size: 14, weight: 400, lineHeight: 1.6, tracking: '0', use: '正文默认' },
  strong: { size: 14, weight: 600, lineHeight: 1.6, tracking: '0', use: '列表项重点、按钮文字' },
  small: { size: 13, weight: 400, lineHeight: 1.55, tracking: '0', use: '副标题、辅助说明' },
  caption: { size: 12, weight: 500, lineHeight: 1.4, tracking: '0.02em', use: '标签、元信息、KPI 提示' },
  micro: { size: 11, weight: 500, lineHeight: 1.3, tracking: '0.02em', use: '角标、计数' },
}

/**
 * 图标尺度。
 *
 * 图标是独立尺度，不属排版。历史上封面占位字形用 `font-size: 40px` 表达，
 * 混进 Type Scale 就成了「尺度外的字号」，实为口径问题而非真违规。
 * 图标尺寸分两种表达，按场景择一：
 *   - 矢量图标组件（@vicons）：用 `<n-icon :size="24">`
 *   - 字形图标（emoji / 符号字形）：用 `font-size: var(--sp-icon-*)`
 */
export const ICON = { sm: 16, md: 20, lg: 24, xl: 32, '2xl': 40 }

// ══════════════════════════════════════════════════════════════════════════
// 3 · 圆角
// ══════════════════════════════════════════════════════════════════════════
/**
 * 业务 CSS 历史声明过 13 种圆角（4/5/6/7/8/9/10/12/14/16/18/20/24/999/50%），
 * 外加 Naive 默认值泄漏进来的 3px / 22px / 34px。此处收敛为 7 档。
 * 三角形/半圆等特殊形状用 circle 或 pill，不要新造数值。
 */
export const RADIUS = {
  xs: 6, // 微型元素：进度条、骨架、小徽标
  sm: 8, // 次级容器、下拉面板项、表格内标签
  md: 10, // 按钮、输入框、下拉触发器（最高频）
  lg: 12, // 卡片、面板
  xl: 16, // 弹窗、抽屉
  '2xl': 20, // 大容器（移动端底部抽屉、页面级卡片）
  pill: 999,
  circle: '50%',
}

// ══════════════════════════════════════════════════════════════════════════
// 4 · 间距（基数 4px）
// ══════════════════════════════════════════════════════════════════════════
export const SPACE = {
  1: 4,
  2: 8,
  3: 12,
  4: 16,
  5: 20,
  6: 24,
  8: 32,
  10: 40,
  12: 48,
}

/**
 * 语义间距与布局尺度（声明值）。
 * ⚠️ 落地状态：
 *   - touchTargetMin                                   → 已接入（naive.js 的 heightMedium）
 *   - pagePadX / pagePadY / pagePadYMobile / pagePadXMobile → 已接入（LayoutView 的 .content / .header）
 *   - contentMaxWidth                                  → 已接入（LayoutView .content 限宽居中）
 *   - sectionGap / cardPad / cardGap                   → 已在「值匹配处」消费（--sp-space-section / -card-pad / -card-gap）
 *   - iconButtonSize                                   → 已删除（无现实锚点：全站无「圆形按钮 40px」硬编码）
 */
export const LAYOUT = {
  pagePadX: 20, // 页面左右边距（桌面）
  pagePadY: 16,
  pagePadYMobile: 12, // 移动端竖向边距
  pagePadXMobile: 12,
  sectionGap: 16, // 区块之间
  cardPad: 14, // 卡片内边距
  cardGap: 12, // 卡片之间
  contentMaxWidth: 1280, // 内容最大宽度（居中）
  touchTargetMin: 36, // 触控目标最小尺寸
}

// ══════════════════════════════════════════════════════════════════════════
// 5 · 阴影（暗色更实偏黑，亮色更柔偏冷蓝灰）
// ══════════════════════════════════════════════════════════════════════════
export const SHADOW = {
  light: {
    xs: '0 1px 2px rgba(15, 23, 42, .06)',
    sm: '0 4px 10px rgba(15, 23, 42, .06)',
    md: '0 10px 24px rgba(21, 32, 53, .05)',
    lg: '0 14px 34px rgba(21, 32, 53, .06)',
    xl: '0 20px 48px rgba(21, 32, 53, .10)',
    '2xl': '0 24px 60px rgba(15, 23, 42, .18)',
  },
  dark: {
    xs: '0 1px 2px rgba(0, 0, 0, .30)',
    sm: '0 4px 10px rgba(0, 0, 0, .28)',
    md: '0 10px 24px rgba(0, 0, 0, .34)',
    lg: '0 14px 34px rgba(0, 0, 0, .38)',
    xl: '0 20px 48px rgba(0, 0, 0, .44)',
    '2xl': '0 24px 60px rgba(0, 0, 0, .50)',
  },
}

// ══════════════════════════════════════════════════════════════════════════
// 6 · 动效
// ══════════════════════════════════════════════════════════════════════════
/** 只动 transform / opacity。所有持续或大面积动效必须能用 prefers-reduced-motion 关闭。 */
export const MOTION = {
  durFast: 120, // 微交互：hover、按压
  durBase: 200, // 常规：展开、切换
  durSlow: 240, // 浮层进出
  easeEnter: 'cubic-bezier(.22, 1, .36, 1)', // 进入（ease-out 强化）
  easeExit: 'cubic-bezier(.4, 0, 1, 1)', // 退出（ease-in）
  easeStandard: 'cubic-bezier(.4, 0, .2, 1)',
}

// ══════════════════════════════════════════════════════════════════════════
// 7 · 颜色
// ══════════════════════════════════════════════════════════════════════════
/** 品牌语义色：色相锚点，按模式给出达标的具体值 */
const BRAND = {
  dark: {
    primaryColor: '#10B981',
    primaryColorHover: '#34D399',
    primaryColorPressed: '#059669',
    primaryColorSuppl: '#34D399',
    infoColor: '#6366F1',
    infoColorHover: '#818CF8',
    infoColorPressed: '#4F46E5',
    infoColorSuppl: '#818CF8',
    successColor: '#10B981',
    warningColor: '#F59E0B',
    errorColor: '#EF4444',
  },
  // 明亮模式：主色降到品牌色阶 700（#047857）。
  // #10B981 配白字只有 2.65:1，不达 AA；#047857 为 5.55:1。
  // hover 继续加深而非提亮——交互态朝「远离页面底色」的方向走。
  light: {
    primaryColor: '#047857',
    primaryColorHover: '#065F46',
    primaryColorPressed: '#044434',
    primaryColorSuppl: '#065F46',
    infoColor: '#4F46E5',
    infoColorHover: '#4338CA',
    infoColorPressed: '#3730A3',
    infoColorSuppl: '#4338CA',
    successColor: '#047857',
    warningColor: '#B45309',
    errorColor: '#DC2626',
  },
}

/** 表面 / 文字 / 描边：随模式切换 */
const SURFACE = {
  dark: {
    bodyColor: '#0B0C10',
    cardColor: '#14161C',
    modalColor: '#181B22',
    popoverColor: '#181B22',
    borderColor: '#23262F',
    dividerColor: '#23262F',
    textColorBase: '#ECEEF2',
    textColor1: '#ECEEF2',
    textColor2: '#B6BECB',
    textColor3: '#8B95A5',
  },
  light: {
    bodyColor: '#F5F6F8',
    cardColor: '#FFFFFF',
    modalColor: '#FFFFFF',
    popoverColor: '#FFFFFF',
    borderColor: '#E3E6EB',
    dividerColor: '#E8EAEF',
    textColorBase: '#0B0C10',
    textColor1: '#111827',
    textColor2: '#4B5563',
    textColor3: '#6B7280',
  },
}

/** 中性叠加层与派生面：不进 Naive overrides，只以 CSS 变量暴露 */
const DERIVED = {
  dark: {
    'card-strong': '#181B22',
    'table-header': '#181B22',
    hover: 'rgba(255, 255, 255, 0.06)',
    'on-primary': '#04120C',
    'primary-soft': 'rgba(16, 185, 129, 0.14)',
    'primary-soft-2': 'rgba(16, 185, 129, 0.22)',
  },
  light: {
    'card-strong': '#FFFFFF',
    'table-header': '#F7F8FA',
    hover: 'rgba(15, 23, 42, 0.05)',
    'on-primary': '#FFFFFF',
    'primary-soft': 'rgba(4, 120, 87, 0.10)',
    'primary-soft-2': 'rgba(4, 120, 87, 0.16)',
  },
}

/**
 * 分类强调色（概览页 KPI / 快捷入口 / 活动流等「按类别上色」的场景）。
 * 亮色取 700 级、暗色取 400 级，两套都对该模式的卡片底色满足 WCAG AA 4.5:1：
 *   亮色 #FFF 底需 L ≤ 0.183；暗色 #14161C 底需 L ≥ 0.209。
 * 禁止在业务代码里再写死这些色值，一律用 var(--sp-accent-*)。
 *
 * ⚠️ 用量纪律：同一屏内同时出现的强调色不得超过 3 种，否则视觉噪声压过信息本身。
 * 进度条、条形图等「同性质、重复出现」的元素一律用主色或中性色，不得逐个换色
 * （历史问题：概览页三条同性质进度条分别用了绿 / 紫 / 橙，后两者完全在色板之外）。
 */
const ACCENTS = {
  teal: { light: '#0F766E', dark: '#2DD4BF' },
  blue: { light: '#1D4ED8', dark: '#60A5FA' },
  rose: { light: '#BE123C', dark: '#FB7185' },
  amber: { light: '#B45309', dark: '#FBBF24' },
  sky: { light: '#0369A1', dark: '#38BDF8' },
  green: { light: '#15803D', dark: '#4ADE80' },
  slate: { light: '#475569', dark: '#94A3B8' },
}

/** 软底（图标底色）的混色比例：暗底上需要更高比例才可见 */
const ACCENT_SOFT = { dark: 16, light: 12 }

/**
 * 品牌渐变：仅用于 LOGO / 焦点态 / 强调条。
 * 禁止用作大面积背景或浮层氛围光（历史问题：播放器抽屉曾叠三层全屏渐变，
 * 其中紫色 #5856D6 完全在色板之外）。
 */
export const BRAND_GRADIENT = 'linear-gradient(135deg, #64F0AC 0%, #22D3EE 38%, #556FE1 72%, #7A40DC 100%)'

/** 吉祥物「拾耳」色：暖橙专属吉祥物与空状态插画，禁止挪作状态语义色 */
export const MASCOT = { main: '#F5A45D', cream: '#F7F1E8', ink: '#2B2118' }

/** 浏览器地址栏 / PWA 主题色 */
export const THEME_COLOR = { dark: '#0B0C10', light: '#F5F6F8' }

// ══════════════════════════════════════════════════════════════════════════
// 派生：CSS 变量
// ══════════════════════════════════════════════════════════════════════════
function px(n) {
  return typeof n === 'number' ? `${n}px` : n
}

/**
 * 颜色部分的唯一派生出口，供 theme/naive.js 组装 Naive 的 `common`。
 * key 名直接沿用 Naive 的语义命名（primaryColor / cardColor / …），
 * 这样「加一个语义色」只需改本文件的 BRAND / SURFACE，不必动适配层。
 */
export function buildCommonColors(isDark) {
  const key = isDark ? 'dark' : 'light'
  return {
    ...BRAND[key],
    ...SURFACE[key],
    tableHeaderColor: DERIVED[key]['table-header'],
    hoverColor: DERIVED[key].hover,
  }
}

function accentVars(isDark) {
  const key = isDark ? 'dark' : 'light'
  const soft = ACCENT_SOFT[key]
  const vars = {}
  for (const name of Object.keys(ACCENTS)) {
    const fg = ACCENTS[name][key]
    vars[`--sp-accent-${name}`] = fg
    vars[`--sp-accent-${name}-soft`] = `color-mix(in srgb, ${fg} ${soft}%, transparent)`
  }
  return vars
}

/**
 * 生成注入到 :root 的 CSS 变量。
 * 注意：定义在 documentElement 而非某个容器上，
 * 这样被 teleport 到 body 的 modal / drawer / popover 也能取到。
 */
export function buildCssVars(isDark) {
  const key = isDark ? 'dark' : 'light'
  const t = { ...BRAND[key], ...SURFACE[key] }
  const d = DERIVED[key]

  const vars = {
    // ── 颜色：表面与文字
    '--sp-ui-body': t.bodyColor,
    '--sp-ui-card': t.cardColor,
    '--sp-ui-card-strong': d['card-strong'],
    '--sp-ui-elevated': t.modalColor,
    '--sp-ui-border': t.borderColor,
    '--sp-ui-divider': t.dividerColor,
    '--sp-ui-text-1': t.textColor1,
    '--sp-ui-text-2': t.textColor2,
    '--sp-ui-text-3': t.textColor3,
    // ── 颜色：主色与语义
    '--sp-ui-primary': t.primaryColor,
    '--sp-ui-primary-hover': t.primaryColorHover,
    '--sp-ui-primary-pressed': t.primaryColorPressed,
    '--sp-ui-primary-soft': d['primary-soft'],
    '--sp-ui-primary-soft-2': d['primary-soft-2'],
    '--sp-ui-on-primary': d['on-primary'],
    '--sp-ui-info': t.infoColor,
    '--sp-ui-success': t.successColor,
    '--sp-ui-warning': t.warningColor,
    '--sp-ui-error': t.errorColor,
    '--sp-ui-hover': d.hover,
    // ── 字体
    '--sp-font-ui': FONT.ui,
    '--sp-font-mono': FONT.mono,
    // ── 排版
    '--sp-fs-display': px(TYPE.display.size),
    '--sp-fs-h1': px(TYPE.h1.size),
    '--sp-fs-h2': px(TYPE.h2.size),
    '--sp-fs-h3': px(TYPE.h3.size),
    '--sp-fs-body': px(TYPE.body.size),
    '--sp-fs-strong': px(TYPE.strong.size),
    '--sp-fs-small': px(TYPE.small.size),
    '--sp-fs-caption': px(TYPE.caption.size),
    '--sp-fs-micro': px(TYPE.micro.size),
    // 移动端降级档位（≤768px 使用）
    '--sp-fs-display-mobile': px(TYPE.display.mobile),
    '--sp-fs-h1-mobile': px(TYPE.h1.mobile),
    '--sp-fs-h2-mobile': px(TYPE.h2.mobile),
    '--sp-fw-regular': String(TYPE.body.weight),
    '--sp-fw-medium': String(TYPE.caption.weight),
    '--sp-fw-semibold': String(TYPE.strong.weight),
    '--sp-fw-bold': String(TYPE.h3.weight),
    '--sp-fw-extrabold': String(TYPE.display.weight),
    // ── 图标尺度
    '--sp-icon-sm': px(ICON.sm),
    '--sp-icon-md': px(ICON.md),
    '--sp-icon-lg': px(ICON.lg),
    '--sp-icon-xl': px(ICON.xl),
    '--sp-icon-2xl': px(ICON['2xl']),
    // ── 圆角
    '--sp-radius-xs': px(RADIUS.xs),
    '--sp-radius-sm': px(RADIUS.sm),
    '--sp-radius-md': px(RADIUS.md),
    '--sp-radius-lg': px(RADIUS.lg),
    '--sp-radius-xl': px(RADIUS.xl),
    '--sp-radius-2xl': px(RADIUS['2xl']),
    '--sp-radius-pill': px(RADIUS.pill),
    '--sp-radius-circle': RADIUS.circle,
    // ── 语义间距
    '--sp-space-section': px(LAYOUT.sectionGap),
    '--sp-space-card-pad': px(LAYOUT.cardPad),
    '--sp-space-card-gap': px(LAYOUT.cardGap),
    // ── 布局（页面边距 / 内容限宽）
    '--sp-layout-page-pad-y': px(LAYOUT.pagePadY),
    '--sp-layout-page-pad-x': px(LAYOUT.pagePadX),
    '--sp-layout-page-pad-y-mobile': px(LAYOUT.pagePadYMobile),
    '--sp-layout-page-pad-x-mobile': px(LAYOUT.pagePadXMobile),
    '--sp-layout-content-max': px(LAYOUT.contentMaxWidth),
    // ── 阴影
    '--sp-shadow-xs': SHADOW[key].xs,
    '--sp-shadow-sm': SHADOW[key].sm,
    '--sp-shadow-md': SHADOW[key].md,
    '--sp-shadow-lg': SHADOW[key].lg,
    '--sp-shadow-xl': SHADOW[key].xl,
    '--sp-shadow-2xl': SHADOW[key]['2xl'],
    // ── 动效
    '--sp-dur-fast': `${MOTION.durFast}ms`,
    '--sp-dur-base': `${MOTION.durBase}ms`,
    '--sp-dur-slow': `${MOTION.durSlow}ms`,
    '--sp-ease-enter': MOTION.easeEnter,
    '--sp-ease-exit': MOTION.easeExit,
    // ── 品牌
    '--sp-brand-grad': BRAND_GRADIENT,
  }

  for (let i = 1; i <= 12; i += 1) {
    if (SPACE[i] != null) vars[`--sp-space-${i}`] = px(SPACE[i])
  }

  return { ...vars, ...accentVars(isDark) }
}
