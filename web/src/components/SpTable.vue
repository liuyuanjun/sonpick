<template>
  <n-data-table v-bind="$attrs">
    <!-- 透传除 empty 之外的全部插槽，包装层对调用方完全透明 -->
    <template v-for="name in forwardedSlots" :key="name" #[name]="slotProps">
      <slot :name="name" v-bind="slotProps || {}" />
    </template>

    <!--
      统一空白态。
      Naive 的 DataTable 在无数据时内部渲染 <n-empty>，其 description 默认值是英文
      「No Data」——这是全站唯一的英文文案来源（实测曲库页、下载页均命中）。
      DataTable 的 description 是组件 prop 而非主题项，无法从 themeOverrides 收口，
      因此必须由本包装层兜住 #empty 插槽。调用方仍可传 #empty 覆盖。
    -->
    <template #empty>
      <slot name="empty">
        <state-empty :title="emptyTitle" :description="emptyDescription" size="compact" />
      </slot>
    </template>
  </n-data-table>
</template>

<script setup>
import { computed, useSlots } from 'vue'
import StateEmpty from '@/components/StateEmpty.vue'

/**
 * 全站表格统一入口。新表格一律用 <sp-table>，不要直接用 <n-data-table>，
 * 否则会漏掉空白态的中文化与统一化。
 *
 * 用法与 n-data-table 完全一致（所有 props / 事件 / 插槽原样透传），
 * 额外支持两个可选属性：
 *   empty-title        空白态标题，默认「暂无数据」
 *   empty-description  空白态说明
 */
defineOptions({ inheritAttrs: false })

defineProps({
  emptyTitle: { type: String, default: '暂无数据' },
  emptyDescription: { type: String, default: '' },
})

const slots = useSlots()
const forwardedSlots = computed(() => Object.keys(slots).filter((name) => name !== 'empty'))
</script>
