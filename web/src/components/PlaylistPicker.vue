<template>
  <div class="plp">
    <div class="plp-head">
      <span class="plp-title">加入歌单</span>
      <span v-if="single && addedCount" class="plp-cnt">已加入 {{ addedCount }} 个</span>
    </div>

    <div v-if="needSearch" class="plp-search">
      <n-icon :size="14"><search-outline /></n-icon>
      <input
        v-model="keyword"
        class="plp-search-input"
        type="text"
        placeholder="搜索歌单…"
        @keydown.esc.stop="keyword = ''"
      />
    </div>

    <div class="plp-list" :class="{ loading }">
      <template v-if="filtered.length">
        <div
          v-for="p in filtered"
          :key="p.id"
          class="plp-row"
          :class="{ on: single && p.contains_song }"
          role="button"
          tabindex="0"
          @click="toggle(p)"
          @keydown.enter="toggle(p)"
        >
          <span class="plp-tick" :class="{ on: single && p.contains_song }">
            <n-icon v-if="single && p.contains_song" :size="11"><checkmark /></n-icon>
          </span>
          <span class="plp-nm" :title="p.name">{{ p.name }}</span>
          <span class="plp-ct">{{ p.song_count }} 首</span>
        </div>
      </template>
      <div v-else class="plp-empty">{{ loading ? '加载中…' : keyword ? '没有匹配的歌单' : '还没有歌单' }}</div>
    </div>

    <div v-if="!creating" class="plp-new" role="button" tabindex="0" @click="startCreate" @keydown.enter="startCreate">
      <n-icon :size="14"><add-outline /></n-icon>新建歌单
    </div>
    <div v-else class="plp-create">
      <input
        ref="newInput"
        v-model="newName"
        class="plp-create-input"
        type="text"
        placeholder="歌单名称"
        @keydown.enter="createAndAdd"
        @keydown.esc.stop="creating = false"
      />
      <button class="plp-create-btn" :disabled="!newName.trim() || creatingLoading" @click="createAndAdd">
        {{ creatingLoading ? '创建中…' : '创建并加入' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref } from 'vue'
import { NIcon, useMessage } from 'naive-ui'
import { AddOutline, Checkmark, SearchOutline } from '@vicons/ionicons5'
import {
  addSongsToPlaylist,
  createPlaylist,
  fetchPlaylists,
  removeSongFromPlaylist,
} from '@/api/music'

// 「加入歌单」共享弹层内容：播放器（当前播放的歌）与曲库右键菜单（单行）共用。
// 宿主：播放器里用 n-popover 锚定 ＋ 按钮；曲库里用 n-modal 承载。本组件只做面板内容。
const props = defineProps({
  // 要加入的歌曲 id 列表；单曲时弹层显示「已加入」勾选态，多选时只做批量加入
  songIds: { type: Array, default: () => [] },
})
const emit = defineEmits(['changed', 'done'])
const message = useMessage()

const loading = ref(false)
const playlists = ref([])
const keyword = ref('')
const creating = ref(false)
const creatingLoading = ref(false)
const newName = ref('')
const newInput = ref(null)

const single = computed(() => props.songIds.length === 1)
const needSearch = computed(() => playlists.value.length > 6)
const filtered = computed(() => {
  const k = keyword.value.trim().toLowerCase()
  if (!k) return playlists.value
  return playlists.value.filter((p) => (p.name || '').toLowerCase().includes(k))
})
const addedCount = computed(() => playlists.value.filter((p) => p.contains_song).length)

async function load() {
  loading.value = true
  try {
    const { data } = await fetchPlaylists(single.value ? props.songIds[0] : undefined)
    playlists.value = data || []
  } catch (e) {
    message.error(e.response?.data?.detail || '加载歌单失败')
  } finally {
    loading.value = false
  }
}

async function toggle(p) {
  if (!props.songIds.length) return
  // 单曲 + 已在歌单 → 点掉 = 移出；否则 = 加入
  const remove = single.value && p.contains_song
  try {
    if (remove) {
      await removeSongFromPlaylist(p.id, props.songIds[0])
      p.contains_song = false
      p.song_count = Math.max(0, (p.song_count || 1) - 1)
      message.success(`已从「${p.name}」移出`)
    } else {
      await addSongsToPlaylist(p.id, props.songIds)
      if (single.value) p.contains_song = true
      p.song_count = (p.song_count || 0) + (single.value ? 1 : props.songIds.length)
      message.success(`已加入「${p.name}」`)
      if (!single.value) emit('done')
    }
    emit('changed')
  } catch (e) {
    message.error(e.response?.data?.detail || '操作失败')
  }
}

async function startCreate() {
  creating.value = true
  await nextTick()
  newInput.value?.focus()
}

async function createAndAdd() {
  const name = newName.value.trim()
  if (!name || creatingLoading.value) return
  creatingLoading.value = true
  try {
    const { data: pl } = await createPlaylist({ name })
    if (props.songIds.length) await addSongsToPlaylist(pl.id, props.songIds)
    message.success(`已创建「${name}」并加入`)
    creating.value = false
    newName.value = ''
    await load()
    emit('changed')
  } catch (e) {
    message.error(e.response?.data?.detail || '创建失败')
  } finally {
    creatingLoading.value = false
  }
}

load()
</script>

<style scoped>
/* 本组件经 popover/modal teleport 到 body：颜色一律用 :root 上的 --sp-ui-*（组件局部变量不可达） */
.plp {
  width: 274px;
  font-size: var(--sp-fs-small);
  color: var(--sp-ui-text-1);
}
.plp-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 11px 12px 7px;
  font-size: var(--sp-fs-caption);
  color: var(--sp-ui-text-3);
}
.plp-title {
  font-weight: 500;
  color: var(--sp-ui-text-1);
}
.plp-cnt {
  color: var(--sp-ui-primary);
}
.plp-search {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 0 10px 8px;
  height: 30px;
  padding: 0 9px;
  border-radius: var(--sp-radius-sm);
  background: var(--sp-ui-hover);
  color: var(--sp-ui-text-3);
}
.plp-search-input {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  background: transparent;
  color: var(--sp-ui-text-1);
  font-size: var(--sp-fs-caption);
}
.plp-search-input::placeholder {
  color: var(--sp-ui-text-3);
}
.plp-list {
  max-height: 260px;
  overflow-y: auto;
}
.plp-list.loading {
  opacity: 0.6;
}
.plp-row {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  cursor: pointer;
  border-radius: var(--sp-radius-sm);
}
.plp-row:hover {
  background: var(--sp-ui-hover);
}
.plp-tick {
  width: 16px;
  height: 16px;
  border-radius: var(--sp-radius-circle);
  border: 1.5px solid var(--sp-ui-border);
  display: grid;
  place-items: center;
  color: var(--sp-ui-on-primary);
  transition: background 0.15s ease, border-color 0.15s ease;
}
.plp-tick.on {
  background: var(--sp-ui-primary);
  border-color: var(--sp-ui-primary);
}
.plp-nm {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.plp-row.on .plp-nm {
  color: var(--sp-ui-text-1);
  font-weight: 500;
}
.plp-ct {
  font-size: var(--sp-fs-micro);
  color: var(--sp-ui-text-3);
  font-variant-numeric: tabular-nums;
}
.plp-row.on .plp-ct {
  color: var(--sp-ui-primary);
}
.plp-empty {
  padding: 22px 0;
  text-align: center;
  color: var(--sp-ui-text-3);
  font-size: var(--sp-fs-caption);
}
.plp-new {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 9px 12px;
  border-top: 1px solid var(--sp-ui-border);
  color: var(--sp-ui-primary);
  font-size: var(--sp-fs-caption);
  cursor: pointer;
}
.plp-new:hover {
  background: var(--sp-ui-hover);
}
.plp-create {
  display: flex;
  gap: 6px;
  padding: 8px 10px;
  border-top: 1px solid var(--sp-ui-border);
}
.plp-create-input {
  flex: 1;
  min-width: 0;
  height: 30px;
  padding: 0 9px;
  border-radius: var(--sp-radius-sm);
  border: 1px solid var(--sp-ui-border);
  background: transparent;
  color: var(--sp-ui-text-1);
  font-size: var(--sp-fs-caption);
  outline: none;
}
.plp-create-input:focus {
  border-color: var(--sp-ui-primary);
}
.plp-create-btn {
  flex: none;
  height: 30px;
  padding: 0 11px;
  border: none;
  border-radius: var(--sp-radius-sm);
  background: var(--sp-ui-primary);
  color: var(--sp-ui-on-primary);
  font-size: var(--sp-fs-caption);
  font-weight: 500;
  cursor: pointer;
}
.plp-create-btn:disabled {
  opacity: 0.5;
  cursor: default;
}
</style>
