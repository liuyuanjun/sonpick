import { defineStore } from 'pinia'
import { computed, ref, watchEffect } from 'vue'
import { darkTheme, lightTheme } from 'naive-ui'
import { buildCssVars, buildNaiveOverrides, THEME_COLOR } from '@/theme/tokens'

const STORAGE_KEY = 'sonpick_theme'
const DARK_QUERY = '(prefers-color-scheme: dark)'
const MODES = ['light', 'dark', 'system']

function readStoredMode() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return MODES.includes(raw) ? raw : null
  } catch {
    return null
  }
}

export const useThemeStore = defineStore('theme', () => {
  // 无存储值时跟随系统，不预设暗色。旧版本只存 'light'/'dark'，可平滑兼容
  const mode = ref(readStoredMode() || 'system')
  const systemDark = ref(false)
  let media = null

  const isDark = computed(() => (mode.value === 'system' ? systemDark.value : mode.value === 'dark'))
  const naiveTheme = computed(() => (isDark.value ? darkTheme : lightTheme))
  const naiveOverrides = computed(() => buildNaiveOverrides(isDark.value))

  function applyToDocument() {
    const root = document.documentElement
    const dark = isDark.value
    root.dataset.theme = dark ? 'dark' : 'light'
    const vars = buildCssVars(dark)
    for (const key of Object.keys(vars)) {
      root.style.setProperty(key, vars[key])
    }
    const meta = document.querySelector('meta[name="theme-color"]')
    if (meta) meta.setAttribute('content', dark ? THEME_COLOR.dark : THEME_COLOR.light)
  }

  function setMode(next) {
    if (!MODES.includes(next)) return
    mode.value = next
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      /* 隐私模式下 localStorage 不可写，忽略 */
    }
  }

  function toggle() {
    // 二态切换：从当前解析值取反，切完即固化为显式偏好
    setMode(isDark.value ? 'light' : 'dark')
  }

  function init() {
    if (media) return
    media = window.matchMedia(DARK_QUERY)
    const onChange = (event) => {
      systemDark.value = event.matches
    }
    if (typeof media.addEventListener === 'function') {
      media.addEventListener('change', onChange)
    } else if (typeof media.addListener === 'function') {
      media.addListener(onChange)
    }
    systemDark.value = media.matches
  }

  // 主题变化立即同步到 DOM。变量写在 documentElement 上，
  // 这样被 teleport 到 body 的 modal / drawer / popover 也能取到
  watchEffect(applyToDocument)

  return { mode, isDark, naiveTheme, naiveOverrides, init, setMode, toggle }
})
