import assert from 'node:assert/strict'
import test from 'node:test'

import {
  formatClock,
  formatDateTime,
  formatDurationText,
  formatFileSize,
  formatRelativeTime,
  secondsBetween,
} from './format.js'

test('体积：B / KB / MB 沿用既有口径', () => {
  assert.equal(formatFileSize(512), '512 B')
  assert.equal(formatFileSize(1536), '1.5 KB')
  assert.equal(formatFileSize(2 * 1024 * 1024), '2.00 MB')
})

test('体积：超过 MB 不再溢出成 1024.00 MB', () => {
  assert.equal(formatFileSize(1024 ** 3), '1.00 GB')
  assert.equal(formatFileSize(2.5 * 1024 ** 3), '2.50 GB')
  assert.equal(formatFileSize(1024 ** 4), '1.00 TB')
})

test('体积：非法值与 0 走 fallback，调用方可自定义', () => {
  assert.equal(formatFileSize(undefined), '大小未知')
  assert.equal(formatFileSize(-1), '大小未知')
  assert.equal(formatFileSize(0, { fallback: '0 B' }), '0 B')
  assert.equal(formatFileSize(null, { fallback: '-' }), '-')
})

test('时间轴：mm:ss，超过一小时进位 h:mm:ss', () => {
  assert.equal(formatClock(0), '0:00')
  assert.equal(formatClock(65), '1:05')
  assert.equal(formatClock(215), '3:35')
  assert.equal(formatClock(3725), '1:02:05')
  assert.equal(formatClock(null), '0:00')
})

test('时长文案：默认带秒，总时长场景可关掉秒', () => {
  assert.equal(formatDurationText(42), '42 秒')
  assert.equal(formatDurationText(125), '2 分 5 秒')
  assert.equal(formatDurationText(3725), '1 小时 2 分 5 秒')
  assert.equal(formatDurationText(3725, { withSeconds: false }), '1 小时 2 分')
  assert.equal(formatDurationText(125, { withSeconds: false }), '2 分钟')
  assert.equal(formatDurationText(0), '0 秒')
  assert.equal(formatDurationText(null), '-')
})

test('相对时间：秒 / 分钟 / 小时', () => {
  assert.equal(formatRelativeTime(5), '5 秒前')
  assert.equal(formatRelativeTime(59), '59 秒前')
  assert.equal(formatRelativeTime(90), '1 分钟前')
  assert.equal(formatRelativeTime(3900), '1 小时 5 分钟前')
  assert.equal(formatRelativeTime(null), '')
})

test('时间差：endAt 省略时取当下；非法输入返回 null', () => {
  const start = new Date(Date.now() - 90_000).toISOString()
  assert.equal(secondsBetween(start), 90)
  assert.equal(secondsBetween(null), null)
  assert.equal(secondsBetween('不是时间'), null)
})

test('时刻：秒可选、年可选、非法值走 fallback', () => {
  const iso = '2026-09-16T10:20:30'
  assert.match(formatDateTime(iso), /09\/16.*10:20:30/)
  assert.match(formatDateTime(iso, { withSeconds: false }), /09\/16.*10:20(?!:)/)
  assert.match(formatDateTime(iso, { withYear: true }), /2026/)
  assert.equal(formatDateTime(null), '—')
  assert.equal(formatDateTime('乱码', { fallback: '-' }), '-')
})
