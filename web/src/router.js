import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { normalizePlayerSection } from '@/stores/player'
import LayoutView from '@/views/LayoutView.vue'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
  },
  {
    path: '/',
    component: LayoutView,
    meta: { requiresAuth: true },
    children: [
      { path: '', name: 'Dashboard', component: () => import('@/views/DashboardView.vue') },
      { path: 'download', name: 'Download', component: () => import('@/views/DownloadView.vue') },
      { path: 'search', redirect: '/download' },
      { path: 'import', redirect: { path: '/download', query: { tab: 'import' } } },
      { path: 'library', name: 'Library', component: () => import('@/views/LibraryView.vue') },
      { path: 'player', redirect: '/player/favorites' },
      {
        path: 'player/:section?',
        name: 'Player',
        component: () => import('@/views/PlayerView.vue'),
        // 非法二级列表（手输地址 / 旧书签）直接纠正到「我喜欢的」，避免侧边栏无高亮
        beforeEnter: (to) => {
          const section = normalizePlayerSection(to.params.section)
          if (section === to.params.section) return true
          return { name: 'Player', params: { section }, replace: true }
        },
      },
      { path: 'sources', redirect: '/library' },
      { path: 'webdav', name: 'WebDAV', component: () => import('@/views/WebDAVView.vue') },
      { path: 'logs', name: 'Logs', component: () => import('@/views/LogsView.vue') },
      { path: 'settings', name: 'Settings', component: () => import('@/views/SettingsView.vue') },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.token) {
    next('/login')
  } else if (to.path === '/login' && auth.token) {
    next('/')
  } else {
    next()
  }
})

export default router
