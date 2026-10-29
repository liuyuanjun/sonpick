<template>
  <!--
    音量图标（自绘，三态共用同一个扬声器轮廓）
    ──────────────────────────────────────────────────────────────
    为什么不用 @vicons/tabler 的 Volume / Volume2 / Volume3：
    实测三者的墨迹包围盒分别是 18×15.9、14×15.9、17×15.9，且 Volume2 的中心偏左 2 个单位，
    Volume3 的右侧其实是「小叉」（Tabler 里那是静音语义，不是低音量）——
    结果是同一枚音量键在 0.8 / 0.6 / 0.2 三档下**忽大忽小，且低音量看起来像静音**。
    换库也不行：Lucide 的 volume-2 墨高 16、repeat 墨高 20，同样差 20%，volume-1 同样偏左。

    这里改成「一个轮廓 + 右侧波形增减」：扬声器路径沿用 Tabler 的几何（经过验证的形状），
    整组统一放大 1.14 倍，使墨高从 15.9 拉到 18.1，与循环 / 闪电（18）一档；
    三态因此**在构造上就同高**，切换只增减波形，不改变主体尺寸。

    stroke-width / linecap 保持 tabler 的写法，全局线宽规则（base.css 把 2 提到 2.25）同样生效。
  -->
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <g transform="translate(12 12) scale(1.14) translate(-12 -12)">
      <path d="M6 15H4a1 1 0 0 1-1-1v-4a1 1 0 0 1 1-1h2l3.5-4.5A.8.8 0 0 1 11 5v14a.8.8 0 0 1-1.5.5L6 15" />
      <!-- 静音：叉的跨度对齐外侧那道波（不是缩成一个小记号） -->
      <path v-if="state === 'muted'" d="M15.4 9.2l5.4 5.4M20.8 9.2l-5.4 5.4" />
      <template v-else>
        <!-- 低：1 道波 -->
        <path d="M15 8a5 5 0 0 1 0 8" />
        <!-- 高：再加外侧那道波 -->
        <path v-if="state === 'high'" d="M17.7 5a9 9 0 0 1 0 14" />
      </template>
    </g>
  </svg>
</template>

<script setup>
// · state: 'muted' | 'low' | 'high'
// · 视觉尺寸由使用方的 n-icon 字号决定（播放器壳里是 20px 档），本组件不再接收 size。
defineProps({
  state: { type: String, default: 'high' },
})
</script>
