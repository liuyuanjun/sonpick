<template>
  <transition name="slide-up">
    <div v-if="player.showPlayer" class="global-player">
      <audio
        ref="audio"
        :src="player.src"
        @timeupdate="onTimeUpdate"
        @loadedmetadata="onLoaded"
        @ended="onEnded"
        @play="onPlay"
        @pause="player.playing = false"
        @error="onAudioError"
      />

      <div class="gp-left" @click="goPlayer">
        <img
          v-if="player.cover && !coverBroken"
          :src="player.cover"
          class="cover"
          alt="cover"
          @error="coverBroken = true"
        />
        <div v-else class="cover placeholder">
          <n-icon size="22"><musical-notes /></n-icon>
        </div>
        <div class="meta">
          <div class="title">{{ player.current?.title || '未知歌曲' }}</div>
          <div class="artist">{{ player.current?.artist || player.current?.album || '' }}</div>
        </div>
      </div>

      <div class="gp-center">
        <div class="controls">
          <n-tooltip>
            <template #trigger>
              <n-button quaternary circle size="small" :type="player.losslessPreferred ? 'primary' : 'default'" @click="player.toggleLosslessPreferred()">{{ player.losslessPreferred ? 'FLAC' : 'MP3' }}</n-button>
            </template>
            {{ player.losslessPreferred ? '无损优先：优先 FLAC' : 'MP3 优先：缺失时自动回退' }}
          </n-tooltip>
          <n-tooltip>
            <template #trigger>
              <n-button quaternary circle size="small" @click="player.toggleMode()">
                <n-icon size="18">
                  <shuffle v-if="player.mode === 'shuffle'" />
                  <repeat v-else-if="player.mode === 'loop'" />
                  <reload v-else-if="player.mode === 'single'" />
                  <list-outline v-else />
                </n-icon>
              </n-button>
            </template>
            {{ player.modeLabel }}
          </n-tooltip>
          <n-button quaternary circle @click="player.prev()">
            <n-icon size="20"><play-skip-back /></n-icon>
          </n-button>
          <n-button type="primary" circle @click="togglePlay">
            <n-icon size="22">
              <pause v-if="player.playing" />
              <play v-else />
            </n-icon>
          </n-button>
          <n-button quaternary circle @click="player.next()">
            <n-icon size="20"><play-skip-forward /></n-icon>
          </n-button>
          <n-button quaternary circle @click="player.showQueue = !player.showQueue">
            <n-icon size="18"><list /></n-icon>
          </n-button>
        </div>
        <div class="progress-row">
          <span>{{ formatTime(player.currentTime) }}</span>
          <n-slider :value="progress" :step="0.1" :tooltip="false" @update:value="seek" />
          <span>{{ formatTime(player.duration) }}</span>
        </div>
      </div>

      <div class="gp-right">
        <n-button quaternary circle size="small" @click="player.toggleMute()">
          <n-icon size="18">
            <volume-mute v-if="player.muted || player.volume === 0" />
            <volume-medium v-else />
          </n-icon>
        </n-button>
        <n-slider
          :value="player.volume * 100"
          :step="1"
          style="width: 100px"
          :tooltip="false"
          @update:value="(v) => player.setVolume(v / 100)"
        />
        <n-button quaternary circle @click="goPlayer">
          <n-icon size="18"><expand /></n-icon>
        </n-button>
        <n-button quaternary circle @click="player.close()">
          <n-icon size="18"><close /></n-icon>
        </n-button>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  Play, Pause, Close, MusicalNotes, PlaySkipBack, PlaySkipForward,
  Shuffle, Repeat, Reload, List, ListOutline, VolumeMedium, VolumeMute, Expand,
} from '@vicons/ionicons5'
import { NSlider, useMessage } from 'naive-ui'
import { usePlayerStore } from '@/stores/player'
import { formatTime } from '@/utils/lrc'

const player = usePlayerStore()
const message = useMessage()
const router = useRouter()
const audio = ref(null)
const coverBroken = ref(false)

const progress = computed(() => {
  if (!player.duration) return 0
  return (player.currentTime / player.duration) * 100
})

watch(() => player.cover, () => {
  coverBroken.value = false
})

watch(() => player.src, () => {
  requestAnimationFrame(() => {
    if (!audio.value) return
    audio.value.load()
    if (player.playing) audio.value.play().catch(() => {})
  })
})

watch(() => player.playing, (val) => {
  if (!audio.value) return
  if (val) audio.value.play().catch(() => {})
  else audio.value.pause()
})

watch(() => player.volume, (v) => {
  if (audio.value) audio.value.volume = player.muted ? 0 : v
})

watch(() => player.muted, (m) => {
  if (audio.value) audio.value.volume = m ? 0 : player.volume
})

function togglePlay() {
  player.togglePlay()
}

function onTimeUpdate(e) {
  player.setProgress(e.target.currentTime || 0, e.target.duration || player.duration || 0)
}

function onLoaded(e) {
  player.setProgress(player.currentTime || 0, e.target.duration || player.duration || 0)
  if (audio.value) audio.value.volume = player.muted ? 0 : player.volume
}

function onEnded() {
  player.next()
}

// 连续播放失败计数：成功播放时清零；整列轮过一遍仍失败则停止，避免死循环
let consecErrors = 0

function onPlay() {
  player.playing = true
  consecErrors = 0
}

function onAudioError() {
  if (!player.src || !player.current) return
  consecErrors += 1
  if (consecErrors > (player.queue?.length || 0)) {
    player.playing = false
    message.error('播放列表中的歌曲暂时都无法播放')
    return
  }
  message.warning(`「${player.current.title || '歌曲'}」播放失败，自动播放下一首`)
  player.next()
}

function seek(val) {
  if (!audio.value || !player.duration) return
  const t = (val / 100) * player.duration
  audio.value.currentTime = t
  player.setProgress(t, player.duration)
}

function onExternalSeek(e) {
  const t = Number(e.detail || 0)
  if (!audio.value || Number.isNaN(t)) return
  audio.value.currentTime = t
  player.setProgress(t, audio.value.duration || player.duration || 0)
  if (!player.playing) player.playing = true
}

function goPlayer() {
  router.push({ name: 'Player' })
}

onMounted(() => window.addEventListener('sonpick-seek', onExternalSeek))
onUnmounted(() => window.removeEventListener('sonpick-seek', onExternalSeek))
</script>

<style scoped>
.global-player {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: 84px;
  z-index: 1000;
  display: grid;
  grid-template-columns: minmax(180px, 280px) minmax(0, 1fr) minmax(180px, 260px);
  align-items: center;
  gap: 12px;
  padding: 0 16px;
  box-sizing: border-box;
  background: color-mix(in srgb, var(--n-card-color) 90%, transparent);
  border-top: 1px solid var(--n-border-color);
  backdrop-filter: blur(14px);
  box-shadow: 0 -8px 28px rgba(0, 0, 0, 0.06);
}
.gp-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  cursor: pointer;
}
.cover {
  width: 52px;
  height: 52px;
  border-radius: 10px;
  object-fit: cover;
  flex-shrink: 0;
  background: rgba(127, 127, 127, 0.12);
}
.cover.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--n-text-color-3);
}
.meta {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.title {
  font-weight: 700;
  font-size: 13px;
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.artist {
  font-size: 12px;
  color: var(--n-text-color-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.gp-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  min-width: 0;
}
.controls {
  display: flex;
  align-items: center;
  gap: 6px;
}
.progress-row {
  width: min(520px, 100%);
  display: grid;
  grid-template-columns: 40px minmax(0, 1fr) 40px;
  gap: 8px;
  align-items: center;
}
.progress-row span {
  font-size: 11px;
  color: var(--n-text-color-3);
  font-variant-numeric: tabular-nums;
  text-align: center;
}
.gp-right {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  min-width: 0;
}
.slide-up-enter-active,
.slide-up-leave-active {
  transition: transform 0.2s ease, opacity 0.2s ease;
}
.slide-up-enter-from,
.slide-up-leave-to {
  transform: translateY(100%);
  opacity: 0;
}
@media (max-width: 900px) {
  .global-player {
    grid-template-columns: minmax(0, 1fr) auto;
    height: 92px;
    padding: 8px 12px;
  }
  .gp-right {
    display: none;
  }
}
</style>
