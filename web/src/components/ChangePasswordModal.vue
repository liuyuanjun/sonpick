<template>
  <n-modal
    v-model:show="show"
    preset="dialog"
    title="修改密码"
    positive-text="确认修改"
    negative-text="取消"
    :loading="changing"
    @positive-click="handleChangePassword"
  >
    <n-space vertical>
      <n-input v-model:value="form.old" type="password" show-password-on="click" placeholder="当前密码" />
      <n-input v-model:value="form.new" type="password" show-password-on="click" placeholder="新密码（至少 6 位）" />
      <n-input v-model:value="form.confirm" type="password" show-password-on="click" placeholder="再次输入新密码" />
    </n-space>
  </n-modal>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { useAuthStore } from '@/stores/auth'

// 修改密码弹窗：LayoutView 左下账户抽屉与设置页账户区共用，避免两处各维护一份表单逻辑
const show = defineModel('show', { type: Boolean, default: false })

const auth = useAuthStore()
const message = useMessage()
const changing = ref(false)
const form = reactive({ old: '', new: '', confirm: '' })

async function handleChangePassword() {
  if (!form.old || !form.new) {
    message.warning('请填写完整')
    return false
  }
  if (form.new.length < 6) {
    message.warning('新密码至少 6 位')
    return false
  }
  if (form.new !== form.confirm) {
    message.warning('两次新密码不一致')
    return false
  }
  changing.value = true
  try {
    await auth.changePassword(form.old, form.new)
    message.success('密码已修改')
    form.old = ''
    form.new = ''
    form.confirm = ''
  } catch (err) {
    message.error(err.response?.data?.detail || '修改失败')
    return false
  } finally {
    changing.value = false
  }
}
</script>
