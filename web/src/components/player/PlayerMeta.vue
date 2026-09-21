<template>
  <div class="pmeta">
    <template v-if="showCover">
      <img v-if="player.cover && !coverBroken" class="mini" :src="player.cover" alt="cover" @error="coverBroken = true" @load="coverBroken = false" />
      <div v-else class="mini placeholder"><n-icon :size="18"><musical-notes /></n-icon></div>
    </template>
    <div class="tx">
      <div class="tt" :title="player.current?.title || '未在播放'">{{ player.current?.title || '未在播放' }}</div>
      <div class="ss" :title="subLine">{{ subLine }}</div>
    </div>
    <div class="acts">
      <n-tooltip>
        <template #trigger>
          <n-button
            quaternary circle size="small" class="act fav"
            :class="{ on: player.current?.is_favorite }"
            :type="player.current?.is_favorite ? 'error' : 'default'"
            :disabled="!player.current"
            aria-label="喜欢"
            @click="toggleFavorite"
          >
            <n-icon :size="19"><heart v-if="player.current?.is_favorite" /><heart-outline v-else /></n-icon>
          </n-button>
        </template>
        {{ player.current?.is_favorite ? '取消喜欢' : '加入我喜欢的' }}
      </n-tooltip>
      <n-popover
        trigger="click"
        placement="top"
        :show-arrow="false"
        :padding="0"
        :disabled="!player.current"
        v-model:show="pickerOpen"
        style="border-radius: var(--sp-radius-lg)"
      >
        <template #trigger>
          <n-button
            quaternary circle size="small" class="act"
            :class="{ on: pickerOpen }"
            :disabled="!player.current"
            aria-label="加入歌单"
          >
            <n-icon :size="19"><add-circle-outline /></n-icon>
          </n-button>
        </template>
        <playlist-picker
          v-if="player.current && pickerOpen"
          :song-ids="[player.current.id]"
          @done="pickerOpen = false"
        />
      </n-popover>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { NButton, NIcon, NPopover, NTooltip, useMessage } from 'naive-ui'
import { AddCircleOutline, Heart, HeartOutline, MusicalNotes } from '@vicons/ionicons5'
import { addFavorite, removeFavorite } from '@/api/music'
import { usePlayerStore } from '@/stores/player'
import PlaylistPicker from '@/components/PlaylistPicker.vue'

// 正在播放的元信息条：迷你封面 + 标题 + 歌手·专辑 + 喜欢 + 加入歌单。
// showCover=false 时不渲染迷你封面——叠层卡的大封面就在上方，小封面会重复。
defineProps({
  showCover: { type: Boolean, default: true },
})
const player = usePlayerStore()
const message = useMessage()
const coverBroken = ref(false)
const pickerOpen = ref(false)

const subLine = computed(() => {
  const s = player.current
  if (!s) return '选择一首歌曲开始'
  return [s.artist, s.album].filter(Boolean).join(' · ') || '选择一首歌曲开始'
})

watch(
  () => player.cover,
  () => { coverBroken.value = false },
)

async function toggleFavorite() {
  const song = player.current
  if (!song) return
  try {
    if (song.is_favorite) {
      await removeFavorite(song.id)
      song.is_favorite = false
      message.success('已取消喜欢')
    } else {
      await addFavorite(song.id)
      song.is_favorite = true
      message.success('已加入我喜欢的')
    }
  } catch (e) {
    message.error(e.response?.data?.detail || '操作失败')
  }
}
</script>

<style scoped>
.pmeta {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.mini {
  width: 46px;
  height: 46px;
  border-radius: var(--sp-radius-sm);
  object-fit: cover;
  flex: none;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(255, 255, 255, 0.08);
}
.player-panel.light .mini {
  box-shadow: 0 6px 16px rgba(20, 30, 50, 0.16), 0 0 0 1px rgba(18, 22, 30, 0.06);
}
.mini.placeholder {
  display: grid;
  place-items: center;
  background: var(--cover-bg, #2a2a2a);
  color: var(--fg-3);
}
.player-panel.light .mini.placeholder {
  background: var(--cover-bg, #eef1f6);
}
.tx {
  flex: 1;
  min-width: 0;
}
.tt {
  font-size: var(--sp-fs-h3);
  font-weight: 600;
  letter-spacing: 0.01em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--fg);
}
.ss {
  margin-top: 2px;
  font-size: var(--sp-fs-caption);
  color: var(--fg-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.acts {
  display: flex;
  align-items: center;
  gap: 2px;
  flex: none;
}
.act {
  color: var(--fg-2);
}
.act.on {
  color: var(--accent, var(--sp-ui-primary));
}
.fav.on {
  color: var(--sp-ui-error);
}
</style>
