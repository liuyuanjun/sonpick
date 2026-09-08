# Sonpick 拾音 · 品牌视觉系统 v1.0

> 一切面向 web/public/brand/。本文档是开发者/设计协作的唯一来源。
> 设计稿：见 Ardot 文件《Sonpick 拾音 · 品牌视觉系统》(fileId `723344971328404`)。

## 1. 母题与 LOGO

### 意象：乐海 · 声波 · 拾音

圆角方形深底上，**两圈同向的同心声波弧线**向外扩散，中央悬浮一枚**八分音符**——
声音从中心荡开，而你在声海中把它拾起。呼应 Slogan「**乐海拾音，好歌不散**」。

- **深色底**：圆角方形，近黑（`#0E0E16`），与产品主题一致
- **双弧线**：同心、同向，左下开口，圆头端（`stroke-linecap="round"` 观感）
- **八分音符**：椭圆符头 + 符干 + S 形符旗，居中悬浮
- **渐变**：亮绿 → 青 → 蓝 → 紫，沿左上到右下方向过渡

> 取样色值（用于邻近配色参照，非重绘依据）：`#64F0AC` → `#22D3EE` → `#556FE1` → `#7A40DC`

### 资产形态：位图（非矢量）

LOGO 源自位图源图，**不再是参数化矢量**。历史上曾尝试手绘 SVG 复刻，两版均无法还原
源图质感（色相、造型都失真），故改为直接从源图导出多尺寸 PNG。

> ⚠️ **禁止对 LOGO 做矢量化重绘或手绘 SVG 复刻。** 需要新尺寸时，从源图重新导出，
> 不要描摹。仅几何构成简单、原生矢量的图形才适合手绘 SVG。

### 资产与用法

| 文件 | 尺寸 | 用途 |
|------|------|------|
| `web/public/brand/logo.png` | 512×512 | 首选用法；登录页主图、`apple-touch-icon` |
| `web/public/brand/logo-mark-sm.png` | 128×128 | 小尺寸（侧栏、列表、≤32px 场景） |
| `web/public/brand/favicon.png` | 64×64 | favicon 默认（高 DPI） |
| `web/public/brand/favicon-32.png` | 32×32 | favicon 标准 |
| `web/public/brand/favicon-16.png` | 16×16 | favicon 小尺寸回退 |

`web/index.html` 按 `sizes` 声明三个 favicon，浏览器自动择优；`LoginView.vue` 引用 `logo.png`。

### 禁用

- 拉伸变形 / 旋转 / 加描边投影 / 改渐变方向 / 重新着色
- **矢量化重绘或手绘 SVG 复刻**（见上文）
- 用 CSS `filter` 改变品牌色相
- 16px 以下仍使用 `logo.png` 大图（应切到 `favicon-16.png`）
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

1. `web/index.html` 按尺寸引入三档 favicon：
   ```html
   <link rel="icon" type="image/png" sizes="64x64" href="/brand/favicon.png" />
   <link rel="icon" type="image/png" sizes="32x32" href="/brand/favicon-32.png" />
   <link rel="icon" type="image/png" sizes="16x16" href="/brand/favicon-16.png" />
   <link rel="apple-touch-icon" href="/brand/logo.png" />
   ```
2. 全局引入 `import './brand/brand.css'`（或 main.js）
3. 主题色保留 Naive UI 的 `--n-primary-color`，或迁移到 `--sp-primary-500`
4. 现有 280px 顶栏 logo 字符（`#18a058` n-icon）可考虑替换为 `/brand/logo.png`
5. 登录页 Slogan 固定为「乐海拾音，好歌不散」（`LoginView.vue` 的 `.brand-slogan`）
