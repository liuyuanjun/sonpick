/**
 * 未解析模板标识符检查（"编译通过、运行期炸"的那一类 bug）。
 *
 * ══ 检查一：未被声明的函数调用 ══
 * 背景：Vue 3 `<script setup>` 下模板标识符解析到 setup 作用域。模板里调用了没
 * import / 没声明的函数（如 `formatFileSize`）时，`vite build` 完全通过，但渲染时
 * 抛 `TypeError: _ctx.xxx is not a function`，被调用的那一块子树直接渲染失败 ——
 * 表现为「弹窗打开后一片空白 / 只剩占位文案」，且没有任何构建期提示。
 * 0.15.1-rc5 ~ rc16 期间「整理到标准路径」弹窗空白即为此原因。
 *
 * ══ 检查二：未注册的组件标签 ══
 * 同一类静默失败：模板里写了未注册的组件标签（`<n-popconfirm>`、`<person />`）时，
 * Vue 只打一条 warning，然后把未知元素**原样渲染** —— 插槽内容以纯文本摊在页面上、
 * 交互全部失效，而 build 一样不报错。实测过的两例：
 *   · `SettingsView` 的「确认退出登录」浮层从没出现过（文案「确认退出当前登录吗?」直接显示在账户区）
 *   · `PlayerView` 的空状态图标位置长期空白
 *
 * 判定口径：模板元素标签（先去掉注释与属性值）若不是原生 HTML/SVG 标签、不是 Vue 内置组件，
 * 也不是本文件 import/声明的组件，就必须能在 `src/main.js` 的全局注册表里找到：
 *   · `create({ components: [NAlert, …] })` —— naive 实际注册的是 `'N' + component.name`，
 *     绝大多数与导出标识符同名，已知不同名的见 NAIVE_REGISTERED_AS
 *   · `app.component('SpTable', …)` 的字面名
 *
 * 用法（必须在 web/ 目录下运行，才能解析到 @vue/compiler-sfc）：
 *   npm run check:template-refs        # 检查 src/
 *   node scripts/check-template-refs.mjs src
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { compileTemplate, parse as parseSfc } from '@vue/compiler-sfc'

const ROOT = process.argv[2] || 'src'

const JS_GLOBALS = new Set([
  'Math', 'Date', 'JSON', 'Object', 'Array', 'Number', 'String', 'Boolean', 'RegExp',
  'Map', 'Set', 'Promise', 'Intl', 'Error', 'Symbol', 'BigInt', 'parseInt', 'parseFloat',
  'isNaN', 'isFinite', 'encodeURIComponent', 'decodeURIComponent', 'undefined', 'null',
  'true', 'false', 'NaN', 'Infinity', 'console', 'window', 'document', 'arguments',
  '$props', '$emit', '$slots', '$attrs', '$refs',
])

function walkDir(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walkDir(full, out)
    else if (name.endsWith('.vue')) out.push(full)
  }
  return out
}

/** script setup 里声明的标识符：import（含 as / 解构）、const/let/var/function/class、解构赋值。 */
function collectScriptBindings(script) {
  const names = new Set()
  const add = (n) => n && names.add(n)

  for (const m of script.matchAll(/import\s+([^'"]+?)\s+from\s*['"]/g)) {
    const clause = m[1].trim()
    const brace = clause.match(/\{([\s\S]*?)\}/)
    if (brace) {
      for (const part of brace[1].split(',')) {
        const piece = part.trim()
        if (!piece) continue
        const [orig, alias] = piece.split(/\s+as\s+/)
        add((alias || orig).trim())
      }
    }
    const def = clause.replace(/\{[\s\S]*?\}/g, '').replace(/,/g, ' ').trim()
    if (def && !def.startsWith('*')) add(def)
  }

  for (const m of script.matchAll(/^(?:export\s+)?(?:async\s+)?(?:const|let|var|function|class)\s+([A-Za-z_$][\w$]*)/gm)) {
    add(m[1])
  }
  for (const m of script.matchAll(/^(?:export\s+)?(?:const|let|var)\s*\{([^}]*)\}\s*=/gm)) {
    for (const part of m[1].split(',')) {
      const [orig, alias] = part.split(':')
      add((alias || orig || '').replace(/\.\.\./, '').trim())
    }
  }
  return names
}

/** 模板局部变量：v-for 别名与 slot props。 */
function collectTemplateLocals(template) {
  const locals = new Set()
  for (const m of template.matchAll(/v-for\s*=\s*"([^"]+)"/g)) {
    const head = m[1].split(/\bin\b/)[0]
    for (const piece of head.split(',')) {
      const name = piece.replace(/[()]/g, '').trim()
      if (/^[A-Za-z_$][\w$]*$/.test(name)) locals.add(name)
    }
  }
  for (const m of template.matchAll(/#default\s*=\s*"\{?([^}"]*)\}?"/g)) {
    for (const piece of m[1].split(',')) {
      const name = piece.trim()
      if (/^[A-Za-z_$][\w$]*$/.test(name)) locals.add(name)
    }
  }
  for (const m of template.matchAll(/v-slot(?::[^\s=]+)?\s*=\s*"([A-Za-z_$][\w$]*)"/g)) {
    locals.add(m[1])
  }
  return locals
}

function compileAndCollectRefs(template, filename) {
  // 不带 bindingMetadata 编译：setup 作用域里的标识符会统一落到 `_ctx.<name>`
  const { code } = compileTemplate({ source: template, filename, id: 'check' })
  return { code, refs: [...new Set([...code.matchAll(/_ctx\.([A-Za-z_$][\w$]*)/g)].map((m) => m[1]))] }
}

/* ══════════════════════════════════════════════════════════════════════
   检查二所需的判定表与辅助
   ══════════════════════════════════════════════════════════════════════ */

/** Vue 内置组件 + vue-router 注册的全局组件（都不需要自己注册） */
const VUE_BUILTINS = new Set([
  'component', 'slot', 'template', 'transition', 'transition-group',
  'keep-alive', 'teleport', 'suspense', 'router-view', 'router-link',
])

/** 原生 HTML + 内联 SVG 元素：模板里这些标签不需要注册 */
const NATIVE_TAGS = new Set([
  // HTML
  'a', 'abbr', 'address', 'area', 'article', 'aside', 'audio', 'b', 'base', 'bdi', 'bdo',
  'blockquote', 'body', 'br', 'button', 'canvas', 'caption', 'cite', 'code', 'col', 'colgroup',
  'data', 'datalist', 'dd', 'del', 'details', 'dfn', 'dialog', 'div', 'dl', 'dt', 'em', 'embed',
  'fieldset', 'figcaption', 'figure', 'footer', 'form', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'head', 'header', 'hgroup', 'hr', 'html', 'i', 'iframe', 'img', 'input', 'ins', 'kbd', 'label',
  'legend', 'li', 'link', 'main', 'map', 'mark', 'menu', 'meta', 'meter', 'nav', 'noscript',
  'object', 'ol', 'optgroup', 'option', 'output', 'p', 'picture', 'pre', 'progress', 'q', 'rp',
  'rt', 'ruby', 's', 'samp', 'script', 'search', 'section', 'select', 'small', 'source', 'span',
  'strong', 'style', 'sub', 'summary', 'sup', 'table', 'tbody', 'td', 'textarea', 'tfoot', 'th',
  'thead', 'time', 'title', 'tr', 'track', 'u', 'ul', 'var', 'video', 'wbr',
  // SVG（StateEmpty / PlayerArt 等有内联 SVG）
  'svg', 'g', 'defs', 'desc', 'symbol', 'use', 'image', 'switch', 'path', 'rect', 'circle',
  'ellipse', 'line', 'polyline', 'polygon', 'text', 'tspan', 'textPath', 'marker', 'stop',
  'pattern', 'clipPath', 'mask', 'filter', 'feGaussianBlur', 'feOffset', 'feBlend',
  'feColorMatrix', 'feMerge', 'feMergeNode', 'feDropShadow', 'animate', 'animateTransform',
  'linearGradient', 'radialGradient', 'foreignObject',
])

/**
 * naive 的 `create()` 注册的是 `'N' + component.name`，多数与导出标识符同名。
 * 实测过的不同名者：`NA`（Anchor）的 name 是 `'Anchor'` → 注册成 `NAnchor`，
 * 所以模板里必须写 `<n-anchor>`；写 `<n-a>` 永远解析不到（SettingsView 曾这么写）。
 */
const NAIVE_REGISTERED_AS = { NA: 'NAnchor' }

function kebabToPascal(tag) {
  return tag.replace(/(^|-)([a-z0-9])/g, (_, __, ch) => ch.toUpperCase())
}

/** 从 src/main.js 推导全局注册表：create({components:[...]}) 与 app.component('X', ...) */
function collectGlobalComponents(mainPath) {
  const registered = new Set()
  let src = ''
  try {
    src = readFileSync(mainPath, 'utf8')
  } catch {
    return null   // 拿不到 main.js 就跳过检查二，避免误报
  }
  for (const m of src.matchAll(/components\s*:\s*\[([^\]]*)\]/g)) {
    for (const piece of m[1].split(',')) {
      const id = piece.trim()
      if (/^[A-Z]\w*$/.test(id)) registered.add(NAIVE_REGISTERED_AS[id] || id)
    }
  }
  for (const m of src.matchAll(/\.component\(\s*['"]([\w-]+)['"]/g)) {
    registered.add(m[1])
  }
  return registered
}

/** 去掉注释与属性值，避免把 `v-if="a<b"`、`d="M0 0"` 这类内容误当标签扫到 */
function stripTemplateNoise(template) {
  return template
    .replace(/<!--[\s\S]*?-->/g, ' ')
    .replace(/=("[^"]*"|'[^']*')/g, '=')
}

function collectTags(template) {
  return [...new Set([...stripTemplateNoise(template).matchAll(/<([a-zA-Z][\w-]*)[\s/>]/g)].map((m) => m[1]))]
}

const globals = collectGlobalComponents(join(ROOT, 'main.js'))
if (!globals) console.log('!! 读不到 src/main.js，跳过「未注册组件标签」检查')

let problems = 0
for (const file of walkDir(ROOT)) {
  const src = readFileSync(file, 'utf8')
  const { descriptor, errors } = parseSfc(src, { filename: file })
  if (errors?.length || !descriptor.template) continue
  const label = relative(process.cwd(), file)

  /* 检查一：未声明的函数调用（编译产物里被当作函数调用的 `_ctx.<name>`） */
  if (descriptor.scriptSetup) {
    const bindings = collectScriptBindings(descriptor.scriptSetup.content)
    const locals = collectTemplateLocals(descriptor.template.content)
    const { code, refs } = compileAndCollectRefs(descriptor.template.content, file)

    const unknown = refs.filter(
      (name) =>
        !bindings.has(name) &&
        !locals.has(name) &&
        !JS_GLOBALS.has(name) &&
        new RegExp(`_ctx\\.${name}\\s*\\(`).test(code),
    )
    if (unknown.length) {
      problems += unknown.length
      console.log(`${label}: 未声明的函数调用 → ${unknown.join(', ')}`)
    }
  }

  /* 检查二：未注册的组件标签（Vue 会把它当未知元素原样渲染，不报错） */
  if (globals) {
    const tagBindings = new Set([
      ...collectScriptBindings(descriptor.scriptSetup?.content || ''),
      ...collectScriptBindings(descriptor.script?.content || ''),
    ])
    const unresolvedTags = collectTags(descriptor.template.content).filter((tag) => {
      if (NATIVE_TAGS.has(tag) || VUE_BUILTINS.has(tag)) return false
      const pascal = kebabToPascal(tag)
      return !globals.has(pascal) && !globals.has(tag) && !tagBindings.has(pascal) && !tagBindings.has(tag)
    })
    if (unresolvedTags.length) {
      problems += unresolvedTags.length
      console.log(`${label}: 未注册的组件标签 → <${unresolvedTags.join('>, <')}>`)
    }
  }
}

if (problems) {
  console.log(`\n共 ${problems} 处问题：未声明的函数调用会在运行期抛 ReferenceError；未注册的组件标签会被当成未知元素渲染（插槽内容变纯文本、交互失效）。`)
  process.exit(1)
}
console.log('未发现未解析的模板函数调用与未注册的组件标签。')
