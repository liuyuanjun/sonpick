<template>
  <n-space vertical size="large" style="width: 100%">
    <n-card title="系统设置">
      <n-form label-placement="left" label-width="160px">
        <n-form-item label="本地存储路径">
          <n-input v-model:value="form.storage_path" placeholder="例如 /app/downloads" />
        </n-form-item>

        <n-form-item label="默认优先格式">
          <n-radio-group v-model:value="form.prefer_format">
            <n-radio-button value="flac">FLAC</n-radio-button>
            <n-radio-button value="mp3">MP3</n-radio-button>
            <n-radio-button value="m4a">M4A</n-radio-button>
            <n-radio-button value="any">任意</n-radio-button>
          </n-radio-group>
        </n-form-item>

        <n-form-item label="下载后自动转 MP3">
          <n-switch v-model:value="form.auto_convert_mp3" />
        </n-form-item>

        <n-form-item label="下载后自动上传">
          <n-space align="center">
            <n-switch v-model:value="form.auto_upload_webdav" />
            <n-text depth="3">开启后上传到「歌曲源」中的默认 WebDAV 源</n-text>
            <n-button text type="primary" @click="$router.push('/sources')">去配置歌曲源</n-button>
          </n-space>
        </n-form-item>

        <n-form-item>
          <n-button type="primary" :loading="saving" @click="save">保存设置</n-button>
        </n-form-item>
      </n-form>
    </n-card>

    <n-card title="说明">
      <n-text depth="3">
        本地/WebDAV 连接、扫描目录、默认上传源、冲突策略等请到「歌曲源」页面管理。播放器页可直接选择源进行扫描。
      </n-text>
    </n-card>
  </n-space>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useMessage } from 'naive-ui'
import api from '@/api/client'

const message = useMessage()
const saving = ref(false)
const form = reactive({
  storage_path: '',
  prefer_format: 'any',
  auto_convert_mp3: false,
  auto_upload_webdav: false,
})

async function load() {
  try {
    const res = await api.get('/settings')
    const d = res.data || {}
    Object.assign(form, {
      storage_path: d.storage_path || '',
      prefer_format: d.prefer_format || 'any',
      auto_convert_mp3: !!d.auto_convert_mp3,
      auto_upload_webdav: !!d.auto_upload_webdav,
    })
  } catch (err) {
    message.error(err.response?.data?.detail || '加载设置失败')
  }
}

async function save() {
  saving.value = true
  try {
    await api.put('/settings', {
      storage_path: form.storage_path,
      prefer_format: form.prefer_format,
      auto_convert_mp3: form.auto_convert_mp3,
      auto_upload_webdav: form.auto_upload_webdav,
    })
    message.success('设置已保存')
  } catch (err) {
    message.error(err.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>
