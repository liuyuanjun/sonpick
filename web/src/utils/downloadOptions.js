// 下载偏好与曲库重复策略的选项清单：导入下载 / 歌单链接导入共用，勿再各写一份
export const FORMAT_PREFER_OPTIONS = [
  { label: '任意', value: 'any' },
  { label: 'FLAC', value: 'flac' },
  { label: 'MP3', value: 'mp3' },
  { label: 'M4A', value: 'm4a' },
]

export const DUPLICATE_ACTION_OPTIONS = [
  { label: '已存在则跳过', value: 'skip' },
  { label: '仍下载为新版本', value: 'keep_both' },
]
