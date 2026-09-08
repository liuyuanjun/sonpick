import { createApp } from 'vue'
import { createPinia } from 'pinia'
import {
  create,
  NAlert,
  NButton,
  NButtonGroup,
  NCard,
  NCheckbox,
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

const naive = create({
  components: [
    NAlert, NButton, NButtonGroup, NCard, NCheckbox, NConfigProvider, NDataTable, NDivider,
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

// 挂载前先定主题：写 data-theme 与 :root 变量，避免首屏闪一下错误配色
useThemeStore().init()

app.mount('#app')
