import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/api/client'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('sonpick_token') || '')
  const isLoggedIn = computed(() => !!token.value)

  async function login(password) {
    const res = await api.post('/auth/login', { password })
    token.value = res.data.access_token
    localStorage.setItem('sonpick_token', token.value)
  }

  function logout() {
    token.value = ''
    localStorage.removeItem('sonpick_token')
  }

  return { token, isLoggedIn, login, logout }
})
