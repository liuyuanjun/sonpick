<template>
  <n-space vertical align="center" justify="center" class="login-page">
    <n-card :title="needsSetup ? '设置管理员密码' : '拾音 Sonpick'" class="login-card">
      <n-space vertical>
        <n-text v-if="needsSetup" depth="3" style="margin-bottom: 4px">
          首次使用，请设置管理员密码（至少 6 位）。
        </n-text>
        <n-input
          v-model:value="password"
          type="password"
          show-password-on="click"
          :placeholder="needsSetup ? '设置密码' : '请输入密码'"
          size="large"
          @keydown.enter="handleSubmit"
        />
        <n-input
          v-if="needsSetup"
          v-model:value="passwordConfirm"
          type="password"
          show-password-on="click"
          placeholder="再次输入密码"
          size="large"
          @keydown.enter="handleSubmit"
        />
        <n-button type="primary" size="large" block :loading="loading" @click="handleSubmit">
          {{ needsSetup ? '完成设置' : '登录' }}
        </n-button>
      </n-space>
    </n-card>
  </n-space>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { useAuthStore } from '@/stores/auth'

const password = ref('')
const passwordConfirm = ref('')
const loading = ref(false)
const needsSetup = ref(false)
const router = useRouter()
const message = useMessage()
const auth = useAuthStore()

onMounted(async () => {
  try {
    const status = await auth.getStatus()
    needsSetup.value = !status.initialized
  } catch {
    // 接口不可用时退回登录态
  }
})

async function handleSubmit() {
  if (!password.value) {
    message.warning('请输入密码')
    return
  }
  if (needsSetup.value) {
    if (password.value.length < 6) {
      message.warning('密码至少 6 位')
      return
    }
    if (password.value !== passwordConfirm.value) {
      message.warning('两次输入不一致')
      return
    }
    loading.value = true
    try {
      await auth.setup(password.value)
      message.success('设置成功')
      router.push('/')
    } catch (err) {
      message.error(err.response?.data?.detail || '设置失败')
    } finally {
      loading.value = false
    }
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
