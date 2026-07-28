import assert from 'node:assert/strict'
import test from 'node:test'

import { shouldSelectScrapeField } from './scrapeApply.js'

test('旧封面不存在且候选封面有效时默认开启', () => {
  assert.equal(shouldSelectScrapeField({
    key: 'cover',
    currentValue: '',
    newValue: 'https://example.com/cover.jpg',
    currentCoverExists: false,
  }), true)
})

test('旧封面存在时默认关闭封面更改', () => {
  assert.equal(shouldSelectScrapeField({
    key: 'cover',
    currentValue: '/music/cover.jpg',
    newValue: 'https://example.com/new-cover.jpg',
    currentCoverExists: true,
  }), false)
})

test('候选封面为空时默认关闭', () => {
  assert.equal(shouldSelectScrapeField({
    key: 'cover',
    newValue: '   ',
    currentCoverExists: false,
  }), false)
})

test('普通字段仅在非空且变化时默认开启', () => {
  assert.equal(shouldSelectScrapeField({ key: 'title', currentValue: '旧标题', newValue: '新标题' }), true)
  assert.equal(shouldSelectScrapeField({ key: 'title', currentValue: '标题', newValue: ' 标题 ' }), false)
  assert.equal(shouldSelectScrapeField({ key: 'title', currentValue: '标题', newValue: '' }), false)
})
