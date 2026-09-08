/**
 * Sonpick 拾音 · 主题 Token 单一真相源
 *
 * 全站颜色只允许从本文件派生，禁止在组件里写死颜色。
 * 产出两份东西：
 *   1. Naive UI 的 themeOverrides（供 n-config-provider）
 *   2. 注入到 :root 的 CSS 变量（供业务组件样式消费，命名 --sp-ui-*）
 *
 * 明亮模式的主色/语义色做了对比度降级（见 LIGHT 注释），
 * 保证白底 + 白字 / 彩色文字满足 WCAG AA 4.5:1。
 */

/** 品牌语义色：与明暗模式无关的部分（色相锚点），按模式给出达标的具体值 */
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
    hover: 'rgba(255, 255, 255, 0.06)',
    'on-primary': '#04120C',
    'primary-soft': 'rgba(16, 185, 129, 0.14)',
    'primary-soft-2': 'rgba(16, 185, 129, 0.22)',
  },
  light: {
    'card-strong': '#FFFFFF',
    hover: 'rgba(15, 23, 42, 0.05)',
    'on-primary': '#FFFFFF',
    'primary-soft': 'rgba(4, 120, 87, 0.10)',
    'primary-soft-2': 'rgba(4, 120, 87, 0.16)',
  },
}

/** 生成 Naive UI 的 themeOverrides.common */
export function buildNaiveOverrides(isDark) {
  const key = isDark ? 'dark' : 'light'
  return { common: { ...BRAND[key], ...SURFACE[key] } }
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
  return {
    '--sp-ui-body': t.bodyColor,
    '--sp-ui-card': t.cardColor,
    '--sp-ui-card-strong': d['card-strong'],
    '--sp-ui-elevated': t.modalColor,
    '--sp-ui-border': t.borderColor,
    '--sp-ui-divider': t.dividerColor,
    '--sp-ui-text-1': t.textColor1,
    '--sp-ui-text-2': t.textColor2,
    '--sp-ui-text-3': t.textColor3,
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
    ...accentVars(isDark),
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

/** 浏览器地址栏 / PWA 主题色 */
export const THEME_COLOR = { dark: '#0B0C10', light: '#F5F6F8' }

/**
 * 分类强调色（概览页 KPI / 快捷入口 / 活动流等「按类别上色」的场景）。
 * 亮色取 700 级、暗色取 400 级，两套都对该模式的卡片底色满足 WCAG AA 4.5:1：
 *   亮色 #FFF 底需 L ≤ 0.183；暗色 #14161C 底需 L ≥ 0.209。
 * 禁止在业务代码里再写死这些色值，一律用 var(--sp-accent-*)。
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
