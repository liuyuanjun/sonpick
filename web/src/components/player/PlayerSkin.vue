<template>
  <div class="skin" :class="`skin-${playerSkin}`">
    <!-- 沉浸式皮肤：整幅模糊封面铺底 + 暗角（仅纯歌词/纯封面；唱片皮以唱片盘为焦点） -->
    <template v-if="showBackdrop">
      <div class="bgart" :style="bgStyle" aria-hidden="true"></div>
      <div class="vignette" aria-hidden="true"></div>
    </template>

    <!-- 叠层卡：左播放卡 + 右歌词 -->
    <div v-if="playerSkin === 'card'" class="body body-card">
      <div class="card">
        <div class="c-art"><player-art :cover="player.cover" :playing="player.playing" :record="true" /></div>
        <player-meta :show-cover="false" />
        <player-seek />
        <div class="c-transport">
          <player-utils :show="['quality', 'mode']" />
          <player-transport :size="46" />
          <player-utils :show="['volume', 'queue']" :compact="isMobile" />
        </div>
      </div>
      <div class="stage-lrc">
        <lyrics-view
          :lines="player.lyrics"
          :active-index="player.lyricIndex"
          :font-size="player.lyricFontSize"
          :immersive="true"
          :empty-title="lyricsEmptyTitle"
          :empty-description="lyricsEmptyDescription"
          @seek="onLyricSeek"
        />
      </div>
    </div>

    <!-- 唱片：巨大旋转唱片挂右上出血作背景 + 左侧歌词 -->
    <template v-else-if="playerSkin === 'vinyl'">
      <div class="vinyl-disc" :class="{ spin: player.playing }" aria-hidden="true">
        <div class="vd-groove"></div>
        <img v-if="player.cover && !vinylBroken" class="vd-face" :src="player.cover" alt="" @error="vinylBroken = true" @load="vinylBroken = false" />
        <div class="vd-veil"></div>
      </div>
      <div class="body body-vinyl">
        <div class="v-meta">
          <div class="v-title" :title="player.current?.title || '未在播放'">{{ player.current?.title || '未在播放' }}</div>
          <div class="v-artist">{{ vinylSubline }}</div>
        </div>
        <div class="v-lrc">
          <lyrics-view
            :lines="player.lyrics"
            :active-index="player.lyricIndex"
            :font-size="player.lyricFontSize"
            :immersive="true"
            :align-left="true"
            :empty-title="lyricsEmptyTitle"
            :empty-description="lyricsEmptyDescription"
            @seek="onLyricSeek"
          />
        </div>
      </div>
      <player-band />
    </template>

    <!-- 纯歌词：整幅模糊封面铺底 + 居中歌词 -->
    <template v-else-if="playerSkin === 'lyrics'">
      <div class="body body-lyrics">
        <lyrics-view
          :lines="player.lyrics"
          :active-index="player.lyricIndex"
          :font-size="player.lyricFontSize"
          :immersive="true"
          :empty-title="lyricsEmptyTitle"
          :empty-description="lyricsEmptyDescription"
          @seek="onLyricSeek"
        />
      </div>
      <player-band />
    </template>

    <!-- 纯封面：大封面居中 -->
    <template v-else>
      <div class="body body-art">
        <div class="art-stage"><player-art :cover="player.cover" :playing="player.playing" :record="true" /></div>
        <div v-if="techLine" class="tech">{{ techLine }}</div>
      </div>
      <player-band />
    </template>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import LyricsView from '@/components/player/LyricsView.vue'
import PlayerArt from '@/components/player/PlayerArt.vue'
import PlayerBand from '@/components/player/PlayerBand.vue'
import PlayerMeta from '@/components/player/PlayerMeta.vue'
import PlayerSeek from '@/components/player/PlayerSeek.vue'
import PlayerTransport from '@/components/player/PlayerTransport.vue'
import PlayerUtils from '@/components/player/PlayerUtils.vue'
import { usePlayerStore } from '@/stores/player'
import { useIsMobile } from '@/composables/useIsMobile'
import { formatLabel } from '@/utils/media'

// 皮肤渲染器：按 playerSkin 切换整套布局（叠层卡 / 唱片 / 纯歌词 / 纯封面）。
// 纯展示 + 组合共享件；播放状态、歌词、进度都从 store 读，不自己取数。
const player = usePlayerStore()
const isMobile = useIsMobile()

const playerSkin = computed(() => player.currentSkin.id)
// 模糊封面铺底只用于「纯歌词 / 纯封面」；唱片皮以唱片盘为视觉焦点，不叠模糊底（否则会糊成一片）
const showBackdrop = computed(() => playerSkin.value === 'lyrics' || playerSkin.value === 'art')
const bgStyle = computed(() =>
  player.cover ? { backgroundImage: `url(${player.cover})` } : {},
)

const vinylBroken = ref(false)
watch(() => player.cover, () => { vinylBroken.value = false })

const lyricsEmptyTitle = computed(() => (player.lyricsMeta.instrumental ? '纯音乐' : '暂无歌词'))
const lyricsEmptyDescription = computed(() =>
  player.lyricsMeta.instrumental ? '该歌曲已标记为纯音乐' : '可点击上方获取歌词',
)
const vinylSubline = computed(() =>
  [player.current?.artist, player.current?.album].filter(Boolean).join(' · '),
)
// 纯封面视图的技术信息行（格式 · 时长 · 体积）：是曲库用户关心、且别处没有的信息
const techLine = computed(() => {
  const v = player.current?.preferred_version
  const parts = []
  if (v?.format) parts.push(formatLabel(v.format, ''))
  if (player.current?.duration) parts.push(formatDuration(player.current.duration))
  if (v?.file_size) parts.push(formatSize(v.file_size))
  return parts.filter(Boolean).join(' · ')
})

function formatDuration(sec) {
  const s = Number(sec) || 0
  const m = Math.floor(s / 60)
  return `${m}:${String(s % 60).padStart(2, '0')}`
}
function formatSize(bytes) {
  const b = Number(bytes) || 0
  if (b <= 0) return ''
  if (b < 1024 * 1024) return `${Math.round(b / 1024)} KB`
  return `${(b / 1024 / 1024).toFixed(1)} MB`
}
function onLyricSeek(time) {
  const t = Number(time)
  if (!Number.isFinite(t) || t < 0) return
  window.dispatchEvent(new CustomEvent('sonpick-seek', { detail: t }))
}
</script>

<style scoped>
.skin {
  position: relative;
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  z-index: 1;
}

/* ---- 沉浸式背景：模糊封面铺底 + 暗角 ---- */
.bgart {
  position: absolute;
  inset: -16%;
  background-size: cover;
  background-position: center;
  filter: blur(58px) saturate(1.22) brightness(0.56);
  opacity: 0.9;
  pointer-events: none;
}
.player-panel.light .bgart {
  filter: blur(58px) saturate(1.05) brightness(1.18);
  opacity: 0.55;
}
.vignette {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: radial-gradient(64% 74% at 50% 44%, rgba(5, 6, 10, 0.04), rgba(5, 6, 10, 0.72) 92%);
}
.player-panel.light .vignette {
  background: radial-gradient(64% 74% at 50% 44%, rgba(245, 246, 248, 0.3), rgba(245, 246, 248, 0.86) 90%);
}

.body {
  position: relative;
  z-index: 2;
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
}

/* ---- 叠层卡：卡片 + 歌词 ----
   布局按「常量」而非「内容」计算，所以歌词怎么变都不会推动卡片：
     左外边距 = (屏宽 − 卡片宽 − 间隙 − 歌词合适宽) / 2
     → [卡片 + 合适宽歌词] 这一块近似居中；卡片右侧的剩余空间全部归歌词，
       略超「合适宽」的单行歌词不必换行/省略，直接往右伸即可（容器只在纵向滚动）。 */
.body-card {
  --card-w: 352px;
  --card-gap: 72px;
  --lyr-w: 560px;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: var(--card-gap);
  padding: 20px clamp(24px, 5vw, 64px) 20px
    max(0px, calc((100% - var(--card-w) - var(--card-gap) - var(--lyr-w)) / 2));
}
.card {
  flex: 0 0 var(--card-w);
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.c-art {
  /* 封面宽度 = 卡片内容宽度（与下方元信息/进度/传输对齐，不再居中收窄） */
  width: 100%;
  margin: 0 0 18px;
}
.c-transport {
  margin-top: 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.c-transport > :first-child,
.c-transport > :last-child {
  flex: 0 0 auto;
}
/* 卡片里的元信息条与进度铺满卡宽 */
.card :deep(.pmeta) {
  margin-bottom: 12px;
}
.stage-lrc {
  /* 卡片右侧整片都归歌词（flex:1）；宽度由容器决定、与歌词内容无关 → 不会推动卡片 */
  flex: 1 1 auto;
  min-width: 0;
  align-self: center;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.stage-lrc :deep(.lyrics) {
  flex: 1;
  min-height: 0;
  text-align: left;
}
/* 长行**允许换行**（歌词区已加宽，正常长度不会折行，只有超长行才合理折到下一行）；
   不用省略号——折行比截断好读。
   选择器写到 .lyrics .line 是为了压过 LyricsView 自己的 .line 规则（同为两段时先后次序不定）。 */
.stage-lrc :deep(.lyrics .line) {
  white-space: normal;
  overflow: visible;
  text-overflow: clip;
  overflow-wrap: break-word;
}

/* ---- 唱片：巨大旋转唱片挂右上出血，标题/歌手左上，歌词左对齐 ---- */
/* 出血量按黄金比例：只藏一个「半径 × (1-1/φ) ≈ 0.382」的角帽（≈直径的 19%），大部分盘面可见。
   半径按「盘面 − 盘面与标签的半径差的三分之一」收小：R' = R − (R − R_label)/3，R_label = R/φ ≈ 0.618R
   → R' ≈ 0.873R（40vh → 35vh）。尺寸用 vh，窗口缩放时盘面等比跟随。 */
.vinyl-disc {
  --disc-r: 35vh;
  --disc-cap: calc(var(--disc-r) * 0.382);
  position: absolute;
  top: calc(var(--disc-cap) * -1);
  right: calc(var(--disc-cap) * -1);
  width: calc(var(--disc-r) * 2);
  height: calc(var(--disc-r) * 2);
  z-index: 0;
  pointer-events: none;
}
.vd-groove {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background:
    conic-gradient(from 205deg at 50% 50%, rgba(255, 255, 255, 0.13), rgba(255, 255, 255, 0) 62deg, rgba(255, 255, 255, 0) 296deg, rgba(255, 255, 255, 0.1) 360deg),
    repeating-radial-gradient(circle at center, #17181d 0 1.6px, #0c0d10 1.6px 3.2px);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.08), inset 0 0 90px rgba(0, 0, 0, 0.45), 0 40px 90px rgba(0, 0, 0, 0.5);
}
/* 盘面 = 沟槽环（大尺寸下沟槽真正可读）+ 封面作中心标签 + 缓慢自转。
   标签半径 = 盘面半径 × 1/φ ≈ 0.618（黄金比例大份）：封面是主体、外圈沟槽是唱片暗示。
   不画中心孔——标签已占盘面一大半，孔会落在封面主体（多是人脸）的圆心上，反而难看。 */
.vd-face {
  position: absolute;
  left: 19.1%;
  top: 19.1%;
  width: 61.8%;
  height: 61.8%;
  border-radius: 50%;
  object-fit: cover;
  box-shadow: 0 0 0 4px rgba(0, 0, 0, 0.45);
  filter: brightness(0.82) saturate(1.05);
}
.vd-veil {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: radial-gradient(circle at 34% 30%, rgba(6, 7, 11, 0.1), rgba(6, 7, 11, 0.34) 78%);
}
/* 整张唱片（沟槽 + 封面标签 + 中心孔）一起转，才是"唱片在转"；
   只转沟槽的话标签不动，看着是穿帮的。 */
.vinyl-disc.spin {
  animation: spin 30s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.body-vinyl {
  flex-direction: column;
  padding: 22px 24px 0 88px;
}
.v-title {
  font-size: 30px;
  font-weight: 700;
  letter-spacing: 0.01em;
  color: var(--fg);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.v-artist {
  margin-top: 8px;
  font-size: 15px;
  color: var(--fg-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.v-lrc {
  margin-top: 30px;
  flex: 1;
  min-height: 0;
  max-width: 520px;
  display: flex;
  flex-direction: column;
}
.v-lrc :deep(.lyrics) {
  flex: 1;
  min-height: 0;
  text-align: left;
}

/* ---- 纯歌词 ---- */
.body-lyrics {
  align-items: stretch;
  justify-content: center;
}
.body-lyrics :deep(.lyrics) {
  flex: 1;
  min-height: 0;
  width: min(680px, 78%);
  margin: 0 auto;
  text-align: center;
}

/* ---- 纯封面 ---- */
.body-art {
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 0;
}
.art-stage {
  width: min(46vh, 420px);
}
.art-stage :deep(.art-wrap) {
  width: 100%;
}
.tech {
  margin-top: 22px;
  font-size: 12px;
  color: var(--fg-3);
  letter-spacing: 0.03em;
}

/* 移动端：窄屏收拢（叠层卡在移动端不可用，由 store 收敛掉，故这里不再有它的覆盖样式） */
@media (max-width: 768px) {
  .body-vinyl {
    padding: 16px 22px 0;
  }
  .vinyl-disc {
    --disc-r: 65vw;
    --disc-cap: calc(var(--disc-r) * 0.382);
  }
  .v-title {
    font-size: 22px;
  }
  .art-stage {
    width: min(52vw, 300px);
  }
}
</style>
