# 元数据 L0 与封面规范改造

> 用途：后续 Agent / 协作者可按本文继续实施，无需重新梳理讨论。
>
> 起始版本：`0.15.0-rc5` → 已落地预发：`0.15.0-rc9`（本轮以 bugfix/行为修正为主，只升 rc）。
>
> 文档状态：设计定稿；**P0 已在 0.15.0-rc6 落地**，`0.15.0-rc7` 修复封面失败误杀标签写穿并补齐错误日志/前端摘要，`0.15.0-rc8` 修复 NAS 出网问题并支持浏览器提交封面字节，`0.15.0-rc9` 支持刮削新值手动编辑；P1/P2 可后续迭代。

---

## 1. 问题陈述

多格式、多 SongFile 版本（如 WMA + 已转码 MP3）下，展示与刮削被绑在「某一物理格式能否写内嵌标签」上，导致：

1. WMA 等格式 `write_audio_tags` 返回空 → `apply_metadata_to_song_files` 整版本 `failed`。
2. 侧车 `cover.jpg` 可能已写成功，但成功语义仍算失败，UI 提示「写入失败」。
3. 列表/播放器以 `Song.cover_path` 真值闸门决定是否请求 `/cover`；聚合路径为空或不稳则无封面。
4. 转码 MP3 不回填 `SongFile.cover_path` / `lrc_path`，写穿不完整。
5. 读路径三套优先级并存（`resolve_song_meta` 文件优先、刮削 DB 优先、整理文档又一套）。

根因：**没有统一的「应用规范真相（L0）」**；展示、成功判定、文件写穿耦合在一起。

---

## 2. 目标模型（三层）

```text
L0  应用规范真相（UI / 刮削成功 / 播放器只认）
    - 文本：Song.title/artist/album/year/genre
    - 封面：data/covers/by-hash/{sha}.{ext} + Song.cover_path 指针
    - 歌词：仍按 song 的 lrc 指针 + provenance（正文不强制进 DB）
    - 锁与状态：meta_locked / meta_confidence / scrape_status

L1  可携带侧车（格式无关，跟曲库目录走）
    - Artist/Album/cover.jpg
    - 同 stem .lrc
    - 所有可写本地 SongFile best-effort；WebDAV 只读 skipped

L2  内嵌标签（格式相关）
    - 仅能力矩阵支持的格式（mp3/flac/m4a…）
    - 不支持 → unsupported（不是 failed）
    - 永远不单独决定刮削是否成功
```

### 成功语义（硬约束）

```text
刮削/保存成功  ≜  L0 提交成功
文件结果        ≜  L1/L2 的 written | skipped | unsupported | failed
UI 展示         ≜  永远 L0
ok              ≜  L0 成功（即使全部版本 unsupported/skipped 仍可为 true）
partial         ≜  L0 成功且存在 L1/L2 failed（真正 I/O 失败）
```

**禁止**：把「格式不支持内嵌」当成整次刮削失败。

---

## 3. 封面存储：内容寻址 + 专辑键共享（不上 Album 表）

### 3.1 为什么不用 `songs/{song_id}.jpg` 作为默认唯一策略

正规专辑多轨共用同一封面图时会 N 倍复制；改专辑封面也要更新 N 个文件。

### 3.2 为什么不用「艺术家-专辑.jpg」当文件名主键

- artist/album 随刮削变化 → 路径漂移
- 同名专辑、合辑、edition 碰撞
- 字符清洗后与显示名不一致

可用作 **分组 key**，不可作存储权威路径。

### 3.3 为什么本轮不上 Album 表

Album 实体能挂发行信息、MBID、整专编辑，但是：

- 专辑身份自动合并极易误伤（多源扫描/下载/转码）
- 全库 Song 扁平模型迁移面大
- 单曲封面、VA、edition 仍需要 Song 级覆盖

**去重不依赖 Album 表**。中期做「专辑产品」时再把 `album_key` 升级为 `album_id`。

### 3.4 规范落盘

```text
data/covers/
  by-hash/
    {sha256前16或全量}.{jpg|png|webp}   # 像素内容一份只存一次
  cache/                                 # 既有 path-keyed 临时缓存，可保留
  songs/                                 # 历史 song_id 缓存；迁移后可逐步清空
```

DB：

- `Song.cover_path` → 稳定指向 `data/covers/by-hash/...`（兼容现有字段，本轮不强制加 `cover_hash` 列）
- 可选内存/服务层：`album_cover_key = sha1(norm(artist) + "\0" + norm(album))`
- 空 / Unknown Album：**不进共享桶**，只挂当前 Song

### 3.5 写入规则

1. 得到封面 bytes（URL 下载 / 本地复制 / 内嵌提取）
2. `hash = sha256(bytes)`，写入 `by-hash/{hash}{ext}`（已存在则跳过写盘）
3. `song.cover_path = 该路径`（L0）
4. 若存在有效 album_key 且本次为「专辑封面」（默认网易/QQ 专辑图、目录 cover.jpg）：
   - 将同 album_key、且非 track 覆盖意图的其他 Song 的 `cover_path` 指到同一文件（本轮可先做「仅当前 song + 同目录侧车」；批量同 key 传播可 P1）
5. L1：各可写版本目录写/复用 `cover.jpg`（按目录去重）
6. L2：支持的格式内嵌

### 3.6 读取规则

- `GET /api/songs/{id}/cover`：优先 `Song.cover_path`（应为 by-hash 或仍有效的本地文件）；否则 materialize 进 by-hash 再返回
- 列表/播放器：**有 song id 即可请求封面**；404 再占位。不再用 `cover_path` 字符串真值卡死请求
- 展示路径 **只读 L0**，禁止 file-first 覆盖已刮削/已 lock 的 DB 字段

### 3.7 侧车与 L0 的关系

- 目录 `cover.jpg` 仍保留：给外部播放器/整理（L1）
- L0 by-hash 解决应用展示与刮削主数据，**不要求**删光侧车
- 多源多目录下侧车可有多份；L0 仍一份

---

## 4. 文本元数据与歌词

| 字段 | L0 | 写穿 |
|------|----|------|
| title/artist/album/year/genre | Song 列 | L2 按能力；L1 无对应文件 |
| 歌词正文 | `Song.lrc_path` 指向侧车或未来 `data/lyrics/{id}.lrc` | 每版本 `.lrc` + 可选内嵌 |
| 歌词 provenance | 已有 lyrics_* 列 | 不写文件 |

本轮歌词 **不强制** 迁到 `data/lyrics/`（P2）；但 apply/clear 的「unsupported ≠ failed」与元信息对齐。

空歌词不覆盖；清空必须独立确认——保持既有边界。

---

## 5. 格式能力矩阵

| 后缀 | 文本标签 | 内嵌封面 | 内嵌歌词 | apply 内嵌结果 |
|------|----------|----------|----------|----------------|
| `.mp3` | ✅ | ✅ | ✅ | written / failed |
| `.flac` | ✅ | ✅ | ✅ | written / failed |
| `.m4a` `.mp4` `.aac` | ✅ | ✅ | ✅ | written / failed |
| `.ogg` `.opus` | 尽力 | ❌ 本轮 | 尽力 | 有写入则 written，否则 unsupported |
| `.wma` `.wav` `.ape` 等 | ❌ 或不可靠 | ❌ | ❌ | **unsupported**（侧车成功仍算版本 ok 维度上的 sidecar-written） |
| WebDAV only | — | — | — | **skipped** |

实现要点：

- 新增 `tag_write_capability(path|suffix) -> {text, cover, lyrics}`
- `write_audio_tags` 对明确 unsupported 可返回标记或由调用方先查 capability
- `apply_metadata_to_song_files`：
  - 侧车成功 + 内嵌 unsupported → 版本 `status=written` 或 `status=partial_sidecar`，**计入 written 或单独 unsupported 计数，不进 failed**
  - 内嵌返回 `{}` 且格式 unsupported → 不 raise
  - 仅当侧车失败或支持格式的内嵌异常 → `failed`

返回结构扩展（兼容旧字段）：

```json
{
  "ok": true,
  "partial": false,
  "written": 1,
  "failed": 0,
  "skipped": 1,
  "unsupported": 1,
  "versions": [
    {
      "song_file_id": 1,
      "format": "wma",
      "status": "unsupported",
      "reason": "格式不支持内嵌标签",
      "sidecar": {"cover": "written"},
      "tags": {}
    }
  ],
  "cover_path": "/.../data/covers/by-hash/....jpg",
  "cover_paths": ["...侧车..."]
}
```

前端文案：

- `元信息已保存；MP3 已写标签；WMA 仅侧车（格式不支持内嵌）`
- 不再把 unsupported 说成「失败」

---

## 6. 读路径统一（P1 为主，P0 做最低必要）

### 展示 / API（唯一）

只读 Song L0 字段 + by-hash 封面。

### 入库 / 扫描补空

仅当 L0 字段为空且未 `meta_locked`：

```text
内嵌 → 侧车 → 路径启发式 →（可选）网络
```

补上后，封面应 **materialize 到 by-hash** 并写回 `Song.cover_path`。

### 禁止

- 已刮削 / locked 歌曲被扫描用弱文件标签盖回
- 三套文档优先级继续漂移：AGENTS / resolve_song_meta / reorganize 最终都改成与本文一致

P0 只改：apply 成功语义、L0 封面落盘、convert 回填、前端闸门。  
P1 再系统性改 `resolve_song_meta` 与扫描覆盖策略。

---

## 7. 转码与多版本

### convert → MP3

转码是 L0 → 新文件的写穿：

1. 生成 MP3（可用现有 ffmpeg 元数据）
2. 回填 `SongFile.cover_path` / `lrc_path`（侧车若存在或从 L0 复制）
3. 尽量用 L0 封面 embed（已有则保持）
4. UI 不依赖「源是不是 WMA」

WMA 不是无损，不走自动转码；「不支持标签的有损也转一份可内嵌 MP3」若需要，单开产品开关，不与无损转码混谈。

### 多版本同 Song

- 文本与封面展示共享 L0
- 写穿能写则写，不能写标 unsupported
- 不存在「主版本没内嵌成功就不显示封面」

---

## 8. 分阶段落地

### P0（本轮，rc6）— 消假失败 / 稳封面

| # | 项 | 主要文件 |
|---|----|----------|
| 1 | 能力矩阵 + apply：unsupported ≠ failed；侧车成功可保留 | `media_meta_service.py`, `song_metadata_apply_service.py` |
| 2 | 封面 L0：`store_cover_bytes` → by-hash；apply/scrape 先写 L0 再写穿 | `media_meta_service.py`, `song_metadata_apply_service.py`, `library_extra.py` apply, `scrape/job.py` |
| 3 | `GET /cover` 与 materialize 优先稳定 L0 路径 | `media_meta_service.py`, `library_extra.py` |
| 4 | convert 回填 MP3 的 cover/lrc SongFile 字段；有 L0 封面则侧车复制 | `convert_service.py` |
| 5 | 前端：播放器/列表封面请求不因空 `cover_path` 直接放弃（apply 成功后必有 path；列表仍可用 cover_path 优化，但 player 在 scrape 后应刷新；SongTable 可保留 v-if 若 API 保证有 cover 即有 path） | `player.js`, 文案 `PlayerPanel.vue` |
| 6 | 单测更新 + CHANGELOG + 版本 rc6 | `tests/`, `CHANGELOG.md`, 三处 version |

### P1

- 展示路径禁用 file-first 覆盖；扫描只补空 + 尊重 lock
- 同 album_key 批量共享 cover_path
- 文档三处优先级对齐
- API 暴露 `has_cover` / scrape 状态（可选）

### P2

- 历史 cover_path 迁移脚本 → by-hash
- 歌词 L0 文件化 `data/lyrics/{id}.lrc`
- 能力矩阵返回给工作台 UI
- 真正需要时再引入 Album 表

### 明确不做

- 封面/长歌词默认 BLOB 进 SQLite
- SongFile 上挂 title/artist
- 把 WebDAV 当可写标签目标
- 用 artist-album 字符串当封面文件名主键
- 本轮为省重复先上 Album 表

---

## 9. 关键代码锚点（改造前）

| 区域 | 路径 |
|------|------|
| Song / SongFile | `app/models.py` |
| 写标签 / 封面缓存 | `app/services/media_meta_service.py` |
| 多版本 apply | `app/services/song_metadata_apply_service.py` |
| 刮削采用 API | `app/routers/library_extra.py` `apply_scrape_candidate` |
| 批量刮削 | `app/services/scrape/job.py` |
| 转码 | `app/services/convert_service.py` |
| 布局侧车 | `app/services/library_layout.py` |
| 前端封面闸门 | `web/src/stores/player.js`, `SongTable.vue` |
| 测试 | `tests/test_multi_version_metadata.py` |

### 已知反模式（P0 必须消掉）

```python
# song_metadata_apply_service.py
if not tags:
    raise RuntimeError("音频标签写入未生效")
```

WMA 等会稳定踩中。应改为 capability 判断。

---

## 10. 验收标准（P0）

1. 仅有 WMA 本地版本的歌曲：刮削采用封面 + 文本 → **L0 成功**，`Song.cover_path` 指向 by-hash 文件，`/cover` 200，列表/播放器能显示封面；版本结果为 unsupported 或 sidecar-written，**整体 ok=true**（无 L1 失败时）。
2. WMA + MP3 双版本：MP3 written，WMA unsupported；文案区分失败与不支持；封面仍显示。
3. 同目录多版本：侧车 cover.jpg 仍按目录去重写一次。
4. 转码出的 MP3：`SongFile.cover_path`/`lrc_path` 在有 L0 资源时被回填。
5. 现有多版本/封面单测通过；新增 unsupported 与 by-hash 用例。
6. 版本号三处一致为 `0.15.0-rc6`，CHANGELOG 有条目。

---

## 11. 与歌词拆分文档的关系

- `docs/lyrics-metadata-separation-handoff.md` 界定刮削 vs 歌词功能边界，仍然有效。
- 本文不重新合并两类事务；仅统一 **写穿成功语义** 与 **封面 L0 资产**。
- 刮削仍 `write_lyrics=False`；歌词 apply 对齐 unsupported 语义即可。

---

*设计依据：多格式写穿失败、封面聚合不稳、Album 表成本、内容寻址去重等讨论。实施时若与代码冲突，以「L0 成功 / 文件降级 / by-hash 封面」三原则裁决。*
