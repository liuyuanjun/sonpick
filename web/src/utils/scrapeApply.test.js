import assert from 'node:assert/strict'
import test from 'node:test'

import { formatSongFileSize, normalizeSongFiles, shouldSelectScrapeField } from './scrapeApply.js'

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

test('格式化完整歌曲文件列表并保留长路径', () => {
  const longPath = `/music/${'很长的目录/'.repeat(20)}song.flac`
  const files = normalizeSongFiles([
    { id: 1, format: 'flac', local_path: longPath, file_size: 1536 },
    { id: 2, format: 'mp3', webdav_path: '/remote/song.mp3', file_size: 2 * 1024 * 1024 },
  ])
  assert.equal(files.length, 2)
  assert.equal(files[0].displayPath, longPath)
  assert.equal(files[0].displayStatus, '可写入本地文件')
  assert.equal(files[1].displaySource, 'WebDAV')
  assert.equal(files[1].displayStatus, '远端只读，未写入')
})

test('歌曲文件列表支持空值和文件大小格式化', () => {
  assert.deepEqual(normalizeSongFiles(null), [])
  assert.equal(formatSongFileSize(512), '512 B')
  assert.equal(formatSongFileSize(1536), '1.5 KB')
  assert.equal(formatSongFileSize(2 * 1024 * 1024), '2.00 MB')
  assert.equal(formatSongFileSize(undefined), '大小未知')
})
