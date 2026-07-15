<template>
  <n-space vertical size="large" style="width: 100%">
    <n-card title="导入歌单下载">
      <n-space vertical style="width: 100%">
        <n-space>
          <n-button size="small" @click="selectFile">选择歌单文件</n-button>
          <n-text depth="3">支持 .txt 文件，每行一首</n-text>
        </n-space>
        <input ref="fileInput" type="file" accept=".txt" style="display: none" @change="onFileChange" />

        <n-form-item label="粘贴歌单（每行一首：歌名 - 歌手）">
          <n-input
            v-model:value="content"
            type="textarea"
            placeholder="例如：\n停了的钟 - 萧煌奇\n淋雨一直走 - 张韶涵"
            :autosize="{ minRows: 10, maxRows: 20 }"
          />
        </n-form-item>

        <n-form-item label="优先格式">
          <n-radio-group v-model:value="prefer">
            <n-radio-button value="flac">FLAC</n-radio-button>
            <n-radio-button value="mp3">MP3/M4A</n-radio-button>
            <n-radio-button value="any">任意</n-radio-button>
          </n-radio-group>
        </n-form-item>

        <n-button type="primary" :loading="submitting" @click="submit">开始批量下载</n-button>
      </n-space>
    </n-card>
  </n-space>
</template>

<script setup>
import { ref } from 'vue'
import { useMessage, NText } from 'naive-ui'
import api from '@/api/client'

const content = ref('')
const prefer = ref('mp3')
const submitting = ref(false)
const fileInput = ref(null)
const message = useMessage()

function selectFile() {
  fileInput.value?.click()
}

function onFileChange(e) {
  const file = e.target.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = (ev) => {
    content.value = String(ev.target.result || '')
    message.success(`已加载 ${file.name}`)
  }
  reader.onerror = () => message.error('读取文件失败')
  reader.readAsText(file)
  e.target.value = ''
}

async function submit() {
  if (!content.value.trim()) {
    message.warning('请输入歌单内容')
    return
  }
  submitting.value = true
  try {
    await api.post('/download/batch', {
      content: content.value,
      prefer: prefer.value,
    })
    message.success('已加入批量下载队列')
    content.value = ''
  } catch (err) {
    message.error(err.response?.data?.detail || '提交失败')
  } finally {
    submitting.value = false
  }
}
</script>
