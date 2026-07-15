<template>
  <div class="queue-panel">
    <div class="queue-head">
      <div>
        <div class="queue-title">播放队列</div>
        <div class="queue-count">{{ player.queue.length }} 首</div>
      </div>
      <n-space :size="4">
        <n-button size="tiny" quaternary :disabled="!player.queue.length" @click="player.clearQueue()">
          清空
        </n-button>
        <n-button size="tiny" quaternary @click="player.showQueue = false">关闭</n-button>
      </n-space>
    </div>
    <n-empty v-if="!player.queue.length" description="队列为空" class="queue-empty" />
    <div v-else class="queue-list">
      <div
        v-for="(song, idx) in player.queue"
        :key="song.id + '-' + idx"
        class="queue-item"
        :class="{ active: idx === player.currentIndex }"
        @click="player.jumpTo(idx)"
      >
        <div class="q-idx">{{ idx + 1 }}</div>
        <div class="meta">
          <div class="q-title">{{ song.title || '未知歌曲' }}</div>
          <div class="q-artist">{{ song.artist || '未知艺术家' }}</div>
        </div>
        <n-button
          size="tiny"
          quaternary
          circle
          class="q-remove"
          @click.stop="player.removeFromQueue(idx)"
        >
          <n-icon size="14"><close /></n-icon>
        </n-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { Close } from '@vicons/ionicons5'
import { usePlayerStore } from '@/stores/player'

const player = usePlayerStore()
</script>

<style scoped>
.queue-panel {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: transparent;
  backdrop-filter: blur(12px);
  color: var(--n-text-color);
}
.queue-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  padding: 14px 14px 10px;
  border-bottom: 1px solid var(--n-border-color);
}
.queue-title {
  font-weight: 700;
  font-size: 14px;
  color: var(--n-text-color);
}
.queue-count {
  margin-top: 2px;
  font-size: 12px;
  color: var(--n-text-color-3);
}
.queue-empty {
  margin-top: 48px;
}
.queue-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 8px;
}
.queue-item {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) 28px;
  gap: 8px;
  align-items: center;
  padding: 10px 8px;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
  color: var(--n-text-color);
}
.queue-item:hover {
  background: var(--n-button-color-hover, rgba(127, 127, 127, 0.1));
}
.queue-item.active {
  background: color-mix(in srgb, var(--n-primary-color) 16%, transparent);
}
.queue-item.active .q-title {
  color: var(--n-primary-color);
}
.q-idx {
  font-size: 12px;
  color: var(--n-text-color-3);
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.queue-item.active .q-idx {
  color: var(--n-primary-color);
}
.meta {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.q-title {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--n-text-color);
}
.q-artist {
  font-size: 12px;
  color: var(--n-text-color-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.q-remove {
  opacity: 0.55;
  color: var(--n-text-color-2);
}
.queue-item:hover .q-remove {
  opacity: 1;
}
</style>
