<template>
  <div class="pm">
    <n-card size="small" class="pm-card">
      <template #header>
        <div class="pm-head">
          <div>
            <div class="pm-title">管理歌单</div>
            <div class="pm-hint">
              拖动行首手柄调整顺序（也可聚焦手柄后按 <kbd>Alt</kbd>+<kbd>↑</kbd> / <kbd>Alt</kbd>+<kbd>↓</kbd>）。
              这个顺序就是侧边栏「歌单」子菜单取前 5 个的依据。
            </div>
          </div>
          <n-button size="small" type="primary" @click="openCreate">
            <template #icon><n-icon><CreateOutline /></n-icon></template>
            新建歌单
          </n-button>
        </div>
      </template>

      <n-empty v-if="!items.length && !loading" description="还没有歌单，先新建一个" class="pm-empty" />

      <!--
        拖拽用手写 pointer 事件而不是 HTML5 draggable：
        HTML5 DnD 在触屏上不工作，且无法在 CDP 里可靠地合成事件做实测。
        这里 1) 拖动中实时重排数组、其余行 FLIP 跟位；2) 松手才落库。
      -->
      <ul v-else ref="listEl" class="pm-list" :data-dragging="dragging ? 'true' : 'false'">
        <li
          v-for="(pl, index) in items"
          :key="pl.id"
          class="pm-row"
          :data-id="pl.id"
          :data-index="index"
        >
          <button
            class="pm-handle"
            type="button"
            :aria-label="`拖动调整「${pl.name}」的顺序，当前第 ${index + 1} 位`"
            @pointerdown="onDragStart($event, index)"
            @keydown="onHandleKeydown($event, index)"
          >
            <ReorderTwoOutline />
          </button>

          <span class="pm-index">{{ index + 1 }}</span>
          <span class="pm-name">{{ pl.name }}</span>
          <span class="pm-count">{{ pl.song_count }} 首</span>

          <span class="pm-actions">
            <n-button size="tiny" quaternary @click="openRename(pl)">
              <template #icon><n-icon><PencilOutline /></n-icon></template>
              重命名
            </n-button>
            <n-popconfirm @positive-click="remove(pl)">
              <template #trigger>
                <n-button size="tiny" quaternary type="error">
                  <template #icon><n-icon><TrashOutline /></n-icon></template>
                  删除
                </n-button>
              </template>
              删除歌单「{{ pl.name }}」？歌单内的歌曲不会从曲库删除。
            </n-popconfirm>
          </span>
        </li>
      </ul>
    </n-card>

    <n-modal
      v-model:show="editorOpen"
      preset="dialog"
      :title="editorMode === 'create' ? '新建歌单' : '重命名歌单'"
      positive-text="保存"
      negative-text="取消"
      :loading="saving"
      @positive-click="submitEditor"
    >
      <n-input
        v-model:value="editorName"
        placeholder="歌单名称"
        maxlength="255"
        show-count
        @keydown.enter="submitEditor"
      />
    </n-modal>
  </div>
</template>

<script setup>
/**
 * 管理歌单：排序（拖拽 + Alt+方向键）、重命名、删除、新建。
 *
 * 排序位由后端 `playlists.sort_order` 承载；侧边栏「歌单」子菜单与播放器歌单区
 * 都读同一个 playlists store，所以这里落库后直接 `apply()` 回写缓存，
 * 侧边栏立刻就是新顺序 —— 不需要通知谁刷新。
 */
import { computed, nextTick, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { CreateOutline, PencilOutline, ReorderTwoOutline, TrashOutline } from '@vicons/ionicons5'
import {
  createPlaylist,
  deletePlaylist,
  reorderPlaylists,
  updatePlaylist,
} from '@/api/music'
import { usePlaylistsStore } from '@/stores/playlists'

const message = useMessage()
const store = usePlaylistsStore()
const items = computed(() => store.items)
const loading = computed(() => store.loading)

const listEl = ref(null)
const saving = ref(false)
/** 拖动中：给列表挂 data-dragging，用来临时禁掉文本选择 */
const dragging = ref(false)
const editorOpen = ref(false)
const editorMode = ref('create')
const editorName = ref('')
let editingId = null

store.refresh().catch(() => message.error('歌单加载失败'))

/* ── 新建 / 重命名 ─────────────────────────────────────────── */

function openCreate() {
  editorMode.value = 'create'
  editingId = null
  editorName.value = ''
  editorOpen.value = true
}

function openRename(pl) {
  editorMode.value = 'rename'
  editingId = pl.id
  editorName.value = pl.name
  editorOpen.value = true
}

async function submitEditor() {
  const name = editorName.value.trim()
  if (!name) {
    message.warning('歌单名称不能为空')
    return false
  }
  saving.value = true
  try {
    if (editorMode.value === 'create') {
      await createPlaylist({ name })
      message.success('已新建歌单')
    } else {
      await updatePlaylist(editingId, { name })
      message.success('已重命名')
    }
    await store.refresh()
    editorOpen.value = false
    return true
  } catch (err) {
    message.error(err?.response?.data?.detail || '保存失败')
    return false
  } finally {
    saving.value = false
  }
}

async function remove(pl) {
  try {
    await deletePlaylist(pl.id)
    await store.refresh()
    message.success(`已删除「${pl.name}」`)
  } catch (err) {
    message.error(err?.response?.data?.detail || '删除失败')
  }
}

/* ── 拖拽排序 ─────────────────────────────────────────────── */

let drag = null

/** 记录所有行的当前视觉位置，数组重排后据此做 FLIP */
function captureRects() {
  const map = new Map()
  listEl.value?.querySelectorAll('.pm-row').forEach((row) => {
    map.set(Number(row.dataset.id), row.getBoundingClientRect().top)
  })
  return map
}

/** 重排后把除被拖行以外的行从旧位置动画到新位置 */
function flipFrom(previous) {
  nextTick(() => {
    listEl.value?.querySelectorAll('.pm-row').forEach((row) => {
      const id = Number(row.dataset.id)
      const before = previous.get(id)
      if (before == null || id === drag?.id) return
      const after = row.getBoundingClientRect().top
      const delta = before - after
      if (Math.abs(delta) < 0.5) return
      row.animate(
        [{ transform: `translateY(${delta}px)` }, { transform: 'translateY(0)' }],
        { duration: 180, easing: 'cubic-bezier(.32,.72,0,1)' },
      )
    })
  })
}

function rowHeight() {
  const row = listEl.value?.querySelector('.pm-row')
  return row ? row.getBoundingClientRect().height + 6 : 0 // +6 = 行间距
}

function onDragStart(event, index) {
  // 只响应主键/触摸
  if (event.button != null && event.button !== 0) return
  const row = event.currentTarget.closest('.pm-row')
  if (!row) return
  event.preventDefault()
  drag = {
    id: items.value[index].id,
    index,
    grabDy: event.clientY - row.getBoundingClientRect().top,
    row,
  }
  row.style.zIndex = '2'
  row.style.transform = 'translateY(0px)'
  dragging.value = true
  window.addEventListener('pointermove', onDragMove)
  window.addEventListener('pointerup', onDragEnd, { once: true })
  window.addEventListener('pointercancel', onDragEnd, { once: true })
}

function onDragMove(event) {
  if (!drag) return
  const row = drag.row
  // 先清掉 transform 再量布局位置：getBoundingClientRect 会把已有 transform 算进去，
  // 直接量会形成自我叠加、行会越飘越远
  row.style.transform = 'translateY(0px)'
  const layoutTop = row.getBoundingClientRect().top
  row.style.transform = `translateY(${event.clientY - drag.grabDy - layoutTop}px)`

  const list = listEl.value
  if (!list) return
  const h = rowHeight()
  if (!h) return
  const offset = event.clientY - drag.grabDy - list.getBoundingClientRect().top
  const target = Math.max(0, Math.min(items.value.length - 1, Math.round(offset / h)))
  if (target === drag.index) return

  const previous = captureRects()
  const next = items.value.slice()
  const [moved] = next.splice(drag.index, 1)
  next.splice(target, 0, moved)
  store.apply(next)
  drag.index = target
  flipFrom(previous)
}

async function onDragEnd() {
  window.removeEventListener('pointermove', onDragMove)
  const current = drag
  drag = null
  if (!current) return
  current.row.style.transform = ''
  current.row.style.zIndex = ''
  dragging.value = false
  await persistOrder()
}

/** 把当前顺序落库。后端返回排好的完整列表，直接回写缓存（侧边栏同步更新） */
async function persistOrder() {
  try {
    const res = await reorderPlaylists(items.value.map((pl) => pl.id))
    store.apply(res.data)
  } catch (err) {
    message.error('顺序保存失败，正在恢复')
    await store.refresh().catch(() => {})
  }
}

/** 键盘增强：手柄聚焦后 Alt+↑/↓ 换位 */
async function onHandleKeydown(event, index) {
  if (!event.altKey) return
  const delta = event.key === 'ArrowUp' ? -1 : event.key === 'ArrowDown' ? 1 : 0
  if (!delta) return
  const target = index + delta
  if (target < 0 || target >= items.value.length) return
  event.preventDefault()
  const next = items.value.slice()
  const [moved] = next.splice(index, 1)
  next.splice(target, 0, moved)
  store.apply(next)
  await nextTick()
  // 焦点跟着走，否则连续按第二次会作用到别行
  listEl.value?.querySelectorAll('.pm-handle')[target]?.focus()
  await persistOrder()
}
</script>

<style scoped>
.pm {
  max-width: 760px;
}

.pm-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-space-4);
}
.pm-title {
  font-size: var(--sp-fs-h3);
  font-weight: var(--sp-fw-bold);
}
.pm-hint {
  margin-top: 4px;
  color: var(--sp-ui-text-3);
  font-size: var(--sp-fs-caption);
  line-height: 1.6;
}
.pm-hint kbd {
  padding: 0 4px;
  border: 1px solid var(--sp-ui-border);
  border-radius: var(--sp-radius-xs);
  background: var(--sp-ui-body);
  font-family: var(--sp-font-mono);
  font-size: var(--sp-fs-micro);
}

.pm-empty {
  padding: var(--sp-space-6) 0;
}

.pm-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.pm-row {
  display: flex;
  align-items: center;
  gap: var(--sp-space-2);
  min-height: 44px;
  padding: 0 var(--sp-space-3) 0 var(--sp-space-1);
  border: 1px solid var(--sp-ui-border);
  border-radius: var(--sp-radius-md);
  background: var(--sp-ui-card);
  transition: box-shadow var(--sp-dur-fast) var(--sp-ease-enter), border-color var(--sp-dur-fast) var(--sp-ease-enter);
}
.pm-list[data-dragging='true'] .pm-row {
  /* 拖动中禁掉文本选择，否则会一路选中整页 */
  user-select: none;
}
.pm-row:hover {
  border-color: var(--sp-ui-text-3);
}

.pm-handle {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  flex: 0 0 auto;
  border: 0;
  border-radius: var(--sp-radius-xs);
  background: none;
  color: var(--sp-ui-text-3);
  cursor: grab;
  /* 触屏拖动时不要让浏览器把纵向手势吃掉当成滚动 */
  touch-action: none;
  -webkit-tap-highlight-color: transparent;
}
.pm-handle:hover {
  color: var(--sp-ui-text-1);
  background: var(--sp-ui-hover);
}
.pm-handle:active {
  cursor: grabbing;
}
.pm-handle :deep(svg) {
  width: var(--sp-icon-md);
  height: var(--sp-icon-md);
  display: block;
}

.pm-index {
  flex: 0 0 auto;
  width: 20px;
  color: var(--sp-ui-text-3);
  font-size: var(--sp-fs-caption);
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.pm-name {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: var(--sp-fw-medium);
}

.pm-count {
  flex: 0 0 auto;
  color: var(--sp-ui-text-3);
  font-size: var(--sp-fs-caption);
  font-variant-numeric: tabular-nums;
}

.pm-actions {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: var(--sp-space-1);
}

@media (max-width: 768px) {
  .pm-head {
    flex-direction: column;
    align-items: stretch;
  }
  .pm-count {
    display: none;
  }
  .pm-row {
    padding-right: var(--sp-space-2);
  }
}
</style>
