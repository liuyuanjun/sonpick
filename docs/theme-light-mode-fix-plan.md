# 明亮模式损坏：诊断与修复方案

> 日期：2026-09-08 ｜ 影响版本：v0.15.1-rc8 起（含 rc9 / rc10）
> 结论：不是「切换没生效」，而是**主题覆盖层被写死成暗色**，明亮主题只生效了局部。
>
> **状态：已修复**（2026-09-08）。§1-§3 为诊断存档，§8 记录最终决策与落地结果。

---

## 1. 现象

点击主题按钮切到明亮模式后，页面整体仍是暗色，只有少数线条 / 控件（输入框、表头、弹窗、hover 态、分隔线）变亮。

---

## 2. 根因（P0）

`web/src/App.vue` 的 `themeOverrides` 是一个**与当前主题无关的常量对象**，里面把 Naive UI 的表面色、文字色、描边色全部写死成暗色值：

```js
// App.vue L29-50（问题代码）
const themeOverrides = {
  common: {
    bodyColor: '#0B0C10',     // ← 暗色底
    cardColor: '#14161C',     // ← 暗色面
    borderColor: '#23262F',   // ← 暗色描边
    textColorBase: '#ECEEF2', // ← 亮字（在亮底上会不可读）
    textColor1: '#ECEEF2',
    textColor2: '#B6BECB',
    textColor3: '#8B95A5',
  },
}
```

它被无条件传给 `n-config-provider`：

```vue
<n-config-provider :theme="themeStore.isDark ? darkTheme : lightTheme"
                   :theme-overrides="themeOverrides">
```

**切换明亮模式时的实际结果**：

| 颜色 | 来源 | 明亮模式下实际值 |
|------|------|------------------|
| body / card / border / text | `themeOverrides`（写死） | **仍是暗色** |
| input / tableHeader / popover / modal / hover / divider / actionColor | Naive `lightTheme` 衍生值（未被覆盖） | 亮色 ✅ |

于是「底和面是暗的，只有若干控件和线条是亮的」——与用户描述完全一致。

**引入点**：`ecc941e feat(brand): 品牌视觉系统 v1.0`（v0.15.1-rc8）。rc8 之前的 `App.vue` 没有 `theme-overrides`，明亮模式正常。

---

## 3. 并发问题（P1/P2）

### P0-2：约 88 处 CSS 变量引用了「从不存在的变量」

Naive UI **不会**向 `:root` 注入全局 `--n-*` 变量（`LayoutView.vue` L135 的注释也这么说）。项目里却大量依赖它们：

- `var(--n-card-color)` / `var(--n-border-color)` / `var(--n-text-color-*` / `var(--n-primary-color)` 等 —— **50 处**
- `var(--card-color)` / `var(--primary-color)` / `var(--border-color)` / `var(--text-color-3)` —— **38 处**（同样零定义）

分布：`PlayerView`(8) `SongTable`(7) `PlayerQueue`(9) `SearchDownload`(8) `DashboardView`(18) `LibraryView`(15) `SettingsView`(5) `LogsView`(3) `SourcesView`(2) `DownloadView`(2) `TaskCenter`(1)

这些声明在**计算值阶段无效**，等于没写：背景变透明、色值走继承。暗色模式下「透明叠在深底上」碰巧看不出来；明亮模式下会成片失效（高亮态、分组条、次要文字、卡片底色全部丢失）。

### P1-1：`brand.css` 的亮色分支是死代码

`web/public/brand/brand.css` 已经写了 `[data-theme="light"] { --sp-bg: #FAFAFA; ... }`，但**全项目没有任何一处设置 `document.documentElement.dataset.theme`**，所以登录页等使用 `--sp-*` 的地方永远走暗色回退值。

### P1-2：硬编码暗色残留

| 文件 | 行 | 内容 |
|------|----|------|
| `views/LoginView.vue` | 152 | `.brand-pane { background: #0B0C10 }` |
| `views/LoginView.vue` | 130-140 | `var(--sp-bg/--sp-surface, 暗色回退)` |
| `views/PlayerView.vue` | 1155 | `.mobile-player-overlay { background: #0b0c10 }` |
| `views/PlayerView.vue` | 1161 | `.mobile-queue-sheet { background: var(--n-card-color) }`（无效） |

### P2-1：主题元数据与主题状态不同步
`index.html` 的 `<meta name="theme-color" content="#0B0C10">` 固定暗色，移动端浏览器地址栏不跟随。

### P2-2：主色双轨
`themeOverrides.primaryColor = #10B981`，但 CSS 里硬编码大量 `#18a058`（Naive 默认绿）。两套绿并存。

### P2-3：`themeStore` 能力缺失
- 无 `system` 模式，只在 `init()` 时读一次 `prefers-color-scheme`，之后系统切换不跟随；
- `init()` 在 `App.vue` 的 `onMounted` 里执行 → 首屏会闪一下错误主题（FOUC）；
- 切换主题后不写 `data-theme`、不更新 meta。

---

## 4. 修复方案

### 设计原则：单一主题真相源

把「主题 token」收口到一处，同时产出两样东西：**Naive `themeOverrides`** 和 **全局 CSS 变量**。业务组件只消费变量，不再写死颜色。

```
themeStore.isDark ──┬──> naiveTheme (lightTheme | darkTheme)
                    ├──> naiveOverrides (common: 品牌色 + 该模式的表面/文字色)
                    └──> CSS 变量注入到 :root（--sp-ui-*，并保留 --n-* / --card-color 别名）
                              │
                              ├──> data-theme="light|dark"（brand.css 分支生效）
                              └──> <meta name="theme-color">
```

### 步骤 1（P0，止血 · ~20 行）

新建 `web/src/theme/tokens.js`：

```js
// 与模式无关：品牌语义色
export const brandCommon = {
  primaryColor: '#10B981', primaryColorHover: '#34D399',
  primaryColorPressed: '#059669', primaryColorSuppl: '#34D399',
  infoColor: '#6366F1', infoColorHover: '#818CF8',
  infoColorPressed: '#4F46E5', infoColorSuppl: '#818CF8',
  successColor: '#10B981', warningColor: '#F59E0B', errorColor: '#EF4444',
}

// 与模式相关：表面 / 文字 / 描边
export const darkTokens = {
  bodyColor: '#0B0C10', cardColor: '#14161C', borderColor: '#23262F',
  textColorBase: '#ECEEF2', textColor1: '#ECEEF2', textColor2: '#B6BECB', textColor3: '#8B95A5',
}
export const lightTokens = {
  bodyColor: '#F5F6F8', cardColor: '#FFFFFF', borderColor: '#E5E7EB',
  textColorBase: '#0B0C10', textColor1: '#111827', textColor2: '#4B5563', textColor3: '#6B7280',
}
```

`App.vue` 改为：

```vue
<n-config-provider :theme="themeStore.naiveTheme" :theme-overrides="themeStore.naiveOverrides">
```

```js
const naiveOverrides = computed(() => ({ common: { ...brandCommon, ...(themeStore.isDark ? darkTokens : lightTokens) } }))
```

→ 修完这一步，明亮模式即可正常切换（覆盖 80% 观感）。

### 步骤 2（P0，消除 88 处死变量 · ~40 行）

在 `App.vue` 根元素用 `:style` 注入 CSS 变量（Vue 的 `v-bind`-in-style / 内联 style 均可），同时把 `--n-*` 和 `--card-color` 等别名一并定义，**一次性兜住全部历史引用，无需改 88 处组件**：

```js
const cssVars = computed(() => {
  const t = { ...brandCommon, ...(themeStore.isDark ? darkTokens : lightTokens) }
  return {
    '--sp-ui-body': t.bodyColor,
    '--sp-ui-card': t.cardColor,
    '--sp-ui-border': t.borderColor,
    '--sp-ui-text-1': t.textColor1,
    '--sp-ui-text-2': t.textColor2,
    '--sp-ui-text-3': t.textColor3,
    '--sp-ui-primary': t.primaryColor,
    // 兼容别名：历史代码里的 --n-* / --card-color 等
    '--n-body-color': t.bodyColor, '--n-card-color': t.cardColor,
    '--n-border-color': t.borderColor, '--n-text-color': t.textColor1,
    '--n-text-color-2': t.textColor2, '--n-text-color-3': t.textColor3,
    '--n-primary-color': t.primaryColor, '--n-color': t.cardColor,
    '--body-color': t.bodyColor, '--card-color': t.cardColor,
    '--border-color': t.borderColor, '--primary-color': t.primaryColor,
    '--text-color-3': t.textColor3,
  }
})
```

> 说明：别名是**过渡手段**。建议在同一次修复中顺手把 `var(--n-*)` 批量替换为 `var(--sp-ui-*)`（纯机械替换，约 50 处），别名保留 1-2 个版本后删除。

### 步骤 3（P1，`themeStore` 增强）

`web/src/stores/theme.js`：

- 增加 `mode: 'system' | 'light' | 'dark'`（默认 `system`，localStorage key 保持 `sonpick_theme` 兼容旧值 `light`/`dark`）；
- `watchEffect` 里统一执行副作用：
  - `document.documentElement.dataset.theme = resolved`（让 `brand.css` 的亮色分支生效）
  - 更新 `<meta name="theme-color">`
- 监听 `window.matchMedia('(prefers-color-scheme: dark)')` 的 `change` 事件，`mode === 'system'` 时自动跟随；
- 导出 `naiveTheme` / `naiveOverrides` / `cssVars` computed，供 `App.vue` 消费；
- `init()` 挪到 `main.js` 的 `app.mount()` **之前**执行，消除首屏闪色。

### 步骤 4（P1，清理硬编码暗色）

| 位置 | 处理 |
|------|------|
| `LoginView.vue` `.brand-pane` `#0B0C10` | 改 `var(--sp-ui-card)`；若希望保留品牌深色栏，则显式加 `.brand-pane { background: #0B0C10 }` 并限定为暗色模式（**需拍板**） |
| `LoginView.vue` `--sp-*` 回退值 | 步骤 3 生效后自动跟随 |
| `PlayerView.vue` `.mobile-player-overlay` `#0b0c10` | 改 `var(--sp-ui-body)` |
| `PlayerView.vue` `.mobile-queue-sheet` | 改 `var(--sp-ui-card)` |
| `PlayerPanel.vue` 封面占位 `radial-gradient(...#3a3a3a, #0a0a0a)` | 该处已有亮色兄弟选择器（L1677），确认 `.light` 分支命中即可 |

### 步骤 5（P2，可选）

- 主色统一：把 CSS 里硬编码的 `#18a058` 收敛到 `var(--sp-ui-primary)`（约 15 处），与 `#10B981` 并轨；
- 主题按钮升级为 light / dark / system 三态（`LayoutView.vue` L39）；
- `ambientBackground()`（`utils/color.js`）已有 light 分支，明亮模式下播放器舞台需实测对比度。

---

## 5. 验证清单

- [ ] 明亮模式：概览 / 曲库 / 下载 / 播放器 / 日志 / 设置 六个页面底色、卡片、文字全部为亮色，无暗块残留
- [ ] 明亮模式：登录页整体为亮色
- [ ] 明亮模式：`SongTable` / `PlayerQueue` / `PlayerView` 右侧栏（原本走 `--n-*` 的区域）卡片底色与次要文字正常显示
- [ ] 明亮模式：曲库来源卡片 `.active` 高亮（原本 `var(--card-color)` 失效）可见
- [ ] 明暗切换：快速连点无残留、无闪烁
- [ ] 刷新页面：不闪错主题（FOUC 已消除）
- [ ] `mode=system`：系统主题切换时应用跟随
- [ ] 移动端：地址栏 `theme-color` 跟随；底部 tab 栏配色正确
- [ ] 暗色模式回归：所有页面与修复前一致，无亮色泄漏

---

## 6. 工作量与风险

| 步骤 | 改动量 | 风险 |
|------|--------|------|
| 1. 分主题 overrides | ~20 行，1 文件 | 低 |
| 2. 注入 CSS 变量 | 新增 1 文件 + App.vue 5 行（+ 可选 50 处机械替换） | 低 |
| 3. themeStore 增强 | 1 文件重写 | 中（需兼容旧 localStorage 值） |
| 4. 清理硬编码 | 4 处 | 低 |
| 5. 主色并轨 / 三态 | ~20 处 | 低 |

**整体风险：低。** 步骤 1+2 即可解决问题，且为纯增量，不触碰任何业务逻辑。

---

## 7. 需要拍板

> 已于 2026-09-08 拍板，见 §8.1。以下为原始提问，保留存档。

1. ~~**登录页品牌栏**（`.brand-pane`）：明亮模式下改为浅色，还是保持深色作为品牌锚点？~~
2. ~~**主色**：统一到品牌 `#10B981`，还是沿用 Naive 默认 `#18a058`？~~
3. ~~**是否一步到位**：本次是否顺带把 50 处 `var(--n-*)` 全部替换为 `var(--sp-ui-*)`（不留别名）？~~

---

## 8. 最终决策与落地结果

### 8.1 三个拍板项

| 议题 | 决策 | 依据 |
|------|------|------|
| 登录页品牌栏 | 明亮模式随卡片走浅色；**暗色模式保留 `#0B0C10` 深底** | 深色栏在明亮页面中会形成硬边割裂，破坏整页统一的视觉基线；品牌感应由 LOGO 与主色承担，而不是靠一块深色底。暗色保留深底是为了不改动既有暗色观感 |
| 主色 | 统一到品牌 `#10B981`（暗色）；**明亮模式降级为品牌 700 `#047857`** | `#10B981` 配白字仅 2.65:1，不达 WCAG AA 4.5:1；`#047857` 为 5.55:1。亮色下 hover 继续**加深**（`#065F46`）而非提亮——交互态朝「远离页面底色」的方向走 |
| 变量迁移 | **一步到位，不留别名** | 88 处全量替换为 `--sp-ui-*` |

### 8.2 实际落地

**新增 `web/src/theme/tokens.js`（单一真相源）**

```
isDark ──┬──> buildNaiveOverrides()         → n-config-provider 的 theme-overrides
         ├──> buildCssVars()                → :root 上的 --sp-ui-*（teleport 弹层也能取到）
         ├──> documentElement.dataset.theme → 激活 brand.css 的 [data-theme] 分支
         └──> <meta name="theme-color">
```

与原方案的差异：CSS 变量改为**直接写到 `document.documentElement.style`**，而不是绑在 `App.vue` 根节点的 `:style` 上。原因是 Naive UI 的 modal / drawer / popover 会被 teleport 到 `body`，绑在 `.app-layout` 上取不到变量。

**`web/src/stores/theme.js`**：新增 `mode`（`system`/`light`/`dark`，默认跟随系统，兼容旧 `light`/`dark` 存储值）、`naiveTheme`、`naiveOverrides`；`watchEffect` 统一执行 DOM 副作用；监听 `prefers-color-scheme`；`init()` 由 `main.js` 在 `mount()` 之前调用，消除首屏闪色（FOUC）。

**迁移脚本 `scripts/migrate-theme-vars.js`**：一次性把 88 处死变量与硬编码主色替换为 token，共改动 15 个文件约 121 行。已执行（幂等，重跑无副作用）。

**顺带修掉的隐性 bug**

- `PlayerPanel.vue` 的 `--bg` 从未定义（`.lyrics-actions` 粘性底栏背景失效）→ 暗色 `rgba(10,11,15,.92)` / 亮色 `rgba(255,255,255,.94)`
- `PlayerView.vue` 移动端遮罩 `#0b0c10` → `var(--sp-ui-body)`
- `LoginView.vue` `.form-foot` 写死 `#6B7280` → `var(--sp-ui-text-3)`
- `LoginView.vue` 卡片阴影在亮色下过重 → 亮色 `rgba(15,23,42,.12)`，暗色保留原 `.5` 黑

### 8.3 遗留项（不在本次范围）

- 概览页 KPI / 快捷入口的分类配色（`#0f766e` `#1d4ed8` `#be123c` `#b45309` 等）是按浅底挑的，暗色下对卡片底色约 3.3:1，仅够非文本对比（3:1）。若需正文级可读，应补一套暗色版分类色。
- 主题按钮仍是二态（light/dark）。store 已支持 `system`，UI 未暴露三态切换。
