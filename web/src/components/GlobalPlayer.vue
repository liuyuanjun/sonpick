<template>
  <teleport to="body">
    <transition name="slide-up">
    <div v-if="player.showPlayer && player.current" class="global-player" :class="{ dark: themeStore.isDark }">
      <div class="gp-progress-line" aria-hidden="true">
        <div class="fill" :style="{ width: `${progress}%` }"></div>
      </div>
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

      <div v-if="!isMobile" class="gp-center">
        <div class="controls">
          <n-tooltip>
            <template #trigger>
              <n-button
                quaternary
                circle
                size="small"
                class="format-toggle"
                :class="{ active: player.losslessPreferred }"
                :type="player.losslessPreferred ? 'primary' : 'default'"
                @click="player.toggleLosslessPreferred()"
              >
                <template #icon>
                  <n-icon :size="15">
                    <diamond-outline v-if="player.losslessPreferred" />
                    <flash-outline v-else />
                  </n-icon>
                </template>
              </n-button>
            </template>
            {{ player.losslessPreferred ? '无损优先：优先 FLAC' : '速度优先：优先 MP3，缺失时自动回退' }}
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
          <n-button quaternary circle @click="toggleQueue">
            <n-icon size="18"><list /></n-icon>
          </n-button>
          <!-- 音量：只留一个图标，hover/focus 浮出竖向滑杆 + 静音按钮。
               放在播放键右侧第三位（左：音质/模式/上一曲，右：下一曲/队列/音量，3+3 对称） -->
          <n-popover
            trigger="manual"
            :show="volumePanelOpen"
            placement="top"
            :show-arrow="false"
            :padding="0"
            :duration="0"
            :delay="0"
            style="border-radius: 12px"
          >
            <template #trigger>
              <span
                ref="volumeAnchor"
                class="gp-volume-anchor"
                @mouseenter="openVolumePanel"
                @mouseleave="scheduleCloseVolumePanel"
                @wheel.prevent="onVolumeWheel"
              >
                <n-button
                  quaternary
                  circle
                  :aria-label="volumeAriaLabel"
                  aria-haspopup="true"
                  :aria-expanded="volumePanelOpen"
                  @click="player.toggleMute()"
                  @focus="openVolumePanel"
                >
                  <n-icon size="18"><component :is="volumeIcon" /></n-icon>
                </n-button>
              </span>
            </template>

            <!-- 面板被 teleport 到 body：这里只能用 :root 上的 --sp-ui-*（--gp-* 挂在 .global-player 上取不到） -->
            <div
              ref="volumePanel"
              class="gp-volume-panel"
              @mouseenter="openVolumePanel"
              @mouseleave="scheduleCloseVolumePanel"
              @focusin="openVolumePanel"
              @focusout="onVolumeFocusOut"
              @keydown.esc.stop="closeVolumePanel"
            >
              <span class="gp-volume-value">{{ volumeText }}</span>
              <!-- Naive 竖向滑块的 height 是 100%，必须由外层容器给高度（:height prop 无效） -->
              <div class="gp-volume-slider">
                <n-slider
                  vertical
                  :value="volumePercent"
                  :step="1"
                  :tooltip="false"
                  @update:value="setVolumePercent"
                />
              </div>
              <n-button
                quaternary
                circle
                size="small"
                :aria-label="player.muted ? '取消静音' : '静音'"
                @click="player.toggleMute()"
              >
                <n-icon size="18">
                  <volume-mute v-if="volumeMuted" />
                  <volume-medium v-else />
                </n-icon>
              </n-button>
            </div>
          </n-popover>
        </div>
        <div class="progress-row">
          <span>{{ formatClock(player.currentTime) }}</span>
          <n-slider :value="progress" :step="0.1" :tooltip="false" @update:value="seek" />
          <span>{{ formatClock(player.duration) }}</span>
        </div>
      </div>

      <div v-if="isMobile" class="gp-mobile-actions">
        <n-button quaternary circle @click="togglePlay">
          <n-icon size="24">
            <pause v-if="player.playing" />
            <play v-else />
          </n-icon>
        </n-button>
        <n-button quaternary circle @click="player.next()">
          <n-icon size="22"><play-skip-forward /></n-icon>
        </n-button>
      </div>

      <div v-if="!isMobile" class="gp-right">
        <n-button quaternary circle @click="goPlayer">
          <n-icon size="18"><expand /></n-icon>
        </n-button>
        <n-button quaternary circle @click="player.close()">
          <n-icon size="18"><close /></n-icon>
        </n-button>
      </div>
    </div>
  </transition>
  </teleport>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  Play, Pause, Close, MusicalNotes, PlaySkipBack, PlaySkipForward,
  Shuffle, Repeat, Reload, List, ListOutline, VolumeHigh, VolumeLow, VolumeMedium, VolumeMute,
  Expand, DiamondOutline, FlashOutline,
} from '@vicons/ionicons5'
import { NPopover, NSlider, useMessage } from 'naive-ui'
import { usePlayerStore } from '@/stores/player'
import { useThemeStore } from '@/stores/theme'
import { useIsMobile } from '@/composables/useIsMobile'
import { useMediaSession } from '@/composables/useMediaSession'
import { formatClock } from '@/utils/format'

const player = usePlayerStore()
const themeStore = useThemeStore()
const message = useMessage()
const isMobile = useIsMobile()
const audio = ref(null)
const coverBroken = ref(false)
// 系统媒体命令（线控/媒体键）对接：单击=播放/暂停、双击=下一曲、三击=上一曲
const mediaSession = useMediaSession(player, audio)
// 本地进度百分比：直接跟 audio 同步，避免仅依赖 store 时顶部细线不刷新
const progressPct = ref(0)

const progress = computed(() => {
  const local = Number(progressPct.value) || 0
  if (local > 0) return local
  const total = Number(player.duration) || 0
  const cur = Number(player.currentTime) || 0
  if (!(total > 0) || !Number.isFinite(total)) return 0
  return Math.min(100, Math.max(0, (cur / total) * 100))
})

function syncProgressFromAudio(el = audio.value) {
  if (!el) {
    progressPct.value = 0
    return
  }
  const total = Number(el.duration)
  const cur = Number(el.currentTime) || 0
  if (!Number.isFinite(total) || total <= 0) {
    // 流式/未知时长时用 store 兜底
    const st = Number(player.duration) || 0
    const sc = Number(player.currentTime) || 0
    progressPct.value = st > 0 ? Math.min(100, Math.max(0, (sc / st) * 100)) : 0
    return
  }
  progressPct.value = Math.min(100, Math.max(0, (cur / total) * 100))
  player.setProgress(cur, total)
  mediaSession.updatePositionState()
}

watch(() => player.cover, () => {
  coverBroken.value = false
})

watch(() => player.src, () => {
  progressPct.value = 0
  requestAnimationFrame(() => {
    if (!audio.value) return
    audio.value.load()
    if (player.playing) audio.value.play().catch(() => {})
    syncProgressFromAudio(audio.value)
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
  syncProgressFromAudio(e.target)
}

function onLoaded(e) {
  if (audio.value) audio.value.volume = player.muted ? 0 : player.volume
  syncProgressFromAudio(e.target)
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
  if (!audio.value) return
  const total = Number(audio.value.duration)
  const fallback = Number(player.duration) || 0
  const dur = (Number.isFinite(total) && total > 0) ? total : fallback
  if (!(dur > 0)) return
  const t = (val / 100) * dur
  audio.value.currentTime = t
  progressPct.value = Math.min(100, Math.max(0, Number(val) || 0))
  player.setProgress(t, dur)
}

function onExternalSeek(e) {
  const t = Number(e.detail || 0)
  if (!audio.value || Number.isNaN(t)) return
  audio.value.currentTime = t
  player.setProgress(t, audio.value.duration || player.duration || 0)
}

function goPlayer() {
  // 「正在播放」大视图由全局抽屉承载（桌面覆盖内容区、移动端全屏），不再跳页
  player.fullPlayerOpen = true
}

function toggleQueue() {
  const next = !player.showQueue
  player.showQueue = next
  // 队列渲染在抽屉内，关闭抽屉时点队列需要一并把抽屉带出来
  if (next) player.fullPlayerOpen = true
}

// ---------- 音量浮层 ----------
// 触发：hover 或 focus 打开（键盘也走同一路径）；滚轮直接调音量。
// 关闭用"悬停意图"延时：指针要从图标移到浮层上，立即关闭会让滑杆根本拖不到。
const volumePanelOpen = ref(false)
const volumeAnchor = ref(null)
const volumePanel = ref(null)
let volumeCloseTimer = null

const volumePercent = computed(() => Math.round(player.volume * 100))
const volumeMuted = computed(() => player.muted || player.volume === 0)
const volumeText = computed(() => (player.muted ? '静音' : `${volumePercent.value}%`))
const volumeIcon = computed(() => {
  if (volumeMuted.value) return VolumeMute
  if (player.volume < 0.34) return VolumeLow
  if (player.volume < 0.77) return VolumeMedium
  return VolumeHigh
})
const volumeAriaLabel = computed(() =>
  player.muted ? '已静音，点击取消静音' : `音量 ${volumePercent.value}%，点击静音`)

function cancelVolumeClose() {
  if (volumeCloseTimer) {
    clearTimeout(volumeCloseTimer)
    volumeCloseTimer = null
  }
}

function openVolumePanel() {
  cancelVolumeClose()
  volumePanelOpen.value = true
}

function closeVolumePanel() {
  cancelVolumeClose()
  volumePanelOpen.value = false
}

function scheduleCloseVolumePanel() {
  cancelVolumeClose()
  volumeCloseTimer = setTimeout(() => {
    volumePanelOpen.value = false
    volumeCloseTimer = null
  }, 160)
}

/** 焦点移出浮层与图标之外才关闭；内部 Tab 切换保持打开 */
function onVolumeFocusOut(event) {
  const next = event.relatedTarget
  if (next && (volumePanel.value?.contains(next) || volumeAnchor.value?.contains(next))) return
  closeVolumePanel()
}

function setVolumePercent(percent) {
  player.setVolume(Number(percent) / 100)
}

function onVolumeWheel(event) {
  const step = event.deltaY < 0 ? 0.05 : -0.05
  // setVolume 在值 > 0 时会自动取消静音，符合"往上滚就恢复声音"的预期
  player.setVolume(Math.round((player.volume + step) * 100) / 100)
  openVolumePanel()
}

onMounted(() => window.addEventListener('sonpick-seek', onExternalSeek))
onUnmounted(() => {
  window.removeEventListener('sonpick-seek', onExternalSeek)
  cancelVolumeClose()
})
</script>

<style scoped>
.global-player {
  /* 本组件经 Teleport 挂载到 body，不在 n-config-provider 子树内，
     --n-* 主题变量不可达；颜色一律取 :root 上的 --sp-ui-* 令牌，不写死色值 */
  /* 苹果材质玻璃：半透明"材质"填充（亮 35% / 暗 40%，原为 70%）+ 强模糊 + 强 saturate
     提饱和（vibrancy 鲜亮感，苹果玻璃好看的核心）；靠模糊保文字对比，不写死色值随主题 */
  --gp-bg: color-mix(in srgb, var(--sp-ui-card-strong) 35%, transparent);
  --gp-border: color-mix(in srgb, var(--sp-ui-border) 62%, transparent);
  --gp-text: var(--sp-ui-text-1);
  --gp-text-3: var(--sp-ui-text-3);
  /* 玻璃感 = 外投影拉出悬浮 + 内高光勾出「厚度」 */
  --gp-shadow:
    0 18px 44px rgba(15, 23, 42, 0.16),
    0 6px 16px rgba(15, 23, 42, 0.07),
    inset 0 1px 0 rgba(255, 255, 255, 0.55);
  /* 悬浮胶囊：几何由 :root 的 --gp-* 变量驱动，改高度不用同步改圆角 */
  position: fixed;
  left: 24px;
  right: 24px;
  margin: 0 auto;
  max-width: 880px;
  bottom: calc(var(--gp-bar-gap) + var(--gp-bottom-offset));
  height: var(--gp-bar-height);
  z-index: 1000;
  display: grid;
  grid-template-columns: minmax(150px, 250px) minmax(0, 1fr) auto;
  align-items: center;
  gap: 16px;
  padding: 0 22px;
  box-sizing: border-box;
  overflow: hidden;
  border-radius: 999px;
  background: var(--gp-bg);
  border: 1px solid var(--gp-border);
  color: var(--gp-text);
  /* 模糊半径要足够大：糊掉封面花纹才能保住文字对比度；saturate 让透出来的颜色不发灰、反而更鲜（苹果 vibrancy） */
  backdrop-filter: blur(28px) saturate(1.9);
  -webkit-backdrop-filter: blur(28px) saturate(1.9);
  box-shadow: var(--gp-shadow);
}
.global-player.dark {
  --gp-bg: color-mix(in srgb, var(--sp-ui-elevated) 40%, transparent);
  --gp-shadow:
    0 18px 44px rgba(0, 0, 0, 0.55),
    0 6px 16px rgba(0, 0, 0, 0.35),
    inset 0 1px 0 rgba(255, 255, 255, 0.10);
}
/* 不支持 backdrop-filter 时退回高不透明度，避免文字压在封面花纹上不可读 */
@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
  .global-player {
    --gp-bg: color-mix(in srgb, var(--sp-ui-card-strong) 94%, transparent);
  }
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
  color: var(--gp-text-3);
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
  color: var(--gp-text-3);
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
.format-toggle {
  padding: 0;
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
  color: var(--gp-text-3);
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
.gp-progress-line {
  display: none;
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  overflow: hidden;
  border-radius: 999px 999px 0 0;
  background: var(--sp-ui-hover);
  pointer-events: none;
  z-index: 3;
}
.gp-progress-line .fill {
  display: block;
  height: 100%;
  width: 0%;
  background: var(--sp-ui-primary);
  will-change: width;
}
.gp-mobile-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}
/* 音量浮层：面板被 teleport 到 body，只能用 :root 上的 --sp-ui-* */
.gp-volume-anchor {
  display: inline-flex;
  align-items: center;
}
.gp-volume-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 12px 6px 10px;
  width: 46px;
}
/* 竖向滑块靠父容器定高：Naive 的 vertical slider 是 height:100% */
.gp-volume-slider {
  height: 96px;
  display: flex;
  justify-content: center;
}
.gp-volume-value {
  font-size: 11px;
  line-height: 1;
  color: var(--sp-ui-text-3);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.slide-up-enter-active,
.slide-up-leave-active {
  transition: transform 0.24s cubic-bezier(0.25, 1, 0.5, 1), opacity 0.24s ease;
}
.slide-up-enter-from,
.slide-up-leave-to {
  transform: translateY(140%);
  opacity: 0;
}

/* 中等宽度：胶囊变窄时先收掉音量条，保住中间进度条的可用宽度 */
@media (max-width: 1040px) {
  .global-player {
    grid-template-columns: minmax(130px, 1fr) minmax(0, 1.6fr) auto;
    gap: 12px;
  }
}
@media (max-width: 768px) {
  .global-player {
    left: 14px;
    right: 14px;
    max-width: none;
    grid-template-columns: minmax(0, 1fr) auto;
    padding: 0 14px;
    gap: 8px;
  }
  .gp-right {
    display: none;
  }
  .gp-progress-line {
    display: block;
  }
  .cover {
    width: 40px;
    height: 40px;
    border-radius: 10px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .slide-up-enter-active,
  .slide-up-leave-active {
    transition: none;
  }
}
</style>
