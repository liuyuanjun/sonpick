<template>
  <div class="song-table">
    <div class="toolbar">
      <n-space>
        <n-button type="primary" :disabled="!songs.length" @click="playAll">
          <template #icon><n-icon><play /></n-icon></template>
          播放全部
        </n-button>
        <n-button quaternary :disabled="!songs.length" @click="enqueueAll">加入队列</n-button>
      </n-space>
      <n-input
        v-if="showSearch"
        v-model:value="keyword"
        clearable
        placeholder="筛选歌曲"
        class="search-input"
      />
    </div>

    <div v-if="filtered.length" class="song-list" role="list">
      <div class="song-list-head">
        <span class="col-idx">#</span>
        <span class="col-main">歌曲 / 专辑</span>
        <span class="col-time">时长</span>
        <span class="col-actions"></span>
      </div>
      <div
        v-for="(row, i) in filtered"
        :key="row.id"
        class="song-row"
        role="listitem"
        @dblclick="playAt(row)"
      >
        <span class="col-idx">{{ i + 1 }}</span>
        <div class="col-main song-cell">
          <div class="mini-cover-wrap">
            <img
              v-if="row.cover_path"
              class="mini-cover"
              :src="coverUrl(row.id, auth.token)"
              alt=""
              loading="lazy"
              @error="onCoverError($event)"
            />
            <div v-else class="mini-cover placeholder">
              <n-icon :size="16"><musical-notes /></n-icon>
            </div>
          </div>
          <div class="song-meta">
            <div class="song-title" :title="row.title || '未知歌曲'">{{ row.title || '未知歌曲' }}</div>
            <div class="song-sub" :title="subLine(row)">
              <span>{{ row.artist || '未知艺术家' }}</span>
              <template v-if="row.album">
                <span class="dot">·</span>
                <span>{{ row.album }}</span>
              </template>
            </div>
          </div>
        </div>
        <span class="col-time">{{ formatTime(row.duration || 0) }}</span>
        <div class="col-actions">
          <n-button quaternary circle size="tiny" @click.stop="playAt(row)">
            <n-icon :size="16"><play /></n-icon>
          </n-button>
          <n-button
            quaternary
            circle
            size="tiny"
            :type="row.is_favorite ? 'error' : 'default'"
            @click.stop="toggleFav(row)"
          >
            <n-icon :size="16">
              <heart v-if="row.is_favorite" />
              <heart-outline v-else />
            </n-icon>
          </n-button>
          <n-button
            quaternary
            circle
            size="tiny"
            @click.stop="onAddOrRemove(row)"
          >
            <n-icon :size="16"><add /></n-icon>
          </n-button>
        </div>
      </div>
    </div>
    <n-empty v-else description="暂无歌曲" style="padding: 36px 0" />
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useMessage } from 'naive-ui'
import {
  Play,
  Heart,
  HeartOutline,
  Add,
  MusicalNotes,
} from '@vicons/ionicons5'
import { usePlayerStore } from '@/stores/player'
import { addFavorite, removeFavorite, coverUrl } from '@/api/music'
import { useAuthStore } from '@/stores/auth'
import { formatTime } from '@/utils/lrc'

const props = defineProps({
  songs: { type: Array, default: () => [] },
  showSearch: { type: Boolean, default: true },
  playlistId: { type: Number, default: null },
})

const emit = defineEmits(['changed', 'add-to-playlist', 'remove-from-playlist'])

const player = usePlayerStore()
const auth = useAuthStore()
const message = useMessage()
const keyword = ref('')

const filtered = computed(() => {
  const k = keyword.value.trim().toLowerCase()
  if (!k) return props.songs
  return props.songs.filter((s) => {
    const blob = `${s.title || ''} ${s.artist || ''} ${s.album || ''}`.toLowerCase()
    return blob.includes(k)
  })
})

function subLine(row) {
  return [row.artist, row.album].filter(Boolean).join(' · ')
}

function playAt(row) {
  const list = filtered.value
  const idx = list.findIndex((s) => s.id === row.id)
  player.playList(list, idx >= 0 ? idx : 0)
}

function playAll() {
  if (!filtered.value.length) return
  player.playList(filtered.value, 0)
}

function enqueueAll() {
  player.enqueue(filtered.value)
  message.success('已加入播放队列')
}

async function toggleFav(row) {
  try {
    if (row.is_favorite) {
      await removeFavorite(row.id)
      row.is_favorite = false
      message.success('已取消喜欢')
    } else {
      await addFavorite(row.id)
      row.is_favorite = true
      message.success('已加入我喜欢的')
    }
    emit('changed')
  } catch (e) {
    message.error(e.response?.data?.detail || '操作失败')
  }
}

function onAddOrRemove(row) {
  if (props.playlistId) emit('remove-from-playlist', row)
  else emit('add-to-playlist', row)
}

function onCoverError(e) {
  const img = e?.target
  if (img) {
    img.style.display = 'none'
    const wrap = img.parentElement
    if (wrap && !wrap.querySelector('.placeholder')) {
      const ph = document.createElement('div')
      ph.className = 'mini-cover placeholder'
      ph.innerHTML = '♪'
      wrap.appendChild(ph)
    }
  }
}
</script>

<style scoped>
.song-table {
  padding-bottom: 8px;
  min-width: 0;
  max-width: 100%;
}
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  gap: 12px;
  flex-wrap: wrap;
}
.search-input {
  width: min(220px, 100%);
}

.song-list {
  width: 100%;
  min-width: 0;
  border-top: 1px solid rgba(127, 127, 127, 0.12);
}
.song-list-head,
.song-row {
  display: grid;
  /* 序号 | 主信息(限宽) | 时长 | 操作 */
  grid-template-columns: 52px minmax(0, 1fr) 56px 108px;
  gap: 8px;
  align-items: center;
  min-width: 0;
}
.song-list-head {
  padding: 8px 6px;
  font-size: 12px;
  color: var(--n-text-color-3);
}
.song-row {
  padding: 8px 6px;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.12s ease;
}
.song-row:hover {
  background: rgba(24, 160, 88, 0.07);
}

.col-idx {
  text-align: center;
  font-variant-numeric: tabular-nums;
  font-size: 12px;
  color: var(--n-text-color-3);
  white-space: nowrap;
  line-height: 1;
}
.col-time {
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-size: 12px;
  color: var(--n-text-color-3);
  white-space: nowrap;
}
.col-actions {
  display: inline-flex;
  justify-content: flex-end;
  align-items: center;
  gap: 2px;
  opacity: 0.7;
  white-space: nowrap;
}
.song-row:hover .col-actions {
  opacity: 1;
}

.song-cell {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
}

/* 强制封面缩略图，不受原图像素尺寸影响 */
.mini-cover-wrap {
  width: 40px;
  height: 40px;
  min-width: 40px;
  min-height: 40px;
  max-width: 40px;
  max-height: 40px;
  flex: 0 0 40px;
  border-radius: 8px;
  overflow: hidden;
  background: rgba(127, 127, 127, 0.12);
  position: relative;
}
.mini-cover {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  max-width: 100%;
  max-height: 100%;
  object-fit: cover;
  object-position: center;
  display: block;
  border: 0;
}
.mini-cover.placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--n-text-color-3);
  font-size: 14px;
}

.song-meta {
  min-width: 0;
  flex: 1 1 auto;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.song-title {
  font-weight: 600;
  font-size: 13px;
  line-height: 1.35;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--n-text-color);
}
.song-sub {
  font-size: 12px;
  line-height: 1.3;
  color: var(--n-text-color-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.dot {
  margin: 0 4px;
  opacity: 0.55;
}
</style>
