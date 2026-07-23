import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/api/client'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('sonpick_token') || '')
  const isLoggedIn = computed(() => !!token.value)

  async function getStatus() {
    const res = await api.get('/auth/status')
    return res.data
  }

  async function login(password) {
    const res = await api.post('/auth/login', { password })
    token.value = res.data.access_token
    localStorage.setItem('sonpick_token', token.value)
  }

  async function setup(password) {
    const res = await api.post('/auth/setup', { password })
    token.value = res.data.access_token
    localStorage.setItem('sonpick_token', token.value)
  }

  async function changePassword(oldPassword, newPassword) {
    await api.put('/auth/password', { old_password: oldPassword, new_password: newPassword })
  }

  function logout() {
    token.value = ''
    localStorage.removeItem('sonpick_token')
  }

  return { token, isLoggedIn, getStatus, login, setup, changePassword, logout }
})
