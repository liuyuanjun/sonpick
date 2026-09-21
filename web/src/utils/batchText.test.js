import test from 'node:test'
import assert from 'node:assert/strict'

import { countBatchLines, parseBatchLines } from './batchText.js'

test('parseBatchLines 去空行并保序去重', () => {
  const text = '晴天 - 周杰伦\n\n  海阔天空 - Beyond \n晴天 - 周杰伦\n平凡之路 - 朴树\n'
  assert.deepEqual(parseBatchLines(text), ['晴天 - 周杰伦', '海阔天空 - Beyond', '平凡之路 - 朴树'])
})

test('parseBatchLines 空输入返回空数组', () => {
  assert.deepEqual(parseBatchLines(''), [])
  assert.deepEqual(parseBatchLines(null), [])
  assert.deepEqual(parseBatchLines('  \n \n'), [])
})

test('countBatchLines 返回原始行数与去重后首数', () => {
  assert.deepEqual(countBatchLines('a\nb\na\n\nc'), { raw: 4, unique: 3 })
  assert.deepEqual(countBatchLines(''), { raw: 0, unique: 0 })
})
