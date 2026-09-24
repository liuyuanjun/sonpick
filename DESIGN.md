# Sonpick 拾音 · 设计系统（硬标准）

> **本文件是前端设计的唯一权威规范。**
> 文中所有数值都由 `web/src/theme/tokens.js` **独家提供**，本文件只做引用与解释，不重新定义。
> 若本文件与代码不一致：**以 `tokens.js` 为准**，并立即修订本文件。
> 违反 §8「红线」的改动一律视为缺陷，不因「看起来还行」而放行。

---

## 0. 怎么用这份规范

### 0.1 三条路径，按场景择一

| 场景 | 怎么做 | 例子 |
|------|--------|------|
| 用 Naive 组件 | 不用管，主题由 `theme/naive.js` 统一注入 | `<n-button type="primary">` |
| 写自定义组件样式 | 只引用 CSS 变量，不写具体值 | `border-radius: var(--sp-radius-lg)` |
| 需要新颜色/新档位 | 先加进 `tokens.js`，再使用 | 新增语义色 → 改 `BRAND.light/dark` |

### 0.2 为什么必须「一份数据、两个出口」

`tokens.js` 派生两份产物，**缺一不可**：

```
tokens.js ──┬─→ theme/naive.js  buildNaiveOverrides()  → Naive 组件的 themeOverrides
            └─→ buildCssVars()                        → :root 上的 --sp-* CSS 变量
```

**实测教训（这是本架构存在的理由）**：Naive UI 的 `common` 自带一套与规范冲突的默认值，且**业务 CSS 压不住**（Naive 把颜色类变量写在元素 inline style 上）：

| Naive 默认 | 后果 | 现在 |
|-----------|------|------|
| `borderRadius: 3px` | 曲库页 61 个、日志/设置各 22 个元素渲染成 3px 直角 | 已由 `common.borderRadius` 收口为 10px |
| `fontWeightStrong: 500` | 与规范的 600 冲突；概览页 500 字重泛滥 | 已收口为 600 |
| `fontFamily: 'v-sans, …'` | 声明的 Inter 永不生效，部分节点回落 Arial | 已收口为 `FONT.ui` |
| `heightMedium: 34px` | 小于触控目标下限 | 已收口为 36px |

> ⚠️ **新增 Naive 覆盖项前，务必先到 `node_modules/naive-ui/es/<组件>/styles/light.mjs` 核实 key 名。**
> Naive 会**静默忽略**未知 key —— 不核实就会写出「看着改了、实际没生效」的假修复。

### 0.3 变量定义在 `documentElement`

由 `stores/theme.js` 注入 `:root`。这样被 **teleport 到 body** 的 Modal / Drawer / Popover 才取得到。
反过来说：**浮层内的样式只允许引用 `:root` 变量**，不得引用挂载点上的局部变量。

---

## 1. 视觉主题与氛围

- **设计哲学**：个人 NAS 音乐库，沉静、专注、有温度。母题「乐海拾音」——声音从中心荡开，你在声海里把它拾起。
- **基调**：深邃、冷静、克制中带一抹渐变高光。**信息密度优先，但分区必须清晰**。
- **暗色为默认**；明亮模式是**完整对等的第二主题**，不是附属品。
- **核心视觉特征**：① 近黑底 + 玻璃质感卡片；② 品牌四色渐变仅作焦点/强调点缀；③ 圆角方形 LOGO 作视觉锚；④ 暖橙吉祥物「拾耳」是唯一的人文暖色。
- **禁止**：大面积铺品牌渐变（见 §8 R-3）、炫技式动效、把界面做成流媒体信息流。

---

## 2. 令牌体系

### 2.1 字体族 · `FONT`

```css
--sp-font-ui:   "Inter", "PingFang SC", "Noto Sans SC", "Noto Sans CJK SC", "Microsoft YaHei", system-ui, -apple-system, sans-serif;
--sp-font-mono: "SF Mono", "JetBrains Mono", ui-monospace, Menlo, Consolas, monospace;
```

- **西文与数字 = Inter**，自托管 latin 子集（5 字重共约 120KB，`@fontsource/inter`，由 `main.js` 引入）。
- **中文 = 系统 CJK 栈**。理由：中文 webfont 体积以 MB 计，与「NAS 自托管 / 离线可用」的产品前提冲突；各平台系统 CJK 字体（PingFang SC / 微软雅黑 / Noto Sans CJK）观感均达标。**中文字体位已预留在栈内**，日后要自托管只需装 `@fontsource/noto-sans-sc` 并在 `main.js` 追加一行 import，无需改动 `tokens.js`。
- **数字必须等宽**：时长、体积、进度、时间列一律加 `class="sp-num"`（= `font-variant-numeric: tabular-nums`）。**实测问题**：概览页 KPI「349.70 MB」因未等宽被迫折成两行、撑高卡片；日志页时间列上下宽度不一致。

### 2.2 排版 · `TYPE`

| 层级 | 字号 | 移动端 | 字重 | 行高 | 字距 | 用途 |
|------|------|--------|------|------|------|------|
| display | 32px | 28px | 800 | 1.15 | -0.01em | 登录品牌名、空状态大标题 |
| h1 | 28px | 24px | 700 | 1.20 | -0.01em | 页面 Hero 标题 |
| h2 | 22px | 18px | 700 | 1.25 | 0 | 区块大标题、KPI 数值 |
| h3 | 16px | — | 700 | 1.30 | 0 | 面板标题 |
| body | 14px | — | 400 | 1.60 | 0 | 正文默认 |
| strong | 14px | — | 600 | 1.60 | 0 | 列表项重点、按钮文字 |
| small | 13px | — | 400 | 1.55 | 0 | 副标题、辅助说明 |
| caption | 12px | — | 500 | 1.40 | 0.02em | 标签、元信息、KPI 提示 |
| micro | 11px | — | 500 | 1.30 | 0.02em | 角标、计数 |

CSS 变量：`--sp-fs-display|h1|h2|h3|body|strong|small|caption|micro`、`--sp-fs-{display,h1,h2}-mobile`、`--sp-fw-regular|medium|semibold|bold|extrabold`。

**硬规则**

1. **字重只允许 400 / 500 / 600 / 700 / 800。** 禁止 650 / 720 / 760 / 780 等中间值。实测反面教材：概览页曾有 7 处非标声明、影响 32 个文字元素，导致**非标字重（32）比标准字重（16）还多**，层级信号彻底失效。
2. **正文下限 13px。** 12px 只用于标签 / 元信息 / 角标，**不得承载正文**。实测反面教材：概览页曾有 67 个文字元素是 12px，正文被压成「小字墙」。
3. **移动端降级是尺度的一部分**（上表「移动端」列），不要另写一个 px 值。
4. **图标尺寸不要混进排版**，见 §2.3。

### 2.3 图标尺度 · `ICON`

```
--sp-icon-sm: 16px   --sp-icon-md: 20px   --sp-icon-lg: 24px   --sp-icon-xl: 32px   --sp-icon-2xl: 40px
```

图标是**独立尺度**，不属排版。两种表达按场景择一：

- 矢量图标组件（`@vicons/ionicons5`）：用 `<n-icon :size="20">`
- 字形图标（符号字形 / 封面占位字形）：用 `font-size: var(--sp-icon-*)`

**实测教训**：封面占位字形曾用 `font-size: 40px` 表达，混进 Type Scale 后被误判为「尺度外字号」——其实是口径问题，用 `--sp-icon-2xl` 即可。

**图标语言必须单一**：全站统一使用 `@vicons/ionicons5` 的**线性**风格。禁止在同一屏内混用线性与彩色面性图标（实测反面教材：侧栏线性图标与概览页 KPI 的彩色双色图标并列，风格断裂）。

### 2.4 圆角 · `RADIUS`

| 令牌 | 值 | 用途 |
|------|-----|------|
| `--sp-radius-xs` | 6px | 进度条、骨架、小徽标 |
| `--sp-radius-sm` | 8px | 次级容器、下拉面板项、表格内标签 |
| `--sp-radius-md` | 10px | **按钮、输入框、下拉触发器（最高频）** |
| `--sp-radius-lg` | 12px | 卡片、面板 |
| `--sp-radius-xl` | 16px | 弹窗、抽屉 |
| `--sp-radius-2xl` | 20px | 大容器（移动端底部抽屉、页面级卡片） |
| `--sp-radius-pill` | 999px | 胶囊 |
| `--sp-radius-circle` | 50% | 正圆 |

**不得新造圆角数值。** 实测教训：业务 CSS 曾声明过 13 种圆角（4/5/6/7/8/9/10/12/14/16/18/20/24/999/50%），现已全部收敛到上表（105 处字号 + 77 处圆角已 token 化）。

> 说明：浏览器里读到「某个圆形图标按钮的 `border-radius` 等于它的高度」属**正常实现**（Naive 用 `radius = height` 表达圆），不是缺陷，不要「修」。

### 2.5 间距 · `SPACE`

基数 **4px**：`--sp-space-1|2|3|4|5|6|8|10|12` = `4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48`

**语义间距**（优先用这些，而不是随手挑一个倍数）：

| 令牌 | 值 | 用途 |
|------|-----|------|
| `--sp-space-section` | 16px | 区块之间 |
| `--sp-space-card-gap` | 12px | 卡片之间 |
| `--sp-space-card-pad` | 14px | 卡片内边距 |

### 2.6 阴影 · `SHADOW`

暗色更实偏黑，亮色更柔偏冷蓝灰——两套值并列定义在 `tokens.js`。

```css
--sp-shadow-xs   /* 1px 微投影 */
--sp-shadow-sm   /* 4px  */
--sp-shadow-md   /* 10px 卡片默认 */
--sp-shadow-lg   /* 14px Hero */
--sp-shadow-xl   /* 20px */
--sp-shadow-2xl  /* 24px 浮层（Modal / Drawer） */
```

**禁止逐处写 `box-shadow`。**

### 2.7 动效 · `MOTION`

| 令牌 | 值 |
|------|-----|
| `--sp-dur-fast` | 120ms（微交互：hover、按压） |
| `--sp-dur-base` | 200ms（常规：展开、切换） |
| `--sp-dur-slow` | 240ms（浮层进出） |
| `--sp-ease-enter` | `cubic-bezier(.22, 1, .36, 1)` |
| `--sp-ease-exit` | `cubic-bezier(.4, 0, 1, 1)` |

**只动 `transform` / `opacity`。** 不要动 `width` / `height` / `box-shadow`。

**`prefers-reduced-motion` 已在 `styles/base.css` 全局收口**，组件无需再各写一份媒体查询。个别需要「减弱动效下仍保留语义反馈」的组件才单独声明例外。

### 2.8 层级 · z-index

z-index 分带以 `AGENTS.md` §5.5 为唯一权威，此处不重复定义：`1000` 底部播放器、`1100` 移动端底栏、`1400` 播放器抽屉、`2000+` 留给 Naive 弹层（message `6000`）。业务自定义浮层只允许取这些带，**禁止写死 ≥2000 的大数**。

### 2.9 颜色

#### 核心令牌（随模式切换）

| 角色 | 变量 | Dark | Light |
|------|------|------|-------|
| 页面底 | `--sp-ui-body` | `#0B0C10` | `#F5F6F8` |
| 卡片面 | `--sp-ui-card` | `#14161C` | `#FFFFFF` |
| 强卡片面 | `--sp-ui-card-strong` | `#181B22` | `#FFFFFF` |
| 浮层/弹窗 | `--sp-ui-elevated` | `#181B22` | `#FFFFFF` |
| 描边 | `--sp-ui-border` | `#23262F` | `#E3E6EB` |
| 分割线 | `--sp-ui-divider` | `#23262F` | `#E8EAEF` |
| 主文字 | `--sp-ui-text-1` | `#ECEEF2` | `#111827` |
| 次文字 | `--sp-ui-text-2` | `#B6BECB` | `#4B5563` |
| 弱文字 | `--sp-ui-text-3` | `#8B95A5` | `#6B7280` |
| 主色 | `--sp-ui-primary` | `#10B981` | `#047857` |
| 主色 hover | `--sp-ui-primary-hover` | `#34D399` | `#065F46` |
| 主色 pressed | `--sp-ui-primary-pressed` | `#059669` | `#044434` |
| 主色反白 | `--sp-ui-on-primary` | `#04120C` | `#FFFFFF` |
| 主色软底 | `--sp-ui-primary-soft` | `rgba(16,185,129,.14)` | `rgba(4,120,87,.10)` |
| 主色软底2 | `--sp-ui-primary-soft-2` | `rgba(16,185,129,.22)` | `rgba(4,120,87,.16)` |
| 悬停叠层 | `--sp-ui-hover` | `rgba(255,255,255,.06)` | `rgba(15,23,42,.05)` |
| 信息色 | `--sp-ui-info` | `#6366F1` | `#4F46E5` |
| 成功色 | `--sp-ui-success` | `#10B981` | `#047857` |
| 警告色 | `--sp-ui-warning` | `#F59E0B` | `#B45309` |
| 错误色 | `--sp-ui-error` | `#EF4444` | `#DC2626` |

> **Light 主色降级是硬要求**：`#10B981` 配白字只有 2.65:1（不达 AA）；Light 用色阶 700 `#047857`（5.55:1）。hover **继续加深**而非提亮——交互态朝「远离页面底色」的方向走。
> **表面层级避坑**：暗色下 `--sp-ui-elevated` / `--sp-ui-card-strong` 与页面底几乎同亮度，**不要拿它们当主表面**，否则边界消失。主表面一律 `--sp-ui-card`。

#### 分类强调色

`--sp-accent-{teal,blue,rose,amber,sky,green,slate}` + 对应 `-soft`（软底 = `color-mix(in srgb, <fg> 16%:dark / 12%:light, transparent)`）

| 类别 | Dark | Light |
|------|------|-------|
| teal | `#2DD4BF` | `#0F766E` |
| blue | `#60A5FA` | `#1D4ED8` |
| rose | `#FB7185` | `#BE123C` |
| amber | `#FBBF24` | `#B45309` |
| sky | `#38BDF8` | `#0369A1` |
| green | `#4ADE80` | `#15803D` |
| slate | `#94A3B8` | `#475569` |

**用法纪律（硬规则）**

强调色只有**一种**合法用途：**给「类别」编码**（KPI 图标、快捷入口图标、活动流图标）。据此必须区分两类上色：

| 类型 | 允许用什么 | 说明 |
|------|-----------|------|
| **类别编码**（图标软底 + 图标） | `--sp-accent-*` / `-soft` | 同屏类别数上限 = 色板种类数（7）；**只能落在图标上**，不得用于文字、边框、数据填充 |
| **数据填充**（进度条 / 条形 / 数值 / 占比） | **主色或中性色** | 同性质、重复出现的元素**一律同色**。它们表达的是「多少」，不是「哪一类」 |

- **语义色（`success` / `warning` / `error` / `info`）只表达状态，不表达类别。**
  实测反面教材：概览页三条同性质的覆盖率进度条（封面 / 歌词 / 时长）分别用了 `success` / `info` / `warning` —— 这三者是并列的覆盖率，不是三种状态，把语义色当分类色用会让用户误以为「歌词出问题了」。
- 底用 `-soft`，前景用非 soft 的对应色，双模均满足 AA。
- 同一屏内同时出现的**类别色**建议 ≤ 6 种，超出时优先合并语义相近的类别。

#### 品牌渐变

`--sp-brand-grad` = `linear-gradient(135deg, #64F0AC 0%, #22D3EE 38%, #556FE1 72%, #7A40DC 100%)`

**仅用于 LOGO / 焦点态 / 强调条。** 禁止用作大面积背景。

**封面派生氛围光（唯一被允许的「大面积渐变」）** —— 播放器抽屉的氛围底取自**当前专辑封面主色**，让舞台随唱片变化。硬性上限：

1. 最多 **2 层**光晕
2. 单层 alpha ≤ **0.20**（暗）/ **≤ 0.14**（亮）
3. 取不到封面主色时**回落到 `var(--sp-ui-primary)`**，**不得使用色板外的任何颜色**
4. 底色一律取自 `--sp-ui-*`
5. **同一视图只允许存在一套氛围底。** 实测反面教材：播放器抽屉曾同时由 `PlayerPanel` 的内联 `ambientBackground()` 与 `GlobalPlayerDrawer` 的 `.gp-drawer-stage` 各铺一层全屏渐变，叠成两层氛围光，并夹带色板外的硬编码紫 `#5856D6`。**现已合并为唯一来源 = `.gp-drawer-stage`。**

> **氛围光晕 vs 大面积铺色**的界线：低透明度（≤.20）、色板内、≤2 层的**光晕**是允许的氛围手段；高饱和、多层堆叠、色板外的**铺色**是禁止项。

---

## 3. 组件规范

### 3.1 Naive 组件

颜色、圆角、字号、控件高度**全部由 `theme/naive.js` 注入**，业务代码直接使用，**不要逐处覆盖**。

- 覆盖 Naive 的**颜色**必须 `!important`：它把颜色类变量写在元素 inline style 上（几何类变量走 CSS，不需要 `!important`）。
- 点击波纹同样是 inline 的：`--n-ripple-color` 漏了 `!important` 时按下会闪一圈品牌色。

### 3.2 项目自有组件（须在 `main.js` 注册）

| 组件 | 用途 | 用法要点 |
|------|------|----------|
| `SpTable` | **全站表格唯一入口** | 与 `n-data-table` 用法完全一致；额外支持 `empty-title` / `empty-description`。**新表格一律用 `<sp-table>`，不要直接用 `<n-data-table>`** —— 后者无数据时内部渲染的 `n-empty` 默认描述是英文 `No Data`，而该文案是组件 prop、无法从 themeOverrides 收口 |
| `StateEmpty` | **全站空状态唯一实现** | `title`（必填）/ `description` / `actionText` / `size`(`page`\|`block`\|`compact`)；`#illustration` 槽可替换插画 |

### 3.3 基础样式层 · `styles/base.css`

- 把 Token 落到文档根（字体、字号、行高、前后景色）
- **`button, input, select, textarea { font: inherit }`——不可删。** 表单控件默认不继承字体：`<button>` 的 UA 默认字号是 **13.3333px**，无 `font-family` 的节点会回落 **Arial**。实测反面教材：概览页 `.action-tile` 正因未设字号而整块渲染成 13.3333px。
- 工具类：`.sp-num`（数字等宽）、`.sp-truncate`、`.sp-sr-only`
- 全局 `:focus-visible` 焦点环、全局 `prefers-reduced-motion` 收口

### 3.4 按钮层级

同一视野内**只允许一个主按钮**（`type="primary"`）。实测反面教材：概览页「搜索下载」与「去曲库挑几首」同为深绿实心，主次不分。

---

## 4. 状态设计（空 / 加载 / 错误）

**空状态 = 插画 + 一句话说明 + 一个主操作。** 禁止只放一个图标了事，**禁止英文文案**。

三档尺度（`StateEmpty` 的 `size`）：

| 档位 | 场景 | 表现 |
|------|------|------|
| `page` | 整页/整块内容区为空 | 88px 插画 + 标题 + 说明 + 主操作 |
| `block` | 卡片、面板内部 | 88px 插画 + 标题 + 说明 |
| `compact` | 表格、下拉、队列、任务中心 | 48px 插画 + 单行文案 |

> **插画素材现状（待办）**：`web/public/brand/mascot/mascot-scenes.png` 是**深色底、不透明**的三格拼图（空曲库/加载/出错），在亮色主题下会变成一块深色方块——登录页的吉祥物图已有此问题。
> 因此 `StateEmpty` 的默认插画是**内联 SVG 声波弧线**（Token 上色、双模自动跟随）。
> `#illustration` 槽位已预留：待该素材**以透明底 + 单张独立**重新导出后，直接传入 `<img>` 即可替换，无需改动任何调用方。

**加载**：骨架屏优先于 Spin；行级用 shimmer，页级用 `n-spin`。
**错误**：错误色 + 可重试操作，禁止只弹一个 toast 了事。文案必须中文（后端英文枚举需经映射表，见日志页 `statusLabel`）。

---

## 5. 布局与响应式

### 5.1 间距与容器

| 项 | 值 |
|----|-----|
| 页面边距 | 16px 竖向 / 20px 横向（移动 12px） |
| 区块间距 | 16px |
| 卡片间距 | 12px |
| 卡片内边距 | 14px |
| 内容最大宽度 | 1280px（贴侧栏，右侧留白） |
| 触控目标最小 | 36×36px |

> ⚠️ **落地状态**：上表是 `tokens.js` 的**声明值**（详见 `LAYOUT` 注释）。已接入：`touchTargetMin`（→ naive.js 控件高度）；页面边距（`pagePad*`）与内容限宽 `contentMaxWidth`（1280px）由 `LayoutView` 的 `.content`/`.header` 消费；语义间距 `section`/`card-pad`/`card-gap` 已在「值匹配处」消费。`iconButtonSize`（圆形按钮 40px）已删除（无现实锚点）。其余值不匹配的间距（18/10/8/6px）留待「间距收敛」专项。

### 5.2 断点

| 断点 | 取值 | 行为 |
|------|------|------|
| mobile | ≤768px | 极简顶栏 + 底部 Tab 栏（52px + 安全区） |
| desktop | >768px | 完整侧栏 220px；折叠为 64px 由左下「折叠开关」手动触发 |

> ⚠️ 当前代码只实现 768px 一处断点（`useIsMobile()` / CSS `max-width: 768px`）。「tablet / wide 分级」**尚未落地**；内容限宽（贴侧栏）已由 §5.1 的 `contentMaxWidth` 接入（见 §5.1 落地状态）。

**移动端字号降级**用 `--sp-fs-{display,h1,h2}-mobile`，不要另写 px。

### 5.3 外壳架构（**不得改动**）

播放器外壳**只有三层**，不得再增挂载点：

1. 系统侧边栏「我的音乐」六项 → `/player/<section>` 列表页（`PlayerView` 只渲染列表）
2. 底部悬浮胶囊 `GlobalPlayer` → **唯一音频出口**
3. 全局大播放器抽屉 `GlobalPlayerDrawer` → **`PlayerPanel` 与 `PlayerQueue` 的唯一宿主**

- `player.fullPlayerOpen` = 抽屉打开；`player.showQueue` = 队列展开（渲染在抽屉内部）。
- **悬浮胶囊几何的唯一真相源**在 `App.vue` 的 `:root`：`--gp-bar-height` / `--gp-bar-gap` / `--gp-bottom-offset` / `--gp-reserve`。各页面底部留白一律用 `--gp-reserve`，不得自己算。
- 桌面端无顶栏；低频入口（曲库/日志/设置/改密码/退出）收进左下账户抽屉。
- **导航语言全站统一：线性图标 + 文案 + 软底激活态。** 实测反面教材：设置页二级导航曾是纯文字列表（无图标、激活态无圆角），与主侧栏并列像两个产品。

### 5.4 布局收敛

内容不足时**不要用撑满视口的方式留白**。卡片高度由内容决定，剩余空间留给页面底。

---

## 6. 深度与质感

`body → card → elevated → overlay`，靠底色明度 + 阴影层级区分（注意 §2.9 的表面层级避坑）。

**玻璃质感**：移动 Tab 栏与浮层用 `backdrop-filter: blur(14px)` + `color-mix` 半透明底。

**播放器舞台的局部中性梯度（刻意的例外）**：`PlayerPanel` 定义了 `--fg` / `--fg-2` / `--fg-3` / `--fg-4` / `--rail` / `--bg` / `--vinyl-bg-a|b` / `--vinyl-shadow` 等**舞台专用**变量（暗色为底、`.light` 变体并列）。
舞台是沉浸式深色表面，不属于页面表面体系，因此允许自带一套中性梯度。但必须遵守：

- **`--vinyl-bg-a/b` 与 `--vinyl-shadow` 的唯一真相源是 `PlayerPanel`**，`PlayerArt` / `PlayerSkin` 只消费，不得写死色值。
- **投影不要挂在自转层上**：`box-shadow` / `filter` 在元素自身坐标系里绘制，挂到带 `animation: spin` 的盘面上会跟着转（亮色下肉眼可见）。投影留外层，自转下沉到子层。
- `--disc-ratio` 只写在 `PlayerSkin .body-card`；`PlayerArt` 只留同名兜底值，不要两处各写。
- 判断「圆形装饰是否压住相邻内容」要用**可见圆**（直径取 `offsetWidth`、圆心取 `bbox` 中心）；直接读旋转元素的 `getBoundingClientRect()` 会因 √2 膨胀误判。

---

## 7. 无障碍

1. **对比度**：正文/前景 ≥ WCAG AA **4.5:1**；大字与图标 ≥ **3:1**。改动任何色值都必须重新校验（尤其 Light 主色与语义色）。
2. **键盘可达**：`styles/base.css` 已提供全局 `:focus-visible` 焦点环；`aria-label` 必须写在仅有图标的交互元素上。
3. **减弱动效**：全局已收口；新增持续/大面积动效（自转、扫光、脉冲）**不要**再依赖局部媒体查询，直接复用全局规则即可。
4. **语义化**：图标容器加 `aria-hidden="true"`；纯装饰插画同理。
5. **触控目标** ≥ 36×36px。

---

## 8. 红线（Do's & Don'ts）

### Do's

1. 颜色一律走 Token；新增颜色先加进 `tokens.js` 再使用。
2. Light 模式主色必须用降级后达标值（`#047857`），不得用 `#10B981` 配白字。
3. 分类上色一律 `-soft` 做底、非 soft 做前景，双模均达标。
4. 数字加 `.sp-num`。
5. 空状态用 `StateEmpty`，表格用 `SpTable`，文案中文。
6. 新组件（含 `<sp-*>`）必须在 `main.js` 用 `app.component('SpXxx', SpXxx)` 显式注册；**不要把自有组件塞进 `naive-ui` 的 `create({ components })`**（会被注册成 `Nundefined`，见 R-10）。
7. 改完模板跑 `pnpm check:template-refs`（模板里调用未 import 的函数会在渲染期整块子树失败，且 `vite build` 不报错）。

### Don'ts

| # | 禁止 | 原因 |
|---|------|------|
| **R-1** | 写死 HEX / px 数值（含 `var(--sp-ui-primary, #10B981)` 这类兜底） | 兜底会掩盖缺失的 Token，让 bug 静默 |
| **R-2** | 使用 400/500/600/700/800 之外的字重 | 层级信号失效（实测非标比标准还多） |
| **R-3** | 大面积铺品牌渐变 / 高饱和色块；叠超过 2 层氛围光；使用色板外颜色 | 破坏沉静感、冲淡内容 |
| **R-4** | 把类别强调色用到「数据填充」上（进度条 / 条形 / 数值）；或用语义色表达类别 | 类别色表达「哪一类」，数据填充该用主色；语义色表达状态，混用会让用户误读 |
| **R-5** | 英文文案（含后端英文枚举直出） | 中文优先是产品红线 |
| **R-6** | 在 teleport 到 body 的浮层里引用挂载点局部变量 | 取不到，样式静默失效 |
| **R-7** | 把「圆形图标按钮的 radius 等于高度」当成缺陷去改 | 那是 Naive 表达圆形的正常实现 |
| **R-8** | 重新着色 / 旋转 / 拉伸 LOGO，或给 LOGO 加描边投影 | 品牌规范 |
| **R-9** | 重复实现既有能力（如另写一个空状态 / 表格包装 / 选版本逻辑） | AGENTS.md：模块化、一次实现多处调用 |
| **R-10** | 把项目自有组件塞进 `naive-ui` 的 `create({ components })` | 该函数只做 `app.component('N' + name, c)`。SFC 用 `<script setup>` 时没有 `name`，会被注册成 `Nundefined`；模板解析不到即渲染成未知元素，**且控制台不报错**（实测表现为「表格整块消失」）。自有组件一律 `app.component('SpTable', SpTable)` 显式注册 |

---

## 9. 验收清单（可执行）

改完前端后，按下表逐项确认。**任何一项不通过都不得发布。**

**自动化**

- [ ] `pnpm check:template-refs` 无未解析的模板调用
- [ ] `pnpm build` 通过
- [ ] `pnpm test`（`node --test`）全绿

**Token 纪律（可用 grep 直接验）**

- [ ] 无写死的 `font-size: Npx`（应全部为 `var(--sp-fs-*)`）
- [ ] 无写死的 `border-radius: Npx`（多值形式用 `var(--sp-radius-*)` 组合）
- [ ] 无 `font-weight` 非标值（650/720/760/780 等）
- [ ] 无 `var(--sp-*, #hex)` 形式的硬编码兜底
- [ ] 色板外颜色（`#5856D6`、`rgba(64,128,255,…)`、`#12141a` …）零出现
- [ ] 新组件已登记到 `main.js`，**且在真实浏览器确认没有未知标签残留**：
      在控制台执行下面这行，结果必须是 `[]` —— 出现 `sp-xxx` 就说明组件没注册上（这个失败不报错，只能这样验）

      ```js
      [...document.querySelectorAll('*')].map(e => e.tagName.toLowerCase()).filter(t => t.startsWith('sp-'))
      ```

**视觉（在真实浏览器、真实页面上验证，不要只读代码）**

- [ ] 明暗双模逐页过一遍；重点看侧栏激活态、卡片边界、浮层（teleport 后主题是否正确）
- [ ] 移动端（≤768px）底部 Tab 栏不遮挡内容
- [ ] 数字列（时长/体积/进度/时间）上下对齐
- [ ] 空状态为中文且有主操作
- [ ] `docs/ui-smoke-checklist.md` 全项通过

---

## 10. 历史问题与处置（供回归对照）

以下问题均经**真实浏览器取证**确认，已在本次改造中处理。它们曾经出现，**回归时优先复查这几处**。

### 10.1 已修复（代码已落地）

| 问题 | 取证 | 处置 |
|------|------|------|
| Inter / Noto Sans SC 声明了却从未加载，全站实际渲染 Naive 的 `v-sans`，部分节点回落 Arial | `index.html` 无任何字体引入途径 | 自托管 Inter latin 子集；中文明确走系统栈；`font: inherit` 堵住回落 |
| 圆角 3px 泄漏（Naive `common.borderRadius` 默认值） | 曲库 61 个、日志/设置各 22 个元素 | `naive.js` 的 `common.borderRadius` 收口 |
| `fontWeightStrong` 默认 500 与规范 600 冲突 | 概览 500 字重泛滥 | 收口为 600（曲库页 600 从 10 → 130） |
| 非标字重 650/720/760/780 | 概览页 7 处声明、影响 32 个元素 | 按语义映射到 600/700 |
| `13.3333px`（`<button>` 的 UA 默认字号渗出） | 概览页 `.action-tile` 等 18 个元素 | 全局 `font: inherit` |
| 尺度外字号 12.5 / 15 / 15.5 / 17 / 18 / 24 / 26 / 30 / 40px | 27 处声明 | 全部映射到 Type Scale + 移动端档位 + 图标尺度 |
| 表格空态英文 `No Data` | 曲库页、下载页 | 新增 `SpTable` 统一兜住 `#empty` |
| 日志状态标签英文 `success` / `failed` | 日志页 | 新增 `statusLabel` 映射 |
| 日志路径列溢出（565px 内容塞进 153px），12 行全被截断 | 日志页实测 | 只显示文件名，完整路径进 `title` |
| 色板外硬编码紫 `#5856D6` + 蓝 `rgba(64,128,255)` + 底色 `#12141a`/`#0a0b0f`/`#07080b` | `utils/color.js` 的 `ambientBackground()` | 删除该函数；氛围底合并为 `.gp-drawer-stage` 唯一来源 |
| 播放器抽屉叠两层全屏氛围渐变 | `gp-drawer-stage` + `player-panel` 各一层 | 合并为一层，alpha 上限 0.20 |
| 死代码 1117 行 | `SourcesView.vue`(1036) / `ImportView.vue`(81) 零引用 | 已删除 |
| 死样式 `brand.css` 全文件零消费 | 旧 `--sp-*` 色阶、吉祥物色、字体栈均已由 `tokens.js` 取代 | 已删除（连同 `index.html` 的引用） |
| 设置页二级导航无图标、与主侧栏风格割裂 | 设置页截图 | 换用主侧栏同源导航语言（线性图标 + 软底激活态） |
| 设置页「实际路径」与输入框内容完全重复 | 设置页截图 | 改为**仅在输入为相对路径/留空时**显示 |
| 下载页「命名规范」常驻占约 1/3 屏高 | 下载页截图 | 改为可折叠，默认收起 |
| `regionOptions` 地区标注不规范 | `SettingsView.vue` | 改为「中国香港」「中国台湾」 |
| 概览页三条同性质覆盖率进度条用 `success`/`info`/`warning` 区分类别 | 概览页截图（绿/紫/橙三色） | 统一为 `--sp-ui-primary`（见 §2.9） |
| 概览页 KPI「349.70 MB」被拆成两行撑高卡片 | 概览页截图 | `.kpi-value` 加 `tabular-nums` + `nowrap` |
| 项目自有组件 `<sp-table>` 未注册，被渲染成未知元素，**且控制台不报错** | CDP 实测 `spTags: ['sp-table']`、表格整块消失 | 改用 `app.component()` 显式注册（见 §8 R-10） |

### 10.2 遗留（已知、待排期）

| 项 | 说明 |
|----|------|
| 吉祥物场景图素材 | `mascot-scenes.png` 为深色底不透明三格拼图，需**透明底 + 单张独立**重导出；登录页与空状态插画都等它 |
| 前端缺少组件测试 | 目前只有 3 个纯函数用例（`node --test`），**无组件测试 / 无浏览器测试**。视觉改动的回归完全依赖人工跑 §9 清单 |
| 表格分页/筛选 | `SpTable` 只统一了空白态；分页仍由各调用方自行传 `pagination` |
| 概览页信息密度 | 正文实测仍有较多 12px；Type Scale 已定「正文下限 13px」，需逐页把承载正文的 12px 提到 13px（属内容层调整，非 Token 问题） |

---

## 附：相关文档

| 文档 | 职责 |
|------|------|
| `web/src/theme/tokens.js` | **设计 Token 唯一真相源**（本文件所有数值的出处） |
| `web/src/theme/naive.js` | Token → Naive `themeOverrides` 适配层 |
| `web/src/styles/base.css` | 全局基线：Token 落地 + UA 默认值收口 + 工具类 + 无障碍 |
| `AGENTS.md` | 项目操作手册（含前端纪律：组件注册、模板标识符检查） |
| `docs/ui-smoke-checklist.md` | 前端人工冒烟清单（前端改动/发布前必跑） |
| `docs/brand-guidelines.md` | 品牌**资产**清单（LOGO / 图标文件 / 吉祥物）；规范以本文件为准 |
| `docs/ui-diagnosis-2026-09-21.md` | 本次改造的取证报告（一次性审计留档，结论已并入本文件） |
