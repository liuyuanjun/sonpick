/**
 * 一次性迁移脚本：把历史遗留的「未定义 CSS 变量」与硬编码主色
 * 统一替换为 @/theme/tokens 派生的 --sp-ui-* 变量。
 *
 * 用法：node scripts/migrate-theme-vars.js   （--dry 只报告不落盘）
 */
const fs = require('fs')
const path = require('path')

const ROOT = path.resolve(__dirname, '..', 'web', 'src')
const DRY = process.argv.includes('--dry')

/** 顺序敏感：先长后短，先复合后单值 */
const RULES = [
  ['var(--card-color, var(--n-card-color))', 'var(--sp-ui-card)'],
  ['var(--n-text-color-3', 'var(--sp-ui-text-3'],
  ['var(--n-text-color-2', 'var(--sp-ui-text-2'],
  ['var(--n-text-color)', 'var(--sp-ui-text-1)'],
  ['var(--n-card-color)', 'var(--sp-ui-card)'],
  ['var(--n-border-color)', 'var(--sp-ui-border)'],
  ['var(--n-body-color)', 'var(--sp-ui-body)'],
  ['var(--n-primary-color)', 'var(--sp-ui-primary)'],
  ['var(--n-color)', 'var(--sp-ui-card)'],
  ['var(--n-success-color, #18a058)', 'var(--sp-ui-success)'],
  ['var(--n-error-color, #d03050)', 'var(--sp-ui-error)'],
  // 以上为精确匹配；以下几条用前缀匹配，覆盖带 fallback 的写法（如 var(--border-color, rgba(...))）
  ['var(--card-color', 'var(--sp-ui-card'],
  ['var(--primary-color', 'var(--sp-ui-primary'],
  ['var(--border-color', 'var(--sp-ui-border'],
  ['var(--text-color-3', 'var(--sp-ui-text-3'],
  ['var(--body-color', 'var(--sp-ui-body'],
]

/** rgba(24,160,88,a) → color-mix(in srgb, var(--sp-ui-primary) N%, transparent) */
function rgbaToPrimaryMix(src) {
  return src.replace(
    /rgba\(\s*24\s*,\s*160\s*,\s*88\s*,\s*([0-9]*\.?[0-9]+)\s*\)/g,
    (_m, alpha) => {
      const pct = Math.round(parseFloat(alpha) * 100)
      return `color-mix(in srgb, var(--sp-ui-primary) ${pct}%, transparent)`
    },
  )
}

function apply(src) {
  let out = src
  for (const [from, to] of RULES) {
    out = out.split(from).join(to)
  }
  out = rgbaToPrimaryMix(out)
  out = out.replace(/\brgb\(\s*24\s*,\s*160\s*,\s*88\s*\)/g, 'var(--sp-ui-primary)')
  out = out.replace(/#18a058/gi, 'var(--sp-ui-primary)')
  return out
}

function walk(dir, acc = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) walk(full, acc)
    else if (/\.(vue|js|ts)$/.test(entry.name)) acc.push(full)
  }
  return acc
}

let changed = 0
let hits = 0
for (const file of walk(ROOT)) {
  const src = fs.readFileSync(file, 'utf8')
  const out = apply(src)
  if (out !== src) {
    const diff = src.split('\n').filter((line, i) => out.split('\n')[i] !== line).length
    hits += diff
    changed += 1
    console.log(`${path.relative(ROOT, file)}  (${diff} 行)`)
    if (!DRY) fs.writeFileSync(file, out)
  }
}
console.log(`\n共 ${changed} 个文件、${hits} 行被修改${DRY ? '（dry-run，未落盘）' : ''}`)
