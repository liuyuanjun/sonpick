<template>
  <!--
    静音图标：@vicons/tabler 0.13 没有 volume-off（全集只有 Volume/Volume2/Volume3）。
    几何沿用 tabler 的扬声器画法 + 右侧 ×，stroke 属性与 tabler 一致，
    全局线宽规则（base.css 的 svg[stroke-width="2"] 提到 2.25）对它同样生效。
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
    <path d="M15 8a5 5 0 0 1 1.06 4.94" />
    <path d="M17.7 5a9 9 0 0 1 .62 11.86" />
    <path d="M6 15h-2a1 1 0 0 1 -1 -1v-4a1 1 0 0 1 1 -1h2l3.5 -4.5a.8 .8 0 0 1 1.5 .5v6" />
    <path d="M11 15.6v3.4a.8 .8 0 0 1 -1.5 .5l-3.5 -4.5" />
    <path d="M16 16l5 5" />
    <path d="M21 16l-5 5" />
  </svg>
</template>
