<template>
  <div class="login-page">
    <div class="login-shell">
      <!-- 左：品牌区 —— LOGO + 吉祥物 + 标语 -->
      <aside class="brand-pane">
        <span class="brand-glow" aria-hidden="true" />
        <div class="brand-inner">
          <img class="brand-logo" src="/brand/logo.svg" alt="Sonpick 拾音" />
          <div class="brand-name">
            <span class="brand-en">Sonpick</span>
            <span class="brand-cn">拾音</span>
          </div>
          <img class="brand-mascot" src="/brand/mascot/mascot-main.png" alt="拾耳" />
          <p class="brand-slogan">听见，然后收藏。</p>
        </div>
      </aside>

      <!-- 右：表单区 -->
      <section class="form-pane">
        <div class="form-inner">
          <h1 class="form-title">{{ needsSetup ? '设置管理员密码' : '欢迎回来' }}</h1>
          <p class="form-sub">
            {{ needsSetup ? '首次使用，设置一个至少 6 位的密码' : '输入密码，进入你的曲库' }}
          </p>

          <n-input
            v-model:value="password"
            type="password"
            show-password-on="click"
            :placeholder="needsSetup ? '设置密码' : '请输入密码'"
            size="large"
            class="form-input"
            @keydown.enter="handleSubmit"
          />
          <n-input
            v-if="needsSetup"
            v-model:value="passwordConfirm"
            type="password"
            show-password-on="click"
            placeholder="再次输入密码"
            size="large"
            class="form-input"
            @keydown.enter="handleSubmit"
          />
          <n-button type="primary" size="large" block :loading="loading" @click="handleSubmit">
            {{ needsSetup ? '完成设置' : '登录' }}
          </n-button>

          <p class="form-foot">个人音乐下载与管理 · NAS 自部署</p>
        </div>
      </section>
    </div>
  </div>
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
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  box-sizing: border-box;
  background:
    radial-gradient(900px 520px at 18% 18%, rgba(52, 211, 153, 0.10), transparent 62%),
    radial-gradient(820px 520px at 84% 80%, rgba(99, 102, 241, 0.12), transparent 62%),
    var(--sp-bg, #0B0C10);
}

.login-shell {
  display: flex;
  width: min(920px, 100%);
  border-radius: 24px;
  overflow: hidden;
  border: 1px solid var(--sp-border, #23262F);
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.5);
  background: var(--sp-surface, #14161C);
}

/* ── 左：品牌区 ───────────────────────── */
.brand-pane {
  position: relative;
  width: 380px;
  flex: none;
  padding: 40px 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #0B0C10;
  border-right: 1px solid var(--sp-border, #23262F);
  overflow: hidden;
}

.brand-glow {
  position: absolute;
  left: -20%;
  right: -20%;
  top: -30%;
  height: 75%;
  background: radial-gradient(closest-side, rgba(52, 211, 153, 0.22), transparent 70%);
  pointer-events: none;
}

.brand-inner {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.brand-logo {
  width: 88px;
  height: 88px;
  border-radius: 20px;
  display: block;
}

.brand-name {
  margin-top: 18px;
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.brand-en {
  font-size: 26px;
  font-weight: 800;
  letter-spacing: 0.01em;
  color: #F2F4F7;
}

.brand-cn {
  font-size: 17px;
  font-weight: 600;
  color: var(--sp-primary-400, #34D399);
}

.brand-mascot {
  width: 190px;
  height: 190px;
  object-fit: contain;
  margin: 18px 0 8px;
  display: block;
}

.brand-slogan {
  margin: 0;
  font-size: 15px;
  color: var(--sp-text-2, #8B95A5);
  letter-spacing: 0.04em;
}

/* ── 右：表单区 ───────────────────────── */
.form-pane {
  flex: 1;
  min-width: 0;
  padding: 48px 44px;
  display: flex;
  align-items: center;
}

.form-inner {
  width: 100%;
  max-width: 320px;
  margin: 0 auto;
}

.form-title {
  margin: 0 0 8px;
  font-size: 24px;
  font-weight: 700;
  color: var(--sp-text, #ECEEF2);
}

.form-sub {
  margin: 0 0 24px;
  font-size: 14px;
  color: var(--sp-text-2, #8B95A5);
}

.form-input {
  margin-bottom: 14px;
}

.form-foot {
  margin: 22px 0 0;
  font-size: 12px;
  color: #6B7280;
  text-align: center;
}

/* ── 响应式 ───────────────────────────── */
@media (max-width: 820px) {
  .login-shell {
    flex-direction: column;
    width: min(420px, 100%);
  }
  .brand-pane {
    width: 100%;
    border-right: none;
    border-bottom: 1px solid var(--sp-border, #23262F);
    padding: 32px 24px 24px;
  }
  .brand-logo {
    width: 64px;
    height: 64px;
    border-radius: 16px;
  }
  .brand-mascot {
    width: 130px;
    height: 130px;
    margin: 12px 0 4px;
  }
  .form-pane {
    padding: 28px 24px 32px;
  }
}
</style>
