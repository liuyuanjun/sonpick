import { createApp } from 'vue'
import { createPinia } from 'pinia'
import {
  create,
  NAlert,
  NButton,
  NButtonGroup,
  NCard,
  NCheckbox,
  NCheckboxGroup,
  NConfigProvider,
  NDataTable,
  NDivider,
  NDropdown,
  NEllipsis,
  NForm,
  NFormItem,
  NGi,
  NGrid,
  NH1,
  NH2,
  NH3,
  NIcon,
  NInput,
  NInputNumber,
  NLayout,
  NLayoutContent,
  NLayoutFooter,
  NLayoutHeader,
  NLayoutSider,
  NLoadingBarProvider,
  NMenu,
  NMessageProvider,
  NDialogProvider,
  NDrawer,
  NDrawerContent,
  NBadge,
  NModal,
  NBreadcrumb,
  NBreadcrumbItem,
  NCollapseTransition,
  NEmpty,
  NResult,
  NList,
  NListItem,
  NThing,
  NP,
  NPageHeader,
  NPagination,
  NProgress,
  NRadio,
  NRadioButton,
  NRadioGroup,
  NSelect,
  NSlider,
  NSpace,
  NSpin,
  NSwitch,
  NTabPane,
  NTabs,
  NTag,
  NText,
  NTooltip,
  darkTheme,
  lightTheme,
} from 'naive-ui'
import App from './App.vue'
import router from './router'
import { useThemeStore } from '@/stores/theme'
// 项目自有组件（Naive 未提供的能力，必须在此显式注册，否则模板里会渲染成未知元素）
import SpTable from '@/components/SpTable.vue'
import StateEmpty from '@/components/StateEmpty.vue'

// Inter 自托管（latin 子集，5 字重共约 120KB）。
// 中文不在 webfont 内，走 FONT.ui 里的系统 CJK 栈 —— 理由见 theme/tokens.js 的 FONT 注释。
import '@fontsource/inter/latin-400.css'
import '@fontsource/inter/latin-500.css'
import '@fontsource/inter/latin-600.css'
import '@fontsource/inter/latin-700.css'
import '@fontsource/inter/latin-800.css'
// 全局基线：Token 落地 + 消除 UA 默认值渗出 + 工具类 + 可访问性
import './styles/base.css'

const naive = create({
  components: [
    NAlert, NButton, NButtonGroup, NCard, NCheckbox, NCheckboxGroup, NConfigProvider, NDataTable, NDivider,
  NDropdown, NEllipsis,
    NForm, NFormItem, NGi, NGrid, NH1, NH2, NH3, NIcon, NInput, NInputNumber,
    NLayout, NLayoutContent, NLayoutFooter, NLayoutHeader, NLayoutSider,
    NLoadingBarProvider, NMenu, NMessageProvider,
  NDialogProvider, NModal,
    NBreadcrumb, NBreadcrumbItem, NCollapseTransition, NDrawer, NDrawerContent, NBadge, NEmpty, NResult, NList, NListItem, NThing,
    NP, NPageHeader,
    NPagination, NProgress, NRadio, NRadioButton, NRadioGroup, NSelect, NSlider, NSpace,
    NSpin, NSwitch, NTabPane, NTabs, NTag, NText, NTooltip,
  ],
})

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(naive)

/*
  项目自有组件必须走 app.component() 显式注册，**不要塞进上面的 create({ components })**。
  原因（实测踩过）：naive-ui 的 create() 只做一件事——把组件注册成 `'N' + component.name`。
  SFC 用 <script setup> 时没有 name，于是会被注册成 `Nundefined`；
  模板里的 <sp-table> 解析不到，被当成未知元素渲染，**且控制台不报错**，
  表现为「表格整块消失」。这类静默失败只能靠实测 DOM（查 tagName 里有没有 sp-*）发现。
*/
app.component('SpTable', SpTable)
app.component('StateEmpty', StateEmpty)

// 挂载前先定主题：写 data-theme 与 :root 变量，避免首屏闪一下错误配色
useThemeStore().init()

app.mount('#app')
