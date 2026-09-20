# Sonpick 拾音 · 设计系统 DESIGN.md

> 本文件是 Sonpick 拾音前端设计的**唯一权威规范**。一切颜色、字号、间距、阴影、组件样式只允许从本文件的 Token 派生，禁止在组件里写死数值。
> 第 1–9 章为**目标设计系统**（应收敛到的形态）；第 10 章为**现状审计与改造建议**（当前实现与目标之间的差距与落地路径）。
> 颜色单一真相源 = `web/src/theme/tokens.js`（运行时注入 `:root`）；品牌渐变、吉祥物色与字体变量由 `web/public/brand/brand.css` 承载。两处必须保持同步。

> **本文取证口径（客观性声明）**：文中带「✅ 代码事实」标记的值直接来自现有实现（`tokens.js` / `brand.css` / 组件），可直接采用；带「🔷 建议」标记的是本次**新提出**、代码里尚不存在或与代码不一致的目标值（如字号/间距/阴影/渐变停靠点），**需评审后再落地**，不要当成既成事实。

---

## 1. Visual Theme & Atmosphere（视觉主题与氛围）

- **设计哲学**：个人 NAS 音乐库，沉静、专注、有温度。以「乐海拾音」为母题——声音从中心荡开，你在声海里把它拾起。暗色为默认底色（影音场景护眼），明亮模式为可达性补充而非次级体验。
- **视觉基调**：深邃、冷静、克制中带一抹渐变高光。不追求炫技，强调信息密度与可读性。
- **核心视觉特征**：① 近黑底 + 玻璃质感卡片；② 品牌四色渐变（绿→青→蓝→紫）仅做焦点/强调点缀；③ 圆角方形的品牌 LOGO 作为视觉锚；④ 暖橙吉祥物「拾耳」作为唯一的人文暖色，用于空状态与引导。
- **光影与质感**：以微妙的内/外投影与 `color-mix` 软底塑造层级；**禁止大面积铺渐变背景**（会破坏沉静感并冲淡内容）。
- **主题机制（✅ 代码事实）**：明暗由 `<html data-theme="dark|light">` + `:root` 上的 CSS 变量驱动（`stores/theme.js` 的 `buildCssVars` 注入 `--sp-ui-*` / `--sp-accent-*`）。因变量定义在 `documentElement`，被 teleport 到 `body` 的 Modal / Drawer / Popover 才取得到——**组件内浮层只允许引用 `:root` 变量**，不得引用挂载点局部变量。

---

## 2. Color Palette & Roles（调色板与角色）

> 主色/语义色/文字/描边随明暗模式切换；分类强调色与品牌渐变固定锚点。主文字须满足 **WCAG AA 4.5:1**，大字/图标 ≥ **3:1**。

### 2.1 核心 Token（随模式切换 · ✅ 代码事实，变量名以 `tokens.js` 为准）

| 角色 | 变量名 | Dark HEX | Light HEX | 使用场景 |
|------|--------|----------|-----------|----------|
| 页面底 | `--sp-ui-body` | #0B0C10 | #F5F6F8 | body / 页面背景 |
| 卡片面 | `--sp-ui-card` | #14161C | #FFFFFF | 卡片、列表行 |
| 强卡片面 | `--sp-ui-card-strong` | #181B22 | #FFFFFF | 需比 card 略强的面板（谨慎用，见下注） |
| 浮层/弹窗 | `--sp-ui-elevated` | #181B22 | #FFFFFF | Modal / Drawer / Popover |
| 描边 | `--sp-ui-border` | #23262F | #E3E6EB | 边框 |
| 分割线 | `--sp-ui-divider` | #23262F | #E8EAEF | 行内分隔 |
| 主文字 | `--sp-ui-text-1` | #ECEEF2 | #111827 | 标题、正文重点 |
| 次文字 | `--sp-ui-text-2` | #B6BECB | #4B5563 | 副信息 |
| 弱文字 | `--sp-ui-text-3` | #8B95A5 | #6B7280 | 辅助说明、占位 |
| 主色 | `--sp-ui-primary` | #10B981 | #047857 | 主按钮、激活态、链接 |
| 主色 hover | `--sp-ui-primary-hover` | #34D399 | #065F46 | 交互悬停 |
| 主色 pressed | `--sp-ui-primary-pressed` | #059669 | #044434 | 按压 |
| 主色反白 | `--sp-ui-on-primary` | #04120C | #FFFFFF | 主按钮上的文字 |
| 主色软底 | `--sp-ui-primary-soft` | rgba(16,185,129,.14) | rgba(4,120,87,.10) | 选中/高亮底 |
| 主色软底2 | `--sp-ui-primary-soft-2` | rgba(16,185,129,.22) | rgba(4,120,87,.16) | 强高亮底 |
| 悬停叠层 | `--sp-ui-hover` | rgba(255,255,255,.06) | rgba(15,23,42,.05) | 行/卡片 hover |
| 信息色 | `--sp-ui-info` | #6366F1 | #4F46E5 | 信息标签、WebDAV 标识 |
| 成功色 | `--sp-ui-success` | #10B981 | #047857 | 成功态 |
| 警告色 | `--sp-ui-warning` | #F59E0B | #B45309 | 警告、部分覆盖 |
| 错误色 | `--sp-ui-error` | #EF4444 | #DC2626 | 错误、失败态 |

> ⚠️ **表面层级避坑（✅ 代码事实）**：暗色下 `--sp-ui-elevated` / `--sp-ui-card-strong` 与页面底几乎同亮度（#181B22 vs #0B0C10），**不要拿它们做主要表面**，否则边界消失。`GlobalPlayer.vue` 有明确注释禁止改回；主表面一律用 `--sp-ui-card`。
> **Light 主色降级（✅ 代码事实）**：`#10B981` 配白字仅 2.65:1（不达标），故 Light 主色降到 700 阶 `#047857`。hover 继续加深而非提亮——交互态朝「远离页面底色」方向走。

### 2.2 分类强调色（KPI / 快捷入口 / 活动流按类别上色 · ✅ 代码事实）

| 类别 | 变量名 | Dark HEX | Light HEX | 软底变量 |
|------|--------|----------|-----------|----------|
| 青绿 | `--sp-accent-teal` | #2DD4BF | #0F766E | `--sp-accent-teal-soft` |
| 蓝 | `--sp-accent-blue` | #60A5FA | #1D4ED8 | `--sp-accent-blue-soft` |
| 玫红 | `--sp-accent-rose` | #FB7185 | #BE123C | `--sp-accent-rose-soft` |
| 琥珀 | `--sp-accent-amber` | #FBBF24 | #B45309 | `--sp-accent-amber-soft` |
| 天蓝 | `--sp-accent-sky` | #38BDF8 | #0369A1 | `--sp-accent-sky-soft` |
| 绿 | `--sp-accent-green` | #4ADE80 | #15803D | `--sp-accent-green-soft` |
| 石板 | `--sp-accent-slate` | #94A3B8 | #475569 | `--sp-accent-slate-soft` |

软底 = `color-mix(in srgb, <fg> <16%:dark / 12%:light>, transparent)`（✅ 代码事实）。

### 2.3 品牌渐变与吉祥物

| 角色 | 变量名 | 值 | 依据 |
|------|--------|----|------|
| 品牌渐变（仅 LOGO / 焦点态 / 强调条） | `--sp-brand-grad` | `linear-gradient(135deg, #64F0AC 0%, #22D3EE 38%, #556FE1 72%, #7A40DC 100%)` | 🔷 建议 |
| 吉祥物主色 | `--sp-fox` | #F5A45D | ✅ 代码事实 |
| 吉祥物奶白 | `--sp-fox-cream` | #F7F1E8 | ✅ 代码事实 |
| 吉祥物深墨 | `--sp-fox-ink` | #2B2118 | ✅ 代码事实 |

> 🔷 **四色停靠点（0/38/72/100%）为本次提案**。brand-guidelines 只给出沿渐变的**取样色**（`#64F0AC → #22D3EE → #556FE1 → #7A40DC`）而非精确停靠点，落地时须以 LOGO 源图为准重新取样。禁止改用两色简化版。
> **字体变量（✅ 代码事实）**：`--sp-font-en: "Inter","PingFang SC","Microsoft YaHei",system-ui,sans-serif`；`--sp-font-cn: "Noto Sans SC","PingFang SC","Microsoft YaHei",system-ui,sans-serif`（定义在 `brand.css`）。

---

## 3. Typography Rules（排版规则）

- **字体族**：西文 `Inter`；中文 `Noto Sans SC`。**必须实际加载**（见 §10-P1-2），不可仅写在 font-family 里。
- **字重纪律**：只允许 **400 / 500 / 600 / 700 / 800**。禁止 650/720/760/780 等中间值。

### Type Scale（🔷 建议：为归一化提案，代码当前为散值）

| 层级 | 字号 | 字重 | 行高 | 字距 | 用途 |
|------|------|------|------|------|------|
| Display | 32px | 800 | 1.15 | -0.01em | 登录品牌名、空状态大标题 |
| H1 | 28px | 700 | 1.20 | -0.01em | 概览 Hero 标题 |
| H2 | 22px | 700 | 1.25 | 0 | 区块大标题 |
| H3 / Panel | 16px | 700 | 1.30 | 0 | 面板标题 |
| Body | 14px | 400 | 1.60 | 0 | 正文默认 |
| Body Strong | 14px | 600 | 1.60 | 0 | 列表项重点 |
| Small | 13px | 400 | 1.50 | 0 | 副标题、说明 |
| Caption | 12px | 500 | 1.40 | 0.02em | 标签、元信息、KPI 提示 |

**设计哲学**：中文以 400/600/700 三档为主，800 仅用于品牌与空状态；英文 Inter 承接数字与拉丁字符。标题用负字距收紧，正文 1.6 行高保呼吸。字号必须以 Token/工具类引用，不得逐处写 `font-size: 28px`。

---

## 4. Component Stylings（组件样式）

> 以下为可复用组件基线。Naive UI 组件由 `themeOverrides` 驱动；自定义组件（chip / kpi-card / panel / action-tile）必须引用同上 Token，禁止重复定义颜色。圆角值为 🔷 建议（代码当前 8/10/12/14/16/20/24 混用）。

**Buttons**
```css
.btn-primary { background: var(--sp-ui-primary); color: var(--sp-ui-on-primary);
  border: 1px solid var(--sp-ui-primary); border-radius: 10px; padding: 0 16px; height: 36px; font-weight: 600; }
.btn-primary:hover { background: var(--sp-ui-primary-hover); border-color: var(--sp-ui-primary-hover); }
.btn-primary:active { background: var(--sp-ui-primary-pressed); }
.btn-ghost { background: transparent; color: var(--sp-ui-text-1); border: 1px solid var(--sp-ui-border); }
.btn-ghost:hover { background: var(--sp-ui-hover); }
.btn-danger { background: var(--sp-ui-error); color: #fff; border: 1px solid var(--sp-ui-error); }
/* 覆盖 Naive n-button 的颜色必须 !important：它把颜色类变量写在元素 inline style 上 */
```

**Cards / Panel**
```css
.card { background: var(--sp-ui-card); border: 1px solid var(--sp-ui-border);
  border-radius: 12px; padding: 14px; box-shadow: var(--sp-shadow-md); }
```

**Inputs**
```css
.input { background: var(--sp-ui-body); border: 1px solid var(--sp-ui-border);
  border-radius: 10px; color: var(--sp-ui-text-1); padding: 0 12px; height: 36px; }
.input:focus { border-color: var(--sp-ui-primary); box-shadow: 0 0 0 3px var(--sp-ui-primary-soft); }
.input::placeholder { color: var(--sp-ui-text-3); }
```

**Navigation（侧栏 / 移动 Tab）**
- 侧栏菜单项：默认 `--sp-ui-text-2`；激活态 `--sp-ui-primary` + `--sp-ui-primary-soft` 软底；hover `--sp-ui-hover`。
- 移动端 Tab：未激活 `--sp-ui-text-3`；激活 `--sp-ui-primary` + `font-weight:600` + 软底。

**Chips / Tags / Badges**
```css
.chip { display: inline-flex; align-items: center; gap: 6px; height: 34px; padding: 0 12px;
  border-radius: 999px; border: 1px solid var(--sp-ui-border); font-size: 13px; font-weight: 600; }
```

**KPI Card（概览指标块 · ✅ 代码事实几何，圆角建议归一 12px）**
```css
.kpi-card { background: var(--sp-ui-card); border: 1px solid var(--sp-ui-border);
  border-radius: 12px; padding: 14px; min-height: 96px; }
.kpi-icon { width: 34px; height: 34px; border-radius: 10px; } /* 底用 --sp-accent-*-soft，图标用 --sp-accent-* */
.kpi-value { font-size: 22px; font-weight: 700; line-height: 1.15; }
```

**Modal / Drawer**
- 遮罩：`rgba(0,0,0,.5)`（暗）/ `rgba(15,23,42,.4)`（亮，🔷 建议）。
- 内容区：`background: var(--sp-ui-elevated)`；圆角 16px；`box-shadow: var(--sp-shadow-2xl)`。
- 进场：抽屉 translate 缓动 `cubic-bezier(.22,1,.36,1) 240ms`；Modal `scale(.96→1)` 200ms。

**状态设计（Empty / Loading / Error）— 🔷 建议补充（现状为各页临时实现）**
- **空状态**：吉祥物场景图（`mascot-scenes.png` 的「空曲库 / 加载中 / 出错」）+ 一句说明 + 一个主操作按钮；四周留 8% 呼吸区，2:1 横构图。已有素材，规范未纳入。
- **加载**：骨架屏优先于 Spin；行级用 shimmer，页级用 `n-spin`。
- **错误**：错误色 `--sp-ui-error` + 可重试操作，禁止只弹 toast 了事。

---

## 5. Layout Principles（布局原则）

- **间距基数 🔷 建议**：4px。倍数 4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48。组件内 padding 默认 14–16px，区块间距 12–16px，页面边距 16–20px（移动 12px）。
- **栅格**：内容最大宽度 1280px 居中（🔷 建议）；概览页用 `minmax(0,1.35fr) minmax(280px,.9fr)` 主从栅格（✅ 代码事实）；KPI 6 列 → 1200px 降 3 列 → 768px 降 2 列（✅ 代码事实）。
- **容器**：`.content { padding: 16px 20px 24px; }`（✅ 代码事实）；存在悬浮播放胶囊时底部预留 `--gp-reserve`（✅ 代码事实，几何单一真相源在 `App.vue` 的 `:root`）。
- **留白哲学**：信息密度优先但分区清晰——区块之间用 12–16px gap 与 1px 描边界定，而非靠大留白；卡片内部 14px 内边距保证触控与呼吸。

---

## 6. Depth & Elevation（深度与层级）

**Shadow System（🔷 建议：`sm` 取自代码实际卡片阴影，其余为归一化提案）**
```css
--sp-shadow-xs: 0 1px 2px rgba(15,23,42,.06);
--sp-shadow-sm: 0 4px 10px rgba(15,23,42,.06);
--sp-shadow-md: 0 10px 24px rgba(21,32,53,.05);   /* 卡片默认（✅ 取自代码） */
--sp-shadow-lg: 0 14px 34px rgba(21,32,53,.06);   /* Hero（✅ 取自代码） */
--sp-shadow-xl: 0 20px 48px rgba(21,32,53,.10);
--sp-shadow-2xl: 0 24px 60px rgba(0,0,0,.50);     /* 暗色 Modal/Drawer（✅ 取自代码） */
```
> 暗色浮层阴影偏黑（更实），亮色偏冷蓝灰（更柔）。统一引用上述 Token，禁止逐处写 `box-shadow`。

**Surface Layers**：`body → card → elevated → overlay`，靠底色明度 + 阴影区分（注意 §2.1 的表面层级避坑）。
**Z-index**：内容 1 / 侧栏 10 / Dropdown 1000 / 移动 Tab·Drawer 1100 / Modal 1200 / Toast 1300。
**Backdrop**：移动 Tab 与浮层 `backdrop-filter: blur(14px)` + `color-mix` 92% 不透明底（✅ 代码事实）。

**Motion（动效）— 🔷 建议补充（现状为散值）**
- 时长：微交互 120ms / 常规 200–240ms / 浮层进出 240–280ms。
- 缓动：进入 `cubic-bezier(.22,1,.36,1)`（ease-out 强化）；退出 `ease-in`。
- 属性：仅动 `transform` / `opacity`，避免动 `width/height/box-shadow`。
- **可达性**：所有持续/大面积动效（唱片自转、背景扫光、进度脉冲）必须包 `@media (prefers-reduced-motion: reduce)` 关闭。现状仅 4 个播放器文件覆盖，其余页面缺失。

---

## 7. Do's and Don'ts（设计规范与禁忌）

**Do's**
1. 颜色一律走 Token；新增颜色先加进 `tokens.js` / `brand.css` 再使用。
2. Light 模式主色必须用降级后达标值（#047857），不得用 #10B981 配白字。
3. 分类上色一律 `--sp-accent-*-soft` 做底、`--sp-accent-*` 做前景，双模式均达标。
4. 图标用单一图标库（见 §10-P2-1），统一 `currentColor` 着色。
5. 字体必须真正加载；缺字优雅回退系统栈。
6. 主表面用 `--sp-ui-card`；`elevated` / `card-strong` 与暗底过近，别当主表面。

**Don'ts**
1. 禁止写死 HEX（含 `var(--sp-ui-primary, #10B981)` 这类兜底——缺失即暴露 bug 而非掩盖）。
2. 禁止大面积铺品牌渐变；渐变只用于 LOGO / 焦点态 / 强调条。
3. 禁止重新着色 / 旋转 / 拉伸 / 加描边投影 LOGO。
4. 禁止 650/720/760/780 等非标准字重。
5. 禁止在 teleport 到 body 的浮层里引用挂载点局部 CSS 变量。

---

## 8. Responsive Behavior（响应式行为）

| 断点 | 取值 | 说明 |
|------|------|------|
| mobile | ≤768px | 极简顶栏 + 底部 Tab 栏（52px + 安全区）|
| tablet | 769–1024px | 侧栏可折叠（64px）|
| desktop | 1025–1280px | 完整侧栏 220px |
| wide | >1280px | 内容居中限宽 1280px |

- **触控目标**：最小 36×36px（图标按钮 ≥40px 圆形）。
- **折叠策略**：≤900px 概览主从栅格转单列；≤768px KPI 转 2 列、操作入口转单列、chips 各占 50%（✅ 代码事实）。
- **字体缩放**：移动端 H1 28→24、KPI value 22→18；其余层级不变（🔷 建议）。

---

## 9. Agent Prompt Guide（AI 代理提示指南）

**Quick Reference**：配色只有 `tokens.js` 一处真相；核心色 `--sp-ui-*`（底 = `--sp-ui-body`、面 = `--sp-ui-card`），分类色 `--sp-accent-*`；字体 Inter+Noto Sans SC（须加载）；圆角 8/12/16/20；阴影 `--sp-shadow-*`；间距 4 倍数。

**Component Prompts（可直接复制）**
1. `用 Sonpick 设计系统做一个主按钮：背景 --sp-ui-primary，文字 --sp-ui-on-primary，圆角 10px，hover 用 --sp-ui-primary-hover`
2. `生成一个概览 KPI 卡片：--sp-ui-card 底 + 1px --sp-ui-border + 12px 圆角 + --sp-shadow-md，图标用 --sp-accent-teal-soft 底配 --sp-accent-teal`
3. `写一个信息输入行：--sp-ui-body 底、--sp-ui-border 描边、focus 时 border 转 primary 并加 3px primary-soft 光环`
4. `设计一个移动端底部 Tab：未激活 text-3，激活 primary + 600 + primary-soft 软底，底部 blur 毛玻璃`
5. `画一个 Modal：遮罩 rgba(0,0,0,.5)，内容 --sp-ui-elevated 底、16px 圆角、--sp-shadow-2xl，进场 scale .96→1`

**Iteration Guide**
1. 任何颜色需求先问「是不是已有 Token」——没有就加，不写死。
2. 改明暗双模时两套值一起给，并核对 WCAG AA。
3. 浮层 teleport 到 body 的，颜色只引用 `:root` 变量。
4. 字体没加载就先解决加载，再谈排版。
5. 图标统一来源，别混用两套词汇。
6. 间距/圆角/阴影用 Token，别逐处微调。
7. 覆盖 Naive 组件颜色必须 `!important`（它写在 inline style 上）。
8. 组件改动跑 `pnpm check:template-refs` 与构建，确认无渲染期报错。
9. 文档与代码冲突时，以 `tokens.js` + 本文件为准，并同步修订文档。

---

## 10. 现状问题与设计改造建议（附录）

> **取证依据**：`tokens.js`、`brand.css`、`brand-guidelines.md`、`index.html`、`LayoutView.vue`、`DashboardView.vue`、`LoginView.vue` 等 + 全仓 grep 统计。
> **分级口径**：P0 影响正确性/可达性；P1 一致性与规范；P2 体验打磨；P3 文档与细节。「活跃」= 有组件实际消费；「潜在」= 仅定义、零消费。

### P0 — 复核后：**无真正 P0**（初版判断过重，此处据实下调）

> 初版曾将「Token 三套并存」与「Light 模式反色」列为 P0。逐文件核验后**不成立**：
> - 活跃代码中 legacy `--sp-*` **仅 `LoginView.vue` 一个文件、5 处**（`--sp-bg` / `--sp-text` / `--sp-text-2` / `--sp-border`），而这四个在 Light 下**均有正确覆盖**（`brand.css` 的 `[data-theme=light]` 覆盖了 `--sp-bg/surface/border/text/text-2/primary-400`），**无可见缺陷**。初版「`--sp-surface` 仍为暗色致暗卡浮白底」是**误判**——它其实被覆盖为 `#FFFFFF`。
> - 其余组件一致使用 `--sp-ui-*` / `--sp-accent-*`（含 `DashboardView`，它并不混用 legacy）。
> - 结论：不存在影响正确性的 P0；问题本质是**文档漂移 + 死 Token 集**（→ P1/P2）。

### P1 — 一致性（应尽快处理）

**P1-1 · Token 命名「文档讲一套、代码用一套」**
- 现状：`brand.css` 定义了一套**几乎无人消费**的 `--sp-*`（primary-500/bg/surface/border/text/accent-500/success…）；`brand-guidelines.md` 按这套书写并示范 `var(--sp-primary-500)`；而代码实际用 `--sp-ui-*`。**活跃消费者只有 `LoginView` 一个文件。**
- 风险：新人照文档写代码会引入一套平行命名；`--sp-*` 一旦被广泛使用即踩 P2-4 的坑。
- 建议：以 `tokens.js` 为唯一真相，统一为 `--sp-ui-*` + `--sp-accent-*`；`brand.css` 仅保留品牌渐变、吉祥物色、字体变量。迁移 `LoginView` 的 5 处引用。

**P1-2 · 字体从未真正加载（Inter / Noto Sans SC）**
- 现状（✅ 已核）：`index.html` 仅 `<link rel="stylesheet" href="/brand/brand.css">`；全仓无 `@font-face` / Google Fonts / fontsource。声明的 Inter / Noto Sans SC 实际回落系统字体。**这是真实且影响全站观感的问题。**
- 建议：① `@fontsource/inter` + `@fontsource/noto-sans-sc` 打包引入，或自托管 woff2 + `@font-face`；② 若坚持系统字体，则把规范改写成系统栈，别挂名 Inter/Noto。

**P1-3 · 品牌渐变不一致（LOGO 四色 vs 工具两色）**
- 现状：LOGO 为绿→青→蓝→紫四色；`brand.css` 的 `.sp-gradient-brand` 与文档写的是两色 `#34D399→#6366F1`，且 `#6366F1` 不在 LOGO 色域内。
- 建议：以 LOGO 为准定义唯一 `--sp-brand-grad`（四色，停靠点须从源图重新取样）；`info` 色 `#6366F1` 仅作语义/分类色，不参与品牌渐变叙事。

**P1-4 · 非标准字重**
- 现状：`font-weight: 650/720/760/780` **仅出现在 `DashboardView.vue`**（5 处）；其余文件均为标准 600/700/800。
- 建议：收敛到 400/500/600/700/800，改 `DashboardView` 即可。

### P2 — 体验与视觉一致性（规划改造）

**P2-1 · 自研图标零消费，文档与代码背离**
- 现状（✅ 已核）：`brand-guidelines.md` 规定自研 24×24 / 2px / `currentColor` 图标集（21 个，`/brand/icons/*.svg`），全代码库 **grep 零引用**；实际全线用 `@vicons/ionicons5`。文档还示范用 `<img :src>` 渲染——而 `<img>` 无法继承 `currentColor`，示范本身矛盾。
- 建议：二选一——① 正式采用 Ionicons 并更新文档、归档自研图标；② 或真正启用自研图标（以 inline SVG 注入以保留 `currentColor`）。关键：文档说的 = 代码用的。

**P2-2 · 缺 Token 化：间距/圆角/阴影/动效**
- 现状（✅ 已核）：全仓无 `--sp-shadow-*` / `--sp-radius-*` / `--sp-space-*`；圆角 8/10/12/14/16/20/24 混用，阴影 6 种近似 `rgba` 散值。动效可达性（`prefers-reduced-motion`）**仅 4 个播放器文件**覆盖，其余页面缺失。
- 建议：落地 §5/§6 的 Token 与 Motion 规范，逐步替换散值。

**P2-3 · 吉祥物色游离 + 空/加载/错误态未入规范**
- 现状：拾耳暖橙 `#F5A45D` 完全在冷色域外，且与警告琥珀 `#F59E0B/#B45309` 色相接近，有语义混淆风险；空/加载/错误三态有素材（`mascot-scenes.png`）却无统一规范。
- 建议：明确「暖橙仅属吉祥物/空状态，绝不用于状态语义」；把三态纳入 §4 状态设计。

**P2-4 · legacy `--sp-*` 是「潜在陷阱」（当前零消费，但一用即错）**
- 现状：`brand.css` 的 `[data-theme=light]` **未覆盖** legacy 的 `--sp-primary-300/500/600/700`、整个 `--sp-accent-*` 阶、以及 `--sp-success/warning/error/info`——这些在 Light 下仍是暗色值。当前**无组件消费**，故无可见 bug；但任何人一旦使用 `--sp-primary-500`（白底 2.65:1）即踩坑。
- 建议：P1-1 修完后该集合被废弃即自然消除；过渡期至少补 Light 覆盖或全局替换引用。

### P3 — 文档与细节

**P3-1 · `brand-guidelines.md` 与实现/本文件漂移**
- 建议：以本 `DESIGN.md` 为唯一设计规范；将 `brand-guidelines.md` 降为「品牌资产清单」（只留 LOGO/图标文件/吉祥物/用法禁忌），或在顶部指向本文件。

**P3-2 · 组件内 HEX 兜底**
- 现状：`var(--sp-text, #ECEEF2)`、`var(--sp-bg, #0B0C10)`、`var(--sp-ui-border, rgba(127,127,127,.18))` 等兜底集中在 `LoginView`（4 处）与 `DashboardView`（多处 `--sp-ui-*` 兜底）。Light 下变量缺失会静默套用暗色值。
- 建议：删除兜底，缺失即暴露 bug。

**P3-3 · 侧栏左下功能区绝对定位 + 魔法 padding**
- 现状：`LayoutView` 的 `.sider-footer` 绝对贴底，用 `:deep(.n-menu){padding-bottom:54px / 196px}` 给菜单留位，折叠态硬编码易错位。
- 建议：侧栏改 flex 纵向（菜单区 `flex:1` + 底部功能区自然贴底），去掉魔法 padding。

---

### 落地路线（建议顺序）
1. **P1-1 + P2-4**：统一 Token 命名、废弃 legacy `--sp-*`（含 `LoginView` 5 处迁移），顺带消除潜在陷阱。
2. **P1-2 + P1-3 + P1-4**：字体真正加载、品牌渐变唯一化、`DashboardView` 字重标准化。
3. **P2-1 + P2-2 + P2-3**：图标体系二选一、间距/圆角/阴影/动效 Token 化、吉祥物色边界与三态规范。
4. **P3-1/2/3**：文档对齐、清硬编码兜底、侧栏布局稳健化。
