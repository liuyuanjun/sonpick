<template>
  <n-space vertical align="center" justify="center" class="login-page">
    <n-card title="拾音 Sonpick" class="login-card">
      <n-space vertical>
        <n-input
          v-model:value="password"
          type="password"
          placeholder="请输入密码"
          size="large"
          @keydown.enter="handleLogin"
        />
        <n-button type="primary" size="large" block :loading="loading" @click="handleLogin">
          登录
        </n-button>
      </n-space>
    </n-card>
  </n-space>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { useAuthStore } from '@/stores/auth'

const password = ref('')
const loading = ref(false)
const router = useRouter()
const message = useMessage()
const auth = useAuthStore()

async function handleLogin() {
  if (!password.value) {
    message.warning('请输入密码')
    return
  }
  loading.value = true
  try {
    await auth.login(password.value)
    message.success('登录成功')
    router.push('/')
  } catch (err) {
    message.error(err.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  width: 100%;
  padding: 16px;
  box-sizing: border-box;
}
.login-card {
  width: min(360px, 100%);
  border-radius: 16px;
}
</style>
