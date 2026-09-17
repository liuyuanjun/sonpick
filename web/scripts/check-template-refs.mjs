/**
 * 未解析模板标识符检查（"编译通过、运行期炸"的那一类 bug）。
 *
 * 背景：Vue 3 `<script setup>` 下模板标识符解析到 setup 作用域。模板里调用了没
 * import / 没声明的函数（如 `formatFileSize`）时，`vite build` 完全通过，但渲染时
 * 抛 `TypeError: _ctx.xxx is not a function`，被调用的那一块子树直接渲染失败 ——
 * 表现为「弹窗打开后一片空白 / 只剩占位文案」，且没有任何构建期提示。
 * 0.15.1-rc5 ~ rc16 期间「整理到标准路径」弹窗空白即为此原因。
 *
 * 用法（必须在 web/ 目录下运行，才能解析到 @vue/compiler-sfc）：
 *   npm run check:template-refs        # 检查 src/
 *   node scripts/check-template-refs.mjs src
 *
 * 判定口径：编译产物里出现 `_ctx.<name>(`（即以函数调用形式使用）而 `<name>` 既不在
 * script setup 声明里、也不在模板局部变量 / JS 全局里 → 报错。仅以数据处理形式（未加
 * 括号）出现的未声明标识符不报，避免误伤模板作用域推断不到的边界情况。
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

let problems = 0
for (const file of walkDir(ROOT)) {
  const src = readFileSync(file, 'utf8')
  const { descriptor, errors } = parseSfc(src, { filename: file })
  if (errors?.length || !descriptor.template || !descriptor.scriptSetup) continue

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
    console.log(`${relative(process.cwd(), file)}: 未声明的函数调用 → ${unknown.join(', ')}`)
  }
}

if (problems) {
  console.log(`\n共 ${problems} 处未解析的模板函数调用，运行期会抛 ReferenceError（弹窗 / 子树渲染失败）。`)
  process.exit(1)
}
console.log('未发现未解析的模板函数调用。')
