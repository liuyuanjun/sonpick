import assert from 'node:assert/strict'
import test from 'node:test'

import { DOWNLOAD_SOURCES, sourceLabel } from './downloadSources.js'

test('下载源展示名：用平台简称，不加「音乐」后缀', () => {
  // 展示名同时出现在下载来源 chips、搜索结果「来源」列和后端错误提示里
  assert.deepEqual(
    DOWNLOAD_SOURCES.map((s) => s.label),
    ['QQ', '网易云', '咪咕', '酷狗', '酷我', '千千'],
  )
  for (const s of DOWNLOAD_SOURCES) {
    assert.ok(!s.label.includes('音乐'), `${s.value} 的展示名不应带「音乐」：${s.label}`)
  }
})

test('下载源 key：与后端 SOURCE_LABELS / DEFAULT_DOWNLOAD_SOURCES 一致', () => {
  assert.deepEqual(
    DOWNLOAD_SOURCES.map((s) => s.value),
    [
      'QQMusicClient',
      'NeteaseMusicClient',
      'MiguMusicClient',
      'KugouMusicClient',
      'KuwoMusicClient',
      'QianqianMusicClient',
    ],
  )
})

test('sourceLabel：命中返回展示名，未登记 key 原样返回便于排查', () => {
  assert.equal(sourceLabel('KugouMusicClient'), '酷狗')
  assert.equal(sourceLabel('NeteaseMusicClient'), '网易云')
  assert.equal(sourceLabel('NewSourceClient'), 'NewSourceClient')
  assert.equal(sourceLabel(''), '')
  assert.equal(sourceLabel(undefined), '')
})
