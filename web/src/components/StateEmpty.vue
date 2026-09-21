<template>
  <div class="state-empty" :class="`state-empty--${size}`">
    <div class="se-art" aria-hidden="true">
      <slot name="illustration">
        <!--
          默认插画：声波弧线（「乐海拾音」母题），全部用 Token 上色，明暗双模自动跟随。
          槽位预留给吉祥物场景图：待 mascot-scenes.png 以「透明底 + 单张独立」重新导出后，
          在这里传入 <img> 即可替换，无需改动任何调用方。
        -->
        <svg class="se-art-svg" viewBox="0 0 96 96" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect x="6" y="6" width="84" height="84" rx="22" fill="var(--sp-ui-primary-soft)" />
          <path
            d="M28 62a20 20 0 0 1 40 0"
            stroke="var(--sp-ui-primary)"
            stroke-width="3"
            stroke-linecap="round"
            opacity="0.4"
          />
          <path
            d="M37 62a11 11 0 0 1 22 0"
            stroke="var(--sp-ui-primary)"
            stroke-width="3"
            stroke-linecap="round"
            opacity="0.72"
          />
          <circle cx="48" cy="62" r="4.5" fill="var(--sp-ui-primary)" />
        </svg>
      </slot>
    </div>

    <p class="se-title">{{ title }}</p>
    <p v-if="description" class="se-desc">{{ description }}</p>

    <div v-if="actionText || $slots.action" class="se-action">
      <slot name="action">
        <n-button type="primary" @click="emit('action')">{{ actionText }}</n-button>
      </slot>
    </div>
  </div>
</template>

<script setup>
/**
 * 统一空状态。
 *
 * 全站空状态只有这一个实现，三档尺度：
 *   page    —— 整页/整块内容区为空（曲库空、搜索结果空）
 *   block   —— 卡片或面板内部（表格无数据）
 *   compact —— 下拉、队列、任务中心等紧凑容器
 *
 * 规范（DESIGN.md §4 状态设计）：空状态 = 插画 + 一句话说明 + 一个主操作。
 * 禁止只放一个图标了事，禁止使用英文文案。
 */
defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  actionText: { type: String, default: '' },
  size: {
    type: String,
    default: 'block',
    validator: (v) => ['page', 'block', 'compact'].includes(v),
  },
})

const emit = defineEmits(['action'])
</script>

<style scoped>
.state-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: var(--sp-space-2);
  padding: var(--sp-space-6) var(--sp-space-4);
}

.state-empty--page {
  padding: var(--sp-space-10) var(--sp-space-4);
}

.state-empty--compact {
  gap: var(--sp-space-1);
  padding: var(--sp-space-3) var(--sp-space-2);
}

.se-art {
  display: flex;
  align-items: center;
  justify-content: center;
}

.se-art-svg {
  width: 88px;
  height: 88px;
  display: block;
}

.state-empty--compact .se-art-svg {
  width: 48px;
  height: 48px;
}

.se-title {
  margin: 0;
  font-size: var(--sp-fs-strong);
  font-weight: var(--sp-fw-semibold);
  line-height: 1.5;
  color: var(--sp-ui-text-1);
}

.state-empty--compact .se-title {
  font-size: var(--sp-fs-small);
  font-weight: var(--sp-fw-regular);
  color: var(--sp-ui-text-2);
}

.se-desc {
  margin: 0;
  max-width: 34em;
  font-size: var(--sp-fs-small);
  line-height: 1.55;
  color: var(--sp-ui-text-3);
}

.state-empty--compact .se-desc {
  font-size: var(--sp-fs-caption);
}

.se-action {
  margin-top: var(--sp-space-1);
}
</style>
