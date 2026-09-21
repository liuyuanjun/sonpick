<template>
  <div class="source-picker">
    <div class="area-label">
      下载来源<span class="area-hint">实色为已选（按顺序优先，可拖拽或点 ‹ › 调整），虚线为待选（点击追加）</span>
    </div>
    <div class="chips">
      <span
        v-for="(value, i) in modelValue"
        :key="value"
        class="chip selected"
        draggable="true"
        :class="{ dragging: dragIndex === i, 'drag-over': dragOverIndex === i && dragIndex !== i }"
        @dragstart="onDragStart(i, $event)"
        @dragend="onDragEnd"
        @dragover.prevent="dragOverIndex = i"
        @dragleave="dragOverIndex === i && (dragOverIndex = -1)"
        @drop.prevent="onDrop(i)"
      >
        <button type="button" class="chip-btn move" :disabled="i === 0" title="前移" @click="move(i, -1)">‹</button>
        <span class="chip-label">{{ labelOf(value) }}</span>
        <button type="button" class="chip-btn move" :disabled="i === modelValue.length - 1" title="后移" @click="move(i, 1)">›</button>
        <button type="button" class="chip-btn remove" title="移除" @click="removeAt(i)">×</button>
      </span>
      <button
        v-for="opt in candidates"
        :key="opt.value"
        type="button"
        class="chip candidate"
        :title="`添加 ${opt.label}`"
        @click="add(opt.value)"
      >
        <span class="plus">+</span> {{ opt.label }}
      </button>
    </div>
    <div v-if="!modelValue.length" class="empty-tip">未选择来源 —— 点击上方来源添加</div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  // 有序已选源 value 列表，顺序即优先级
  modelValue: { type: Array, required: true },
  // 全部可选源 [{ value, label }]
  options: { type: Array, required: true },
})
const emit = defineEmits(['update:modelValue'])

const candidates = computed(() => props.options.filter((o) => !props.modelValue.includes(o.value)))

function labelOf(value) {
  return props.options.find((o) => o.value === value)?.label || value
}

function update(next) {
  emit('update:modelValue', next)
}

function add(value) {
  update([...props.modelValue, value])
}

function removeAt(i) {
  const next = props.modelValue.slice()
  next.splice(i, 1)
  update(next)
}

function move(i, dir) {
  const j = i + dir
  if (j < 0 || j >= props.modelValue.length) return
  const next = props.modelValue.slice()
  ;[next[i], next[j]] = [next[j], next[i]]
  update(next)
}

// 桌面端拖拽排序（移动端用 ‹ › 按钮，HTML5 drag 触屏不生效）
const dragIndex = ref(-1)
const dragOverIndex = ref(-1)

function onDragStart(i, ev) {
  dragIndex.value = i
  ev.dataTransfer?.setData('text/plain', String(i))
  if (ev.dataTransfer) ev.dataTransfer.effectAllowed = 'move'
}

function onDragEnd() {
  dragIndex.value = -1
  dragOverIndex.value = -1
}

function onDrop(i) {
  const from = dragIndex.value
  onDragEnd()
  if (from < 0 || from === i) return
  const next = props.modelValue.slice()
  const [item] = next.splice(from, 1)
  next.splice(i, 0, item)
  update(next)
}
</script>

<style scoped>
.area-label {
  font-size: 12px;
  color: var(--sp-ui-text-2);
  margin-bottom: 6px;
}
.area-hint {
  margin-left: 8px;
  color: var(--sp-ui-text-3);
  font-size: 11px;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 12.5px;
  line-height: 1.6;
  border: 1px solid var(--sp-ui-border);
  background: var(--sp-ui-card);
  color: var(--sp-ui-text-1);
}
.chip.selected {
  cursor: grab;
  border-color: color-mix(in srgb, var(--sp-ui-primary) 45%, var(--sp-ui-border));
  background: color-mix(in srgb, var(--sp-ui-primary) 10%, var(--sp-ui-card));
}
.chip.selected.dragging {
  opacity: 0.45;
}
.chip.selected.drag-over {
  border-color: var(--sp-ui-primary);
  box-shadow: 0 0 0 1px var(--sp-ui-primary);
}
.chip.candidate {
  cursor: pointer;
  color: var(--sp-ui-text-2);
  background: transparent;
  border-style: dashed;
}
.chip.candidate:hover {
  color: var(--sp-ui-primary);
  border-color: var(--sp-ui-primary);
}
.chip .plus {
  font-weight: 600;
}
.chip-label {
  padding: 0 2px;
  user-select: none;
}
.chip-btn {
  border: none;
  background: transparent;
  color: var(--sp-ui-text-3);
  cursor: pointer;
  padding: 0 3px;
  font-size: 13px;
  line-height: 1.4;
  border-radius: 4px;
}
.chip-btn:hover:not(:disabled) {
  color: var(--sp-ui-primary);
}
.chip-btn:disabled {
  opacity: 0.3;
  cursor: default;
}
.chip-btn.remove:hover {
  color: var(--sp-ui-error);
}
.empty-tip {
  margin-top: 6px;
  font-size: 12px;
  color: var(--sp-ui-warning);
}
</style>
