/**
 * 把 src/theme/tokens.js 派生出的 CSS 变量同步进原型页的 <style id="sp-tokens"> 块。
 *
 * 为什么需要这一步：原型页要能**脱离构建、直接双击打开**（不依赖 vite dev / 后端），
 * 于是没法 import tokens.js；但设计 Token 只能有一个真相源，不允许在原型里手抄一份数值。
 * 所以由本脚本生成，原型页只声明「这块是生成的」。
 *
 * 用法：node scripts/gen-prototype-tokens.mjs
 */
import { readFile, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { buildCssVars } from '../src/theme/tokens.js'

const here = dirname(fileURLToPath(import.meta.url))
const target = join(here, '..', 'prototype', 'sidebar-motion.html')
const START = '/* @tokens:start */'
const END = '/* @tokens:end */'

function block(selector, vars) {
  const body = Object.entries(vars)
    .map(([k, v]) => `${k}:${v}`)
    .join(';')
  return `${selector}{${body}}`
}

const light = buildCssVars(false)
const dark = buildCssVars(true)

const generated = [
  `/* 由 scripts/gen-prototype-tokens.mjs 从 src/theme/tokens.js 生成 —— 不要手改，改 tokens.js 后重跑脚本 */`,
  `/* 共 ${Object.keys(light).length} 个变量 */`,
  block(':root', light),
  block('html[data-theme="dark"]', dark),
].join('\n')

const html = await readFile(target, 'utf8')
const start = html.indexOf(START)
const end = html.indexOf(END)

if (start === -1 || end === -1 || end < start) {
  throw new Error(`原型页缺少 ${START} / ${END} 标记，无法注入 Token`)
}

const next = html.slice(0, start + START.length) + '\n' + generated + '\n' + html.slice(end)
await writeFile(target, next, 'utf8')
console.log(`已同步 ${Object.keys(light).length} 个 Token 变量 → web/prototype/sidebar-motion.html`)
