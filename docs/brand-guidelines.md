# Sonpick 拾音 · 品牌视觉系统 v1.0

> 一切面向 web/public/brand/。本文档是开发者/设计协作的唯一来源。
> 设计稿：见 Ardot 文件《Sonpick 拾音 · 品牌视觉系统》(fileId `723344971328404`)。

## 1. 母题与 LOGO

### 意象：唱片 · 唱针 · 叶片（三重合一）

一枚音符斜搭在**同心圆唱片**上 —— 音符同时是**唱针**，伸出唱片外的那一段是**叶柄**。
"拾音"（针拾声）与"拾起一片叶子做书签"（珍藏）在同一个动作里完成：

- **外圆 r=16.5** = 唱片外缘
- **内圆 r=8.5** = 唱片中心标签，与外圆**同心**（半径比约 1.94:1，接近真实唱片观感）
- **音符** = 唱针 / 叶片；符头在唱片内，符干**伸出外圆之外**形成叶柄

### 缺口逻辑（不是装饰，是叙事）

两个圆的缺口都开在**正上方（对准符干顶端）**。符干顶端是声源，声波从那里向外冲、把同心圆顶开 —— 所以外圈缺口 60° 比内圈 50° 更宽，呈**扇形辐射**，这才是"脉络"。

> ⚠️ 缺口位置不可随意改动；改了就变成"为了缺口而缺口"。

### 构造参数（48 × 48 网格）

| 元素 | 参数 |
|------|------|
| 画布 | 48 × 48，外框圆角 14 |
| 外圆 | 圆心 (24,24)，r=16.5，线宽 2，缺口 240°~300° |
| 内圆 | 圆心 (24,24)，r=8.5，线宽 1.5，缺口 245°~295° |
| 符头 | 椭圆 cx=21.5 cy=25，rx=4 ry=3.2，旋转 -30° |
| 符干 | x=24，y 23 → 5（顶端伸出外圆 2.5） |
| 符旗 | `M 24 5 C 28.5 7, 29.5 11, 26 14`，线宽 2.5 |
| 弧线写法 | `M <终点角点> A r r 0 1 1 <起点角点>`（大弧 + 顺时针绕开缺口），端点 `stroke-linecap="round"` |

**悬浮原则：圆与音符互不接触。** 符头在内圈内悬浮（间隙 ≈1.8），符干走两处缺口**正中央**（两侧各留 ≈2.3），符旗落在内圈外、外圈内。

### 资产与用法

| 文件 | 用途 |
|------|------|
| `web/public/brand/logo.svg` | 首选用法，深底 + 渐变线条 |
| `web/public/brand/logo-mono-white.svg` | 反白版：透明底 + 纯白线条，用于深色背景 |
| `web/public/brand/logo-mono-black.svg` | 纯黑版：透明底 + 深墨线条，用于浅色背景 |
| `web/public/brand/logo-mark-sm.svg` | 简化版（去内圆与符旗、加粗），≤32px 用 |
| `web/public/brand/favicon.svg` | favicon，进一步加粗、圆角 10 |

### 禁用

- 拉伸变形 / 旋转 / 加描边投影 / 改渐变方向
- 随意改动缺口位置或大小（见上文缺口逻辑）
- 让音符与圆接触 —— 悬浮间隙是造型的一部分
- 16px 以下仍使用完整版（应切到 logo-mark-sm / favicon）
- 品牌渐变禁止铺大面积背景

## 2. 色彩

| 角色 | 变量 | Hex |
|------|------|-----|
| 主色 500 | `--sp-primary-500` | #10B981 |
| 辅色 500 | `--sp-accent-500` | #6366F1 |
| 底 | `--sp-bg` | #0B0C10 |
| 面 | `--sp-surface` | #14161C |
| 描边 | `--sp-border` | #23262F |
| 主文字 | `--sp-text` | #ECEEF2 |
| 次文字 | `--sp-text-2` | #8B95A5 |
| 警告 | `--sp-warning` | #F59E0B |
| 错误 | `--sp-error` | #EF4444 |
| 成功 | `--sp-success` | #10B981 |
| 信息 | `--sp-info` | #6366F1 |

**品牌渐变**：`linear-gradient(135deg, #34D399 0%, #6366F1 100%)`。仅用于 logo、焦点态、强调条。详见 `brand.css`。

## 3. 字体

- 西文：`Inter`（Bold / SemiBold / Medium / Regular）
- 中文：`Noto Sans SC`（Bold / Medium / Regular）

CSS：`--sp-font-en`、`--sp-font-cn`。

## 4. 图标系统

- 网格 24×24，2px 线宽，圆头圆角
- `stroke="currentColor"`，**前端通过 CSS `color` 控制颜色**
- 详见 `web/public/brand/icons/` 21 个 SVG

| 文件 | 含义 |
|------|------|
| search.svg | 搜索 |
| download.svg | 下载 |
| library.svg | 曲库 |
| play.svg | 播放 |
| webdav.svg | WebDAV |
| convert.svg | 转码 |
| logs.svg | 日志 |
| settings.svg | 设置 |
| tasks.svg | 任务中心 |
| upload.svg | 上传 |
| delete.svg | 删除 |
| lyrics.svg | 歌词 |
| metadata.svg | 刮削元数据 |
| favorite.svg | 收藏 |
| shuffle.svg | 随机 |
| scan.svg | 扫描 |
| refresh.svg | 刷新 |
| quality.svg | 音质（声波线） |
| user.svg | 用户 |
| theme.svg | 主题 |

### 引入示例（Vue）

```vue
<template>
  <button class="icon-btn">
    <img :src="iconUrl" alt="搜索" width="20" height="20" />
  </button>
</template>

<style scoped>
.icon-btn { color: var(--sp-primary-500); }
</style>
```

## 5. 吉祥物 · 拾耳（Shier）

戴耳机的大耳狐。暖橙 #F5A45D 主色，奶白 #F7F1E8 辅助，深墨 #2B2118 五官；耳机为品牌色（青绿头梁 + 蓝紫耳罩）。头身比 1:1.2，耳高 ≈ 头高 0.9。

资产：

- `web/public/brand/mascot/mascot-main.png` — 标准形象
- `web/public/brand/mascot/mascot-expressions.png` — 4 表情组（听歌 / 开心 / 惊讶 / 找不到歌）
- `web/public/brand/mascot/mascot-scenes.png` — 3 场景（空曲库 / 加载中 / 出错）

使用建议：空状态、加载动画、错误页、引导页。统一 2:1 横构图，四周留 8% 呼吸区。

## 6. 集成步骤

1. `web/index.html` 引入 `<link rel="icon" type="image/svg+xml" href="/brand/favicon.svg">`
2. 全局引入 `import './brand/brand.css'`（或 main.js）
3. 主题色保留 Naive UI 的 `--n-primary-color`，或迁移到 `--sp-primary-500`
4. 现有 280px 顶栏 logo 字符（`#18a058` n-icon）可考虑替换为 `/brand/logo.svg`
