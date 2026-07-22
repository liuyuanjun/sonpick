import { ref } from 'vue'

// 全局单例：所有组件共享同一个 matchMedia 监听
const isMobile = ref(false)
let mql = null

function ensureListener() {
  if (mql || typeof window === 'undefined' || !window.matchMedia) return
  mql = window.matchMedia('(max-width: 768px)')
  isMobile.value = mql.matches
  const onChange = (e) => {
    isMobile.value = e.matches
  }
  if (mql.addEventListener) mql.addEventListener('change', onChange)
  else mql.addListener(onChange)
}

export function useIsMobile() {
  ensureListener()
  return isMobile
}
