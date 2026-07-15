import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useThemeStore = defineStore('theme', () => {
  const isDark = ref(localStorage.getItem('sonpick_theme') === 'dark')

  function toggle() {
    isDark.value = !isDark.value
    localStorage.setItem('sonpick_theme', isDark.value ? 'dark' : 'light')
  }

  function init() {
    const saved = localStorage.getItem('sonpick_theme')
    if (saved) {
      isDark.value = saved === 'dark'
    } else {
      isDark.value = window.matchMedia('(prefers-color-scheme: dark)').matches
    }
  }

  return { isDark, toggle, init }
})
