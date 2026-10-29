<template>
  <teleport to="body">
    <transition name="slide-up">
    <div v-if="player.showPlayer && player.current" class="global-player" :class="{ dark: themeStore.isDark }" :style="accentStyle">
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
          <n-icon class="gp-ico"><musical-notes /></n-icon>
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
                class="gp-btn format-toggle"
                :class="{ active: player.losslessPreferred }"
                @click="player.toggleLosslessPreferred()"
              >
                <template #icon>
                  <n-icon class="gp-ico gp-ico--optical">
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
              <n-button quaternary circle class="gp-btn" @click="player.toggleMode()">
                <n-icon class="gp-ico">
                  <shuffle v-if="player.mode === 'shuffle'" />
                  <repeat v-else-if="player.mode === 'loop'" />
                  <reload v-else-if="player.mode === 'single'" />
                  <list-outline v-else />
                </n-icon>
              </n-button>
            </template>
            {{ player.modeLabel }}
          </n-tooltip>
          <n-button quaternary circle class="gp-btn" aria-label="上一曲" @click="player.prev()">
            <n-icon class="gp-ico gp-ico--nav"><play-skip-back /></n-icon>
          </n-button>
          <n-button type="primary" circle class="gp-btn gp-play" aria-label="播放/暂停" @click="togglePlay">
            <n-icon class="gp-ico gp-ico--play" :class="{ 'is-play': !player.playing }">
              <pause v-if="player.playing" />
              <play v-else />
            </n-icon>
          </n-button>
          <n-button quaternary circle class="gp-btn" aria-label="下一曲" @click="player.next()">
            <n-icon class="gp-ico gp-ico--nav"><play-skip-forward /></n-icon>
          </n-button>
          <n-tooltip>
            <template #trigger>
              <n-button
                quaternary
                circle
                class="gp-btn"
                :class="{ active: player.showQueue }"
                aria-label="播放队列"
                @click="toggleQueue"
              >
                <n-icon class="gp-ico"><list /></n-icon>
              </n-button>
            </template>
            {{ player.showQueue ? '收起队列' : '播放队列' }}
          </n-tooltip>
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
            :style="[accentStyle, { borderRadius: 'var(--sp-radius-lg)' }]"
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
                  class="gp-btn"
                  :class="{ active: volumePanelOpen }"
                  :aria-label="volumeAriaLabel"
                  aria-haspopup="true"
                  :aria-expanded="volumePanelOpen"
                  @click="player.toggleMute()"
                  @focus="openVolumePanel"
                >
                  <n-icon class="gp-ico"><component :is="volumeIcon" /></n-icon>
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
                  class="gp-volume-rail"
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
                class="gp-btn gp-btn--sm"
                :aria-label="player.muted ? '取消静音' : '静音'"
                @click="player.toggleMute()"
              >
                <n-icon class="gp-ico gp-ico--quiet">
                  <volume-mute v-if="volumeMuted" />
                  <volume-medium v-else />
                </n-icon>
              </n-button>
            </div>
          </n-popover>
        </div>
        <div class="progress-row">
          <span>{{ formatClock(player.currentTime) }}</span>
          <n-slider class="gp-progress" :value="progress" :step="0.1" :tooltip="false" @update:value="seek" />
          <span>{{ formatClock(player.duration) }}</span>
        </div>
      </div>

      <div v-if="isMobile" class="gp-mobile-actions">
        <n-button quaternary circle class="gp-btn gp-play" aria-label="播放/暂停" @click="togglePlay">
          <n-icon class="gp-ico gp-ico--play">
            <pause v-if="player.playing" />
            <play v-else />
          </n-icon>
        </n-button>
        <n-button quaternary circle class="gp-btn" aria-label="下一曲" @click="player.next()">
          <n-icon class="gp-ico gp-ico--nav"><play-skip-forward /></n-icon>
        </n-button>
      </div>

      <div v-if="!isMobile" class="gp-right">
        <n-button quaternary circle class="gp-btn" aria-label="打开播放器" @click="goPlayer">
          <n-icon class="gp-ico gp-ico--quiet"><expand /></n-icon>
        </n-button>
        <n-button quaternary circle class="gp-btn" aria-label="关闭播放器" @click="player.close()">
          <n-icon class="gp-ico gp-ico--quiet"><close /></n-icon>
        </n-button>
      </div>
    </div>
  </transition>
  </teleport>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  PlayerPlay as Play,
  PlayerPause as Pause,
  X as Close,
  Music as MusicalNotes,
  PlayerSkipBack as PlaySkipBack,
  PlayerSkipForward as PlaySkipForward,
  ArrowsShuffle as Shuffle,
  Repeat,
  Refresh as Reload,
  List,
  List as ListOutline,
  Volume as VolumeHigh,
  Volume3 as VolumeLow,
  Volume2 as VolumeMedium,
  ArrowsMaximize as Expand,
  Diamond as DiamondOutline,
  Bolt as FlashOutline,
} from '@vicons/tabler'
import VolumeMute from '@/components/icons/VolumeOffIcon.vue'
import { NPopover, NSlider, useMessage } from 'naive-ui'
import { usePlayerStore } from '@/stores/player'
import { useThemeStore } from '@/stores/theme'
import { useIsMobile } from '@/composables/useIsMobile'
import { useMediaSession } from '@/composables/useMediaSession'
import { formatClock } from '@/utils/format'
import { extractAccentFromImage } from '@/utils/color'

const player = usePlayerStore()
const themeStore = useThemeStore()
const message = useMessage()
const isMobile = useIsMobile()
const audio = ref(null)
const coverBroken = ref(false)
// 胶囊不在全屏播放器抽屉里，取不到抽屉按封面注入的 --accent，需要自己算一次，
// 这样「正在播放」的颜色语言（播放键 / 进度 / 音量）与全屏播放器完全一致。
const accent = ref(null)
watch(
  () => player.cover,
  async (url) => {
    accent.value = null
    if (!url) return
    accent.value = await extractAccentFromImage(url)
  },
  { immediate: true },
)
const accentStyle = computed(() => {
  const a = accent.value
  return {
    '--accent': a ? a.css : 'var(--sp-ui-primary)',
    '--play-bg': a ? a.css : 'var(--sp-ui-primary)',
    '--play-fg': a ? a.on || '#FFFFFF' : 'var(--sp-ui-on-primary)',
  }
})
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
/* ══════════════════════════════════════════════════════════════════════════
   悬浮播放胶囊 · 视觉规格（v0.15.2-rc16 重做尺度）

   本组件经 Teleport 挂载到 body，不在 n-config-provider 子树内，
   --n-* 主题变量不可达；颜色一律取 :root 上的 --sp-ui-* 令牌，不写死色值。

   尺度只有一套，全部以组件局部变量声明（下方 --gp-*），改动只改这一处：
     几何  cover 48 / 次级按钮 36（= 触控目标）/ 播放键 40 / 圆角与描边走令牌
     图标  次级 20（= ICON.md）/ 传输 24（= ICON.lg）/ 播放 = 播放键直径 × 0.55
   ⚠️ 历史问题：图标曾用 15 / 18 / 20 / 23 四个各自为政的 px 值，15px 的「音质」
   比 23px 的播放图标小 35%，同一行里视觉重量完全不成比例。现在收敛为两档，
   且都取自 tokens.js 的 ICON 尺度 —— 新增图标只许选这两档，不要再写第三个数。
   ══════════════════════════════════════════════════════════════════════════ */

/* ── 共享尺度 / 前景色变量 ──
   ⚠️ 音量浮层被 n-popover teleport 到 body，**不在 .global-player 的子树里**，
   拿不到挂在 .global-player 上的 --gp-*（实测后果：竖向滑杆的 --n-rail-color 引用不存在的
   变量 → invalid at computed-value time → 轨道变透明，音量条只剩一根红色填充悬空）。
   所以这组变量必须同时声明在两个根上，且只能引用 :root 的 --sp-*。 */
.global-player,
.gp-volume-panel {
  --gp-btn-size: var(--sp-touch-target); /* 36px：与全局触控目标同尺 */
  --gp-btn-sm-size: 30px; /* 音量浮层内的小按钮（浮层本身只有 56px 宽） */
  --gp-play-size: 40px;
  --gp-ico: var(--sp-icon-md); /* 20px：模式 / 队列 / 音量 / 音质 */
  --gp-ico-nav: var(--sp-icon-lg); /* 24px：上一曲 / 下一曲 */
  --gp-ico-quiet: var(--sp-icon-md); /* 展开 / 关闭：同尺度，靠颜色退后 */
  /* 播放/暂停图标 = 播放键直径 × 0.55（40 → 22）。不写死 22 是因为它必须随
     --gp-play-size 联动；0.55 与 PlayerTransport 的 Math.round(size * 0.5) 是同一套比例。 */
  --gp-ico-play: calc(var(--gp-play-size) * 0.55);

  --gp-text: var(--sp-ui-text-1);
  --gp-text-2: var(--sp-ui-text-2);
  --gp-text-3: var(--sp-ui-text-3);
  /* 滑轨：由文字色掺出来，明暗两套自动成立，不额外定义色值 */
  --gp-track: color-mix(in srgb, var(--sp-ui-text-1) 13%, transparent);
}

.global-player {
  /* ── 尺度 ── */
  --gp-cover-size: 48px;

  /* ── 颜色 ──
     玻璃填充取「卡片面」再掺透明度（而不是页面底色）：
     浅色卡片 #FFF 比页面底 #F5F6F8 更亮、暗色卡片 #14161C 也比页面底 #0B0C10 更亮，
     两个方向都比「底色掺 60%」更能把文字从背后内容里托起来，观感也更像毛玻璃而非灰板。 */
  --gp-bg: color-mix(in srgb, var(--sp-ui-card) 76%, transparent);
  --gp-border: color-mix(in srgb, var(--sp-ui-border) 66%, transparent);

  /* ── 阴影：三明治层次 = 贴地一像素 + 中景扩散 + 远景柔光 + 顶部内高光 ── */
  --gp-shadow:
    0 1px 2px rgba(15, 23, 42, 0.04),
    0 8px 20px -6px rgba(15, 23, 42, 0.1),
    0 24px 56px -16px rgba(15, 23, 42, 0.16),
    inset 0 1px 0 rgba(255, 255, 255, 0.72);

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
  gap: 18px;
  padding: 0 20px;
  box-sizing: border-box;
  overflow: hidden;
  border-radius: var(--sp-radius-pill);
  background: var(--gp-bg);
  border: 1px solid var(--gp-border);
  color: var(--gp-text);
  /* 模糊 16px 是「材质」与「透明」的临界档：足够让背后内容不可解析（保住图底分离、不跟滚动内容抢注意力），
     又保留颜色与块面感；28px 会把背后完全洗成灰板，8px 则只留噪声且亮封面滚过时最伤白字对比。
     saturate 1.35 只做轻微提鲜，1.9 会把背后的封面推成荧光色团。 */
  backdrop-filter: blur(16px) saturate(1.35);
  -webkit-backdrop-filter: blur(16px) saturate(1.35);
  box-shadow: var(--gp-shadow);
}
.global-player.dark {
  --gp-bg: color-mix(in srgb, var(--sp-ui-card) 72%, transparent);
  --gp-shadow:
    0 1px 2px rgba(0, 0, 0, 0.24),
    0 8px 20px -6px rgba(0, 0, 0, 0.46),
    0 24px 56px -16px rgba(0, 0, 0, 0.54),
    inset 0 1px 0 rgba(255, 255, 255, 0.07);
}
/* 不支持 backdrop-filter 时退回高不透明度，避免文字压在封面花纹上不可读
   （放在 .dark 之后且同特异性，因此暗色下也能正常覆盖上一条） */
@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
  .global-player {
    --gp-bg: color-mix(in srgb, var(--sp-ui-card) 96%, transparent);
  }
}

/* ── 左：封面 + 曲目信息 ───────────────────────────────────────────── */
.gp-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  cursor: pointer;
}
.cover {
  width: var(--gp-cover-size);
  height: var(--gp-cover-size);
  border-radius: var(--sp-radius-sm);
  object-fit: cover;
  flex-shrink: 0;
  background: color-mix(in srgb, var(--sp-ui-text-1) 8%, transparent);
  /* 一圈 1px 亮边把封面从玻璃面上「抬」起来；纯投影会让浅色封面上半部糊在底色里 */
  box-shadow:
    0 0 0 1px rgba(15, 23, 42, 0.06),
    0 2px 6px rgba(15, 23, 42, 0.1);
  transition: transform var(--sp-dur-fast) var(--sp-ease-enter);
}
.dark .cover {
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.08),
    0 2px 8px rgba(0, 0, 0, 0.5);
}
.gp-left:hover .cover {
  transform: scale(1.03);
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
  gap: 2px;
}
.title {
  font-size: var(--sp-fs-body);
  font-weight: var(--sp-fw-semibold);
  line-height: 1.35;
  letter-spacing: -0.005em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: color var(--sp-dur-fast) var(--sp-ease-standard);
}
.gp-left:hover .title {
  color: var(--sp-ui-primary);
}
.artist {
  font-size: var(--sp-fs-caption);
  font-weight: var(--sp-fw-medium);
  line-height: 1.35;
  color: var(--gp-text-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── 中：控制区 + 进度 ─────────────────────────────────────────────── */
.gp-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  min-width: 0;
}
.controls {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* 圆形图标按钮的统一规格。
   Naive 把 --n-width / --n-height / --n-icon-size / 颜色类变量全写在元素 inline style 上，
   类选择器压不住，必须 !important（否则会出现「静息态对、hover 变回品牌绿」的割裂）。 */
.gp-btn {
  --n-width: var(--gp-btn-size) !important;
  --n-height: var(--gp-btn-size) !important;
  --n-icon-size: var(--gp-ico) !important;
  --n-padding: 0 !important;
  --n-text-color: var(--gp-text-2) !important;
  --n-text-color-hover: var(--gp-text) !important;
  --n-text-color-pressed: var(--gp-text) !important;
  --n-text-color-focus: var(--gp-text) !important;
}
.gp-btn--sm {
  --n-width: var(--gp-btn-sm-size) !important;
  --n-height: var(--gp-btn-sm-size) !important;
}
/* 激活态（队列展开 / 音量浮层打开 / 无损优先）：用被封面的主色点一下，
   只加软底不改尺寸，避免按钮在开合时跳动 */
.gp-btn.active {
  --n-text-color: var(--accent, var(--sp-ui-primary)) !important;
  --n-text-color-hover: var(--accent, var(--sp-ui-primary)) !important;
  --n-text-color-pressed: var(--accent, var(--sp-ui-primary)) !important;
}
.gp-btn.active::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: color-mix(in srgb, var(--accent, var(--sp-ui-primary)) 12%, transparent);
  pointer-events: none;
}

/* 图标：显式尺寸（@vicons 的 SVG 没有 width/height，只认容器的 1em），
   并让容器宽高等于图标尺寸 —— 只写 font-size 会让 flex 轨道按旧值占位 */
.gp-ico {
  font-size: var(--gp-ico) !important;
  transition: transform var(--sp-dur-fast) var(--sp-ease-enter);
}
.gp-ico--nav {
  font-size: var(--gp-ico-nav) !important;
}
.gp-ico--play {
  font-size: var(--gp-ico-play) !important;
}
.gp-ico--quiet {
  font-size: var(--gp-ico-quiet) !important;
  color: var(--gp-text-3);
}
/* 音质按钮用的是 n-button 的 #icon 插槽，槽宽由 --n-icon-size 决定；
   图标做了 +1px 光学补偿，槽宽必须同步，否则 1px 溢出会让图标左右各偏半像素 */
.format-toggle {
  --n-icon-size: calc(var(--gp-ico) + 1px) !important;
}
/* 音质图标的光学补偿：闪电 / 钻石都是「细线 + 小墨量」图形，同样 20px 下比
   repeat / list 这类满格图形显小一圈（用户实测感知就是这个）。放大 1px 让墨量对齐，
   属于同一尺度档位内的光学修正，不是新增第 3 个图标尺寸。 */
.gp-ico--optical {
  font-size: calc(var(--gp-ico) + 1px) !important;
}
/* Naive 的按钮把 outline 抹成 none，全局 :focus-visible 压不住 → 键盘焦点环必须显式补。
   环色 = 封面主色掺「本主题文字色」：只掺透明度时，亮黄/浅粉封面派生出的主色在浅底上
   几乎不可见；掺向文字色等于自动朝「远离底色」的方向走，明暗两套都保得住可见性。 */
.gp-btn:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--accent, var(--sp-ui-primary)) 72%, var(--gp-text)) !important;
  outline-offset: 2px !important;
}
.gp-btn:hover .gp-ico--quiet {
  color: var(--gp-text-2);
}

/* ── 播放键：外观的唯一真相源（与 PlayerTransport 的 .tp-play 同策略） ── */
.gp-play {
  --n-width: var(--gp-play-size) !important;
  --n-height: var(--gp-play-size) !important;
  --n-icon-size: var(--gp-ico-nav) !important;
  background: var(--play-bg) !important;
  color: var(--play-fg) !important;
  --n-color: var(--play-bg) !important;
  --n-color-hover: var(--play-bg) !important;
  --n-color-pressed: var(--play-bg) !important;
  --n-color-focus: var(--play-bg) !important;
  --n-text-color: var(--play-fg) !important;
  --n-text-color-hover: var(--play-fg) !important;
  --n-text-color-pressed: var(--play-fg) !important;
  --n-text-color-focus: var(--play-fg) !important;
  --n-border: 0 solid transparent;
  --n-border-hover: 0 solid transparent;
  --n-border-pressed: 0 solid transparent;
  --n-border-focus: 0 solid transparent;
  /* 点击波纹也吃 --n-ripple-color（同为 inline style），少了 !important 按下时会闪一圈品牌绿 */
  --n-ripple-color: transparent !important;
  /* 投影取自身主色，让播放键「发光」而不是投一块灰 */
  box-shadow:
    0 1px 2px rgba(15, 23, 42, 0.16),
    0 6px 16px -4px color-mix(in srgb, var(--play-bg) 46%, transparent);
  transition:
    transform var(--sp-dur-fast) var(--sp-ease-enter),
    box-shadow var(--sp-dur-fast) var(--sp-ease-standard);
}
.gp-play:hover {
  transform: translateY(-1px);
  box-shadow:
    0 1px 2px rgba(15, 23, 42, 0.18),
    0 10px 22px -4px color-mix(in srgb, var(--play-bg) 52%, transparent);
}
.gp-play:active {
  transform: translateY(0) scale(0.97);
}
.gp-play:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--play-bg) 72%, var(--gp-text));
  outline-offset: 3px;
}
.gp-play :deep(.n-button__border),
.gp-play :deep(.n-button__state-border) {
  display: none;
}
.gp-play :deep(.n-button__content) {
  color: var(--play-fg);
}
/* 播放三角的光学重心偏左，往右轻推一点才是"看起来居中"（暂停的双竖条是对称的，不用推） */
.gp-play :deep(.n-icon.is-play) {
  transform: translateX(1.5px);
}

/* ── 进度行 ───────────────────────────────────────────────────────────
   时间列给 42px（可容纳 1:23:45），数字等宽避免秒跳时整行抖动 */
.progress-row {
  width: min(520px, 100%);
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr) 42px;
  gap: 10px;
  align-items: center;
}
.progress-row span {
  font-size: var(--sp-fs-caption);
  font-weight: var(--sp-fw-medium);
  color: var(--gp-text-3);
  font-variant-numeric: tabular-nums;
  text-align: center;
  letter-spacing: 0.01em;
}

/* ── 滑杆：轨道 / 已播填充 / 手柄 ─────────────────────────────────────
   Naive 把滑杆的颜色与几何变量同样写在 inline style 上，一律 !important。
   手柄原来是纯白 + Naive 默认投影，浅色玻璃底上几乎看不见 ——
   补一圈 1px 冷灰描边 + 下投阴影，让它在两种主题下都能被看见。 */
.gp-progress,
.gp-volume-rail {
  --n-rail-height: 5px !important;
  --n-rail-width-vertical: 5px !important;
  --n-handle-size: 13px !important;
  --n-handle-color: #fff !important;
  --n-handle-box-shadow: 0 0 0 1px rgba(15, 23, 42, 0.12), 0 2px 6px rgba(15, 23, 42, 0.22) !important;
  --n-handle-box-shadow-hover: 0 0 0 1px rgba(15, 23, 42, 0.14), 0 2px 8px rgba(15, 23, 42, 0.26) !important;
  --n-handle-box-shadow-active: 0 0 0 1px rgba(15, 23, 42, 0.14), 0 2px 8px rgba(15, 23, 42, 0.26) !important;
  --n-handle-box-shadow-focus: 0 0 0 2px color-mix(in srgb, var(--accent, var(--sp-ui-primary)) 45%, transparent) !important;
  --n-fill-color: var(--accent, var(--sp-ui-primary)) !important;
  --n-fill-color-hover: var(--accent, var(--sp-ui-primary)) !important;
  --n-rail-color: var(--gp-track) !important;
  --n-rail-color-hover: var(--gp-track) !important;
}
.dark .gp-progress,
.dark .gp-volume-rail {
  --n-handle-box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.35), 0 2px 6px rgba(0, 0, 0, 0.55) !important;
  --n-handle-box-shadow-hover: 0 0 0 1px rgba(0, 0, 0, 0.4), 0 2px 8px rgba(0, 0, 0, 0.6) !important;
  --n-handle-box-shadow-active: 0 0 0 1px rgba(0, 0, 0, 0.4), 0 2px 8px rgba(0, 0, 0, 0.6) !important;
}

/* ── 右：展开 / 关闭 ───────────────────────────────────────────────── */
.gp-right {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 2px;
  min-width: 0;
}
.gp-mobile-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}

/* 移动端顶部细进度线（桌面隐藏，进度由进度条表达） */
.gp-progress-line {
  display: none;
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  overflow: hidden;
  border-radius: var(--sp-radius-pill) var(--sp-radius-pill) 0 0;
  background: color-mix(in srgb, var(--sp-ui-text-1) 12%, transparent);
  pointer-events: none;
  z-index: 3;
}
.gp-progress-line .fill {
  display: block;
  height: 100%;
  width: 0%;
  background: var(--accent, var(--sp-ui-primary));
  will-change: width;
}

/* ── 音量浮层 ───────────────────────────────────────────────────────
   面板被 teleport 到 body，只能用 :root 上的 --sp-ui-*（--gp-* 挂在 .global-player 上取不到） */
.gp-volume-anchor {
  display: inline-flex;
  align-items: center;
}
.gp-volume-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 12px 8px 8px;
  width: 56px;
}
/* 竖向滑块靠父容器定高：Naive 的 vertical slider 是 height:100% */
.gp-volume-slider {
  height: 96px;
  display: flex;
  justify-content: center;
}
.gp-volume-value {
  font-size: var(--sp-fs-caption);
  font-weight: var(--sp-fw-semibold);
  line-height: 1;
  color: var(--sp-ui-text-2);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  letter-spacing: 0.01em;
}
.gp-volume-panel .gp-btn--sm {
  --n-text-color: var(--sp-ui-text-3) !important;
  --n-text-color-hover: var(--sp-ui-text-1) !important;
}

/* ── 进出场 ───────────────────────────────────────────────────────── */
.slide-up-enter-active,
.slide-up-leave-active {
  transition:
    transform var(--sp-dur-slow) var(--sp-ease-enter),
    opacity var(--sp-dur-slow) var(--sp-ease-standard);
}
.slide-up-enter-from,
.slide-up-leave-to {
  transform: translateY(140%);
  opacity: 0;
}

/* 中等宽度：胶囊变窄时先收掉两侧余量，保住中间进度条的可用宽度 */
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
    --gp-cover-size: 40px;
    /* 移动端胶囊只有 60px 高，播放键收到 36 与其余按钮同高，仍保留实心主色以维持主操作地位 */
    --gp-play-size: var(--sp-touch-target);
    /* 传输键也收到 20：60px 高的窄条里，24px 的下一页箭头会比实心播放键更抢眼 */
    --gp-ico-nav: var(--sp-icon-md);
  }
  .gp-right {
    display: none;
  }
  .gp-progress-line {
    display: block;
  }
  .title {
    font-size: var(--sp-fs-small);
  }
}
@media (prefers-reduced-motion: reduce) {
  .slide-up-enter-active,
  .slide-up-leave-active {
    transition: none;
  }
  .cover,
  .gp-play,
  .gp-ico {
    transition: none;
  }
  .gp-left:hover .cover,
  .gp-play:hover,
  .gp-play:active {
    transform: none;
  }
}
</style>
