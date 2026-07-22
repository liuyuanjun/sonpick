<template>
  <n-grid class="settings-layout" cols="1 m:6" responsive="screen" :x-gap="18" :y-gap="18">
    <n-gi span="1 m:1">
      <n-card class="settings-nav" size="small" :bordered="false">
        <n-menu
          v-if="!isMobile"
          v-model:value="activeSection"
          :options="menuOptions"
        />
        <n-tabs
          v-else
          v-model:value="activeSection"
          class="settings-mobile-tabs"
          type="segment"
          size="small"
          justify-content="space-around"
        >
          <n-tab-pane name="general" tab="系统设置" />
          <n-tab-pane name="scrape" tab="刮削源" />
        </n-tabs>
      </n-card>
    </n-gi>
    <n-gi span="1 m:5">
      <n-space vertical size="large" style="width: 100%">
        <template v-if="activeSection === 'general'">
          <n-card title="系统设置">
            <n-form
              class="settings-form"
              :label-placement="isMobile ? 'top' : 'left'"
              :label-width="isMobile ? 'auto' : 160"
            >
              <n-form-item label="本地存储路径">
                <n-input
                  v-model:value="form.storage_path"
                  placeholder="例如 /app/downloads"
                  :input-props="{ autocomplete: 'off', name: 'storage_path' }"
                />
              </n-form-item>
              <n-form-item label="默认优先格式" class="format-item">
                <n-radio-group v-model:value="form.prefer_format" class="format-group" size="small">
                  <n-radio-button value="flac">FLAC</n-radio-button>
                  <n-radio-button value="mp3">MP3</n-radio-button>
                  <n-radio-button value="m4a">M4A</n-radio-button>
                  <n-radio-button value="any">任意</n-radio-button>
                </n-radio-group>
              </n-form-item>
              <n-form-item label="MP3 存放目录">
                <n-space vertical style="width: 100%">
                  <n-input
                    v-model:value="form.mp3_output_path"
                    placeholder="默认：存储目录/MP3"
                    :input-props="{ autocomplete: 'off', name: 'mp3_output_path' }"
                  />
                  <n-text depth="3">MP3 等有损格式（含下载与转码产物）的存放目录；留空使用默认目录；相对路径（如 MP3 或 /MP3）基于本地存储路径解析；多段绝对路径（如 /mnt/nas/mp3）按原样使用。</n-text>
                  <n-text depth="3" class="path-line">实际路径：<code>{{ resolvedMp3Path }}</code></n-text>
                </n-space>
              </n-form-item>
              <n-form-item label="无损存放目录">
                <n-space vertical style="width: 100%">
                  <n-input
                    v-model:value="form.lossless_output_path"
                    placeholder="默认：存储目录/LOSSLESS"
                    :input-props="{ autocomplete: 'off', name: 'lossless_output_path' }"
                  />
                  <n-text depth="3">FLAC/APE/WAV 等无损格式的存放目录，下载无损音乐时落到该目录；留空使用默认目录，路径规则同上。</n-text>
                  <n-text depth="3" class="path-line">实际路径：<code>{{ resolvedLosslessPath }}</code></n-text>
                </n-space>
              </n-form-item>
              <n-form-item label="无损优先播放">
                <n-space class="switch-row" align="center" :wrap="true">
                  <n-switch v-model:value="form.lossless_preferred" />
                  <n-text depth="3">开启优先 FLAC；关闭优先 MP3，缺失时自动回退。</n-text>
                </n-space>
              </n-form-item>
              <n-form-item label="无损优先关闭时自动转 MP3">
                <n-switch
                  v-model:value="form.auto_convert_when_lossless_not_preferred"
                  :disabled="form.lossless_preferred"
                />
              </n-form-item>
              <n-form-item label="下载后自动上传">
                <n-space class="switch-row" align="center" :wrap="true">
                  <n-switch v-model:value="form.auto_upload_webdav" />
                  <n-text depth="3">上传至曲库中的默认 WebDAV 源</n-text>
                  <n-button text type="primary" @click="$router.push({ path: '/library', query: { manage: '1' } })">去配置曲库源</n-button>
                </n-space>
              </n-form-item>
              <n-form-item label="AcoustID API Key">
                <n-space vertical style="width: 100%">
                  <n-input
                    v-model:value="acoustidApiKey"
                    type="password"
                    show-password-on="click"
                    placeholder="留空则不修改已保存的密钥"
                    :input-props="{ autocomplete: 'new-password', name: 'acoustid_api_key' }"
                  />
                  <n-text depth="3">用于 Chromaprint 音频指纹识别：当本地标签、国内源和海外源都未命中时，可按实际音频内容识别歌曲。密钥仅加密保存，不会在接口中返回。</n-text>
                  <n-text depth="3">
                    申请与说明：
                    <n-a href="https://acoustid.org" target="_blank">acoustid.org</n-a>
                    ；运行环境还需安装 <code>fpcalc</code>（chromaprint）。
                  </n-text>
                </n-space>
              </n-form-item>
              <n-form-item>
                <n-button type="primary" class="save-btn" :loading="saving" @click="saveGeneral">保存设置</n-button>
              </n-form-item>
            </n-form>
          </n-card>
          <n-card title="说明">
            <n-text depth="3">本地/WebDAV 连接、扫描目录、默认上传源、冲突策略等请到「曲库」页面管理。</n-text>
          </n-card>
          <n-card title="其它">
            <n-space vertical>
              <n-text depth="3">操作日志不在底部导航中，可从这里进入。</n-text>
              <n-button secondary type="primary" class="logs-entry-btn" @click="$router.push('/logs')">查看操作日志</n-button>
            </n-space>
          </n-card>
        </template>
        <template v-else>
          <n-card title="刮削源">
            <template #header-extra>
              <n-button :loading="saving" type="primary" @click="saveScrapeSources">保存刮削源配置</n-button>
            </template>
            <n-alert type="info" :show-icon="false" style="margin-bottom: 16px">
              自动刮削按优先级依次执行：本地元数据 → 国内主源 → 海外兜底 → 音频指纹。手动刮削仅可选择已启用的来源。
            </n-alert>
            <n-data-table
              v-if="!isMobile"
              :columns="sourceColumns"
              :data="scrapeSources"
              :bordered="false"
              :single-line="false"
              size="small"
            />
            <n-space v-else vertical size="medium" class="scrape-mobile-list">
              <n-card
                v-for="row in scrapeSources"
                :key="row.id"
                size="small"
                class="scrape-card"
                :bordered="true"
              >
                <div class="scrape-card-head">
                  <div>
                    <div class="scrape-name">{{ row.name }}</div>
                    <div class="source-tier">
                      {{ row.tier === 'domestic' ? '国内主源' : row.tier === 'overseas' ? '海外兜底' : '指纹深挖' }}
                    </div>
                  </div>
                  <n-tag size="small" :type="row.enabled ? 'success' : 'default'">
                    {{ row.enabled ? '启用' : '停用' }}
                  </n-tag>
                </div>
                <n-form label-placement="left" label-width="88" size="small" class="scrape-card-form">
                  <n-form-item label="启用">
                    <n-switch v-model:value="row.enabled" />
                  </n-form-item>
                  <n-form-item label="自动刮削">
                    <n-switch v-model:value="row.auto_enabled" :disabled="!row.enabled" />
                  </n-form-item>
                  <n-form-item label="优先级">
                    <n-input
                      :value="String(row.priority)"
                      size="small"
                      @update:value="(value) => { row.priority = Number(value) || 999 }"
                    />
                  </n-form-item>
                  <n-form-item label="地区">
                    <n-select
                      v-model:value="row.region"
                      size="small"
                      :options="regionOptions"
                    />
                  </n-form-item>
                </n-form>
                <div class="source-test">
                  <span class="source-status">{{ row.status_message || (row.available === false ? '不可用' : '就绪') }}</span>
                  <n-button size="small" secondary :disabled="!row.enabled" @click="testSource(row)">测试</n-button>
                </div>
              </n-card>
            </n-space>
            <n-divider />
            <n-space vertical>
              <n-text>AcoustID / Chromaprint 状态：{{ acoustidReady ? '可用' : '不可用' }}</n-text>
              <n-text depth="3">{{ acoustidMessage }}</n-text>
            </n-space>
          </n-card>
        </template>
      </n-space>
    </n-gi>
  </n-grid>
</template>

<script setup>
import { computed, h, onMounted, reactive, ref } from 'vue'
import { NButton, NInput, NSelect, NSwitch, useMessage } from 'naive-ui'
import api from '@/api/client'
import { useIsMobile } from '@/composables/useIsMobile'

const message = useMessage()
const isMobile = useIsMobile()
const saving = ref(false)
const activeSection = ref('general')
const acoustidApiKey = ref('')
const acoustidReady = ref(false)
const acoustidMessage = ref('未检测')
const scrapeSources = ref([])
const menuOptions = [
  { label: '系统设置', key: 'general' },
  { label: '刮削源', key: 'scrape' },
]
const regionOptions = [
  { label: '中国大陆', value: 'cn' },
  { label: '香港', value: 'hk' },
  { label: '台湾', value: 'tw' },
  { label: '全球', value: 'global' },
]
const form = reactive({
  storage_path: '',
  prefer_format: 'any',
  mp3_output_path: '',
  lossless_output_path: '',
  lossless_preferred: false,
  auto_convert_when_lossless_not_preferred: false,
  auto_upload_webdav: false,
})

// 与后端 resolve_output_dir 规则保持一致：留空→存储目录/<默认名>；单段（含 /MP3 写法）→基于存储目录；多段绝对路径→原样
const resolveDir = (raw, defaultName) => {
  const storage = (form.storage_path || '').trim().replace(/\/+$/, '')
  const value = (raw || '').trim()
  const join = (rel) => (storage ? `${storage}/${rel}` : `<本地存储路径>/${rel}`)
  if (!value) return join(defaultName)
  if (value.startsWith('/') && value.slice(1).includes('/')) return value
  return join(value.replace(/^\/+/, ''))
}
const resolvedMp3Path = computed(() => resolveDir(form.mp3_output_path, 'MP3'))
const resolvedLosslessPath = computed(() => resolveDir(form.lossless_output_path, 'LOSSLESS'))

const sourceColumns = [
  {
    title: '来源',
    key: 'name',
    minWidth: 180,
    render: (row) => h('div', [
      h('strong', row.name),
      h('div', { class: 'source-tier' }, row.tier === 'domestic' ? '国内主源' : row.tier === 'overseas' ? '海外兜底' : '指纹深挖'),
    ]),
  },
  {
    title: '启用',
    key: 'enabled',
    width: 80,
    render: (row) => h(NSwitch, { value: row.enabled, 'onUpdate:value': (value) => { row.enabled = value } }),
  },
  {
    title: '自动刮削',
    key: 'auto_enabled',
    width: 100,
    render: (row) => h(NSwitch, {
      value: row.auto_enabled,
      disabled: !row.enabled,
      'onUpdate:value': (value) => { row.auto_enabled = value },
    }),
  },
  {
    title: '优先级',
    key: 'priority',
    width: 110,
    render: (row) => h(NInput, {
      value: String(row.priority),
      size: 'small',
      onUpdateValue: (value) => { row.priority = Number(value) || 999 },
    }),
  },
  {
    title: '地区',
    key: 'region',
    width: 120,
    render: (row) => h(NSelect, {
      value: row.region,
      size: 'small',
      options: regionOptions,
      'onUpdate:value': (value) => { row.region = value },
    }),
  },
  {
    title: '状态 / 测试',
    key: 'test',
    minWidth: 210,
    render: (row) => h('div', { class: 'source-test' }, [
      h('span', row.status_message || (row.available === false ? '不可用' : '就绪')),
      h(NButton, {
        size: 'tiny',
        secondary: true,
        disabled: !row.enabled,
        onClick: () => testSource(row),
      }, { default: () => '测试' }),
    ]),
  },
]

async function load() {
  try {
    const { data: d } = await api.get('/settings')
    Object.assign(form, {
      storage_path: d.storage_path || '',
      prefer_format: d.prefer_format || 'any',
      mp3_output_path: d.mp3_output_path || '',
      lossless_output_path: d.lossless_output_path || '',
      lossless_preferred: !!d.lossless_preferred,
      auto_convert_when_lossless_not_preferred: !!d.auto_convert_when_lossless_not_preferred,
      auto_upload_webdav: !!d.auto_upload_webdav,
    })
    scrapeSources.value = d.scrape_sources || []
    acoustidReady.value = !!d.acoustid_ready
    acoustidMessage.value = d.acoustid_message || '未检测'
  } catch (err) {
    message.error(err.response?.data?.detail || '加载设置失败')
  }
}

async function saveGeneral() {
  await save({
    storage_path: form.storage_path,
    prefer_format: form.prefer_format,
    mp3_output_path: form.mp3_output_path.trim() || undefined,
    lossless_output_path: form.lossless_output_path.trim() || undefined,
    lossless_preferred: form.lossless_preferred,
    auto_convert_when_lossless_not_preferred: form.auto_convert_when_lossless_not_preferred,
    auto_upload_webdav: form.auto_upload_webdav,
    acoustid_api_key: acoustidApiKey.value || undefined,
  }, '设置已保存')
  acoustidApiKey.value = ''
}

async function saveScrapeSources() {
  await save({ scrape_sources: scrapeSources.value }, '刮削源配置已保存')
}

async function save(payload, success) {
  saving.value = true
  try {
    const { data } = await api.put('/settings', payload)
    scrapeSources.value = data.scrape_sources || scrapeSources.value
    acoustidReady.value = !!data.acoustid_ready
    acoustidMessage.value = data.acoustid_message || acoustidMessage.value
    message.success(success)
  } catch (err) {
    message.error(err.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function testSource(row) {
  try {
    const { data } = await api.post(`/settings/scrape-sources/${row.id}/test`)
    row.status_message = data.message || (data.ok ? '连接正常' : '测试失败')
    message[data.ok ? 'success' : 'warning'](`${row.name}：${row.status_message}`)
  } catch (err) {
    row.status_message = err.response?.data?.detail || '测试失败'
    message.error(`${row.name}：${row.status_message}`)
  }
}

onMounted(load)
</script>

<style scoped>
.settings-nav {
  position: sticky;
  top: 16px;
  background: color-mix(in srgb, var(--card-color) 92%, var(--primary-color) 8%);
}
.source-tier {
  margin-top: 3px;
  color: var(--text-color-3);
  font-size: 12px;
}
.source-test {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
}
.path-line code {
  word-break: break-all;
}
.switch-row {
  width: 100%;
}
.format-item {
  overflow: hidden;
}
.format-item :deep(.n-form-item-blank) {
  min-width: 0;
  width: 100%;
  max-width: 100%;
}
/* n-radio-group 根节点就是 .format-group；子节点是 button + splitor 交替 */
.format-group {
  display: inline-flex !important;
  flex-wrap: nowrap;
  align-items: stretch;
  max-width: 100%;
  width: auto;
}
.format-group :deep(.n-radio-button) {
  flex: 0 0 auto;
  white-space: nowrap;
}
.format-group :deep(.n-radio-group__splitor) {
  flex: 0 0 auto;
}
.scrape-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}
.scrape-name {
  font-weight: 600;
  line-height: 1.35;
}
.scrape-card-form :deep(.n-form-item) {
  margin-bottom: 10px;
}
.source-status {
  min-width: 0;
  flex: 1;
  font-size: 13px;
  color: var(--text-color-3);
  word-break: break-word;
}
@media (max-width: 768px) {
  .settings-nav {
    position: static;
    padding: 0;
    background: transparent;
  }
  .settings-mobile-tabs :deep(.n-tabs-nav) {
    padding: 3px;
    border: 1px solid var(--border-color);
    border-radius: 10px;
    background: color-mix(in srgb, var(--body-color) 78%, var(--primary-color) 5%);
  }
  .settings-mobile-tabs :deep(.n-tabs-tab) {
    flex: 1;
    justify-content: center;
  }
  .settings-form :deep(.n-form-item-label) {
    padding-bottom: 4px;
  }
  .settings-form :deep(.n-button) {
    width: 100%;
  }
  /* 覆盖 settings-form 里 n-button width:100% —— radio-button 内部也是 button */
  .settings-form .format-group :deep(.n-radio-button),
  .settings-form .format-group :deep(.n-button),
  .settings-form .format-group :deep(button) {
    width: auto !important;
    min-width: 0 !important;
    max-width: none !important;
    flex: 1 1 0 !important;
  }
  .format-group {
    display: flex !important;
    flex-wrap: nowrap !important;
    width: 100% !important;
    max-width: 100% !important;
  }
  .format-group :deep(.n-radio-button) {
    padding: 0 4px !important;
    justify-content: center;
    text-align: center;
  }
  .format-group :deep(.n-radio-button__content) {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .format-group :deep(.n-radio-group__splitor) {
    flex: 0 0 1px !important;
    width: 1px !important;
    min-width: 1px !important;
    max-width: 1px !important;
  }
  .scrape-card {
    border-radius: 12px;
  }
  .scrape-mobile-list {
    width: 100%;
  }
  .logs-entry-btn {
    width: 100%;
  }
}
</style>
