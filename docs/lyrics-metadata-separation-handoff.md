# 歌词与元信息拆分改造：完整实施与交接手册

> 用途：将本文完整提供给任意后续 Agent，即可从当前工作区状态继续实施，不需要重新梳理需求。
>
> 当前代码版本标记：`0.13.0`（歌词与元信息拆分功能已完成实现，等待最终验收结果记录）。
>
> 文档状态：实施完成，验收进行中。

## 1. 最终目标

将当前混合的“歌曲信息刮削 + 歌词获取”重构为两个边界清晰、配置独立、交互完整的功能：

1. **刮削信息**：标题、艺术家、专辑、年份、风格、封面。
2. **获取歌词**：同步歌词、纯文本歌词、纯音乐标记。
3. **刮削源**与**歌词源**分别配置、测试、排序和启停。
4. 新增歌词源 **LRCLIB**，严格遵循其 User-Agent、节流与 429 `Retry-After` 要求。
5. 单曲与批量操作都必须锁定歌曲 ID，后台切歌不得写错歌曲或覆盖当前播放器 UI。
6. 空歌词默认不得覆盖已有歌词；只有用户明确执行“清空歌词”时才允许删除。

## 2. 产品与交互原则

### 2.1 功能边界

- “刮削信息”不得隐式请求、比较、写入或删除歌词。
- “获取歌词”不得修改标题、艺术家、专辑、年份、风格和封面。
- 可后续提供“一键完善”，但只能作为顺序编排：先完成信息刮削，再进入歌词流程；两者事务与失败状态独立。

### 2.2 单曲歌词流程

播放器顶部应有两个并列且语义明确的按钮：

- 魔法棒：`刮削信息`
- 文档/歌词图标：`获取歌词`

点击“获取歌词”后采用三段式工作台：

1. **查询条件区**
   - 展示目标歌曲、艺术家、专辑、时长。
   - 显示签名完整度。
   - 支持自动选择歌词源或指定歌词源。
   - 支持修改关键词并重新检索。
   - 缺少专辑或时长时明确提示 LRCLIB 将使用宽松搜索。
2. **候选区**
   - 展示匹配分、来源、标题、艺术家、专辑、时长差、歌词类型。
   - 标签：同步歌词、纯文本、纯音乐、版本风险。
   - 点击候选后加载详情，不直接写入。
   - 来源失败不关闭弹窗，允许换源或重试。
3. **预览与应用区**
   - 完整预览候选歌词。
   - 应同时提供当前歌词与候选歌词切换或双栏比较；移动端改为上下切换。
   - 已有歌词时突出覆盖风险，并显示当前来源/类型/获取时间。
   - 选项：仅保存 `.lrc`；同时写入音频内嵌歌词。
   - 空候选默认禁用保存按钮；清空歌词必须单独入口和二次确认。

### 2.3 状态文案

必须使用具体阶段，避免笼统“加载中”：

- 正在精确匹配
- 精确匹配未命中，正在宽松搜索
- 正在检索指定歌词源
- 正在加载歌词详情
- 触发来源限流，等待 N 秒
- 正在写入歌词侧车
- 正在写入音频标签

### 2.4 UI 设计要求

- 桌面歌词弹窗建议宽度 1080–1180px，候选区与预览区约 55:45。
- 候选选中态应有明显但不刺眼的主色背景和左侧强调线。
- 匹配分采用视觉等级：90+ 绿色、70–89 蓝色、低于 70 橙色；版本冲突红色警告。
- 歌词预览使用等宽时间戳或保持原文本格式，行高不少于 1.7。
- 移动端改为单列：查询条件 → 候选 → 预览 → 固定底部操作栏。
- 重要操作按钮不得依赖悬浮才能理解；图标必须有 tooltip 与 aria-label。
- 限流、空结果、来源故障、无本地文件等均需独立空状态，不允许只弹 toast 后留下空白页面。

## 3. 歌词源能力矩阵

- **LRCLIB**
  - 支持：同步歌词、纯文本、纯音乐。
  - 精确接口：`GET /api/get`，要求标题、艺术家、专辑、时长。
  - 搜索接口：`GET /api/search`。
  - 详情接口：`GET /api/get/{id}`。
  - 不实现发布接口。
- **网易云音乐**
  - 搜索歌曲与获取歌词为两个接口。
  - 流程：搜索候选 → 使用歌曲 ID 获取歌词。
- **咪咕音乐**
  - 搜索歌曲与获取歌词为两个接口。
  - 流程：搜索候选 → 使用版权 ID 获取歌词。
- **QQ 音乐**
  - 当前不进入歌词源列表；底层下载流程可能携带歌词，但暂无稳定独立歌词 Provider。
- **iTunes / Deezer / MusicBrainz / AcoustID**
  - 仅作为元信息能力，不进入歌词源列表。

## 4. LRCLIB 强制实现要求

1. 由后端请求，浏览器不得直接请求 LRCLIB。
2. Header 必须包含可识别客户端，例如：
   `Sonpick/<当前版本> (https://github.com/liuyuanjun/sonpick)`。
3. 同一实例 LRCLIB 请求必须串行。
4. 相邻请求间隔 200–500ms，建议默认 300ms。
5. 收到 429 时读取并遵循 `Retry-After`。
6. 设置最大等待上限，避免请求线程无限阻塞；超限后返回结构化限流错误。
7. 批量任务不得并发调用 LRCLIB。
8. 按 URL/参数短期缓存，并对相同进行中的请求做去重。
9. 精确 `/api/get` 只有签名完整时调用；404 自动降级 `/api/search`。
10. LRCLIB 时长匹配以 ±2 秒为高可信，但搜索结果仍需本地评分和版本词判断。

## 5. 后端目标架构

### 5.1 配置层

- `AppSettings.scrape_sources_json`：仅元信息源。
- `AppSettings.lyrics_sources_json`：仅歌词源。
- 歌词源配置字段：
  - `id`
  - `name`
  - `enabled`
  - `auto_enabled`
  - `priority`
  - `timeout`
  - `capabilities`
  - `description`

升级兼容：若 `lyrics_sources_json` 为空，LRCLIB 默认启用；网易云和咪咕沿用旧刮削源启用状态作为一次性默认值，但保存后完全独立。

### 5.2 Provider 层

统一协议：

- `search(query, limit) -> list[LyricsCandidate]`
- `get(source_id) -> LyricsCandidate | None`

统一候选字段：

- `source`
- `source_id`
- `track_name`
- `artist_name`
- `album_name`
- `duration`
- `synced_lyrics`
- `plain_lyrics`
- `instrumental`
- `score`
- `match_detail`
- `diagnostic`

### 5.3 歌词服务层

职责：

- 根据配置实例化 Provider。
- 构建歌曲查询签名。
- 聚合并排序候选。
- 获取候选详情。
- 选择同步歌词优先、纯文本次之。
- 写入同名 `.lrc`。
- 更新 `SongFile.lrc_path` 与 `Song.lrc_path`。
- 可选写入音频标签。
- 保存来源元数据。
- 禁止默认空值覆盖。

### 5.4 歌词来源持久化

当前草案已在 `Song` 增加：

- `lyrics_provider`
- `lyrics_source_id`
- `lyrics_type`
- `lyrics_score`
- `lyrics_fetched_at`
- `lyrics_instrumental`

最终需确认是否足够。若需要保存历史与多个版本，建议改为独立 `SongLyrics` 表；本轮最低可接受是上述当前来源字段。

### 5.5 API 目标

单曲：

- `POST /api/songs/{song_id}/lyrics/candidates`
- `POST /api/songs/{song_id}/lyrics/candidate-details`
- `POST /api/songs/{song_id}/lyrics/apply`
- 建议补充：`DELETE /api/songs/{song_id}/lyrics`，仅用于明确清空并要求确认参数。

设置：

- `GET /api/settings` 返回 `scrape_sources` 与 `lyrics_sources`。
- `PUT /api/settings` 分别保存。
- `POST /api/settings/lyrics-sources/{source_id}/test`。

批量：

- `POST /api/songs/lyrics`，参数应支持：
  - `song_ids`
  - `source_id`
  - `only_missing=true`
  - `overwrite=false`
  - `write_file_tags=true`
  - `async_mode=true`

### 5.6 任务与日志

- 新任务类型：`lyrics`，不得继续复用 `scrape`。
- 统计：总数、已处理、命中、写入、纯音乐、跳过已有、未命中、限流等待、失败。
- 任务严格顺序执行外部歌词请求。
- 操作日志 action 使用 `lyrics`。
- 日志只记录来源、类型、路径和结果，不记录完整歌词。

## 6. 前端目标架构

### 6.1 设置页

桌面导航与移动端标签均拆为：

- 系统设置
- 刮削源
- 歌词源

歌词源表格/卡片展示：

- 名称与能力
- 启用
- 自动参与
- 优先级
- 超时
- 状态/测试
- 来源说明

LRCLIB 卡片必须显示：无需 API Key、公共服务、串行节流、优先同步歌词。

### 6.2 播放器

- 将所有“刮削”用户文案改为“刮削信息”。
- 增加“获取歌词”入口和完整工作台。
- 两个流程各自维护 target song 快照和 ID。
- 切歌后结果仍写原歌曲，但只有原歌曲仍为当前歌曲时才刷新 UI。

### 6.3 曲库与播放器列表

- 批量“刮削本页”改名“刮削信息”。
- 增加“获取歌词”批量入口。
- 操作前弹窗选择：仅补缺失 / 覆盖已有、歌词源、是否写入内嵌标签。
- 任务创建后进入任务中心，不在页面阻塞轮询。

### 6.4 任务中心

- `scrape` 显示“刮削信息”。
- `lyrics` 显示“获取歌词”。
- 单独展示歌词任务统计和限流等待状态。

## 7. 当前已完成的代码改造

以下内容已写入当前工作区，但还没有完整验收：

- 新增 `app/services/lyrics_source_registry.py`。
- 新增 `app/services/lyrics_provider.py`。
- 新增 `app/services/lrclib_provider.py`。
- 新增 `app/services/domestic_lyrics_provider.py`。
- 新增 `app/services/lyrics_search_service.py`。
- `AppSettings` 增加 `lyrics_sources_json` 草案。
- `Song` 增加歌词来源字段草案。
- SQLite `_ensure_columns` 与 Song 重建迁移已加入对应字段草案。
- 设置 schema、响应与保存逻辑已加入 `lyrics_sources`。
- 新增歌词源测试接口草案。
- 新增单曲歌词候选、详情、应用 API 草案。
- 播放器已增加独立“获取歌词”按钮与三段式弹窗草案。
- 元信息字段确认已移除歌词项。
- 设置页已增加“歌词源”导航、桌面表格、移动端卡片和测试函数草案。
- 前端 API 已增加歌词搜索、详情和应用方法。

## 8. 当前明确未完成/需修复事项

### P0：必须先处理

1. 当前改造没有完成 Python 语法验证；最后一次验证被 Goal 模式主机守卫阻止。
2. 前端没有构建，当前环境此前缺少 pnpm/yarn/npm。
3. `SettingsView.vue`、`PlayerPanel.vue` 是连续增量编辑，需要完整模板和脚本结构检查，防止标签插入位置或未定义符号问题。
4. LRCLIB 详情逻辑存在问题：搜索结果已包含歌词时不应强制再次 `/api/get/{id}`；应优先复用候选或缓存。
5. LRCLIB 精确接口 404 降级行为需测试；当前 `_request()` 返回 `None`，逻辑基本存在但未验收。
6. 国内 Provider 的 `get()` 返回候选时标题等为空，当前 fallback 合并需验证。
7. 元信息路由仍需全文搜索，确保不存在歌词字段、歌词侧车和歌词标签残留写入。
8. 版本已统一升级为 `0.13.0`；最终发布仍以完整测试、构建和视觉验收结果为准。
9. 当前 CHANGELOG 仍描述 rc3 的早期混合刮削字段功能，需要改写成最终拆分设计。
10. 未实现批量歌词任务、曲库/播放器列表入口、任务中心展示。

### P1：功能完整性

1. 增加明确清空歌词 API 与二次确认 UI。
2. 增加当前歌词/候选歌词比较，而非仅单面预览。
3. 保存后返回完整 `SongOut` 或歌词来源信息，便于 UI 即时更新。
4. 新增批量歌词任务，并严格串行。
5. 完成 429 结构化状态向前端透传，而非普通字符串。
6. 增加请求进行中去重；当前只有结果缓存。
7. Provider 测试不应依赖固定英文歌曲长期存在，建议按来源设计轻量健康检查或允许测试关键词。
8. 记录歌词来源后，标签弹窗或歌词面板应显示来源与获取时间。
9. 纯音乐候选的播放器体验需定义：显示“纯音乐”而不是“暂无歌词”。

### P2：体验和质量

1. 候选匹配分颜色等级与版本风险标签。
2. 当前/候选双栏比较及移动端切换。
3. 弹窗底部操作栏在移动端固定。
4. 键盘可访问性、焦点回收和 aria 标签检查。
5. 来源失败、限流、空结果使用页面内状态卡，而不只 toast。
6. 可选“一键完善”编排入口。

## 9. 推荐实施顺序

### 阶段 A：收口当前草案

1. 运行 Python `py_compile`。
2. 检查 Vue 模板闭合、导入和未定义变量。
3. 清理元信息路由中的所有歌词残留。
4. 为歌词服务补齐错误类型：未命中、限流、超时、无本地文件、空歌词。
5. 验证数据库迁移可在旧数据库与新数据库运行。

### 阶段 B：单曲完整闭环

1. 完善 LRCLIB 与国内 Provider。
2. 完善三段式弹窗和当前歌词比较。
3. 完善应用、清空、纯音乐、来源展示。
4. 验证切歌竞态。
5. 增加后端与前端单曲测试。

### 阶段 C：批量与任务中心

1. 新增 `lyrics` 任务和 worker 分支。
2. 新增批量 API。
3. 修改 PlayerView、LibraryView、SourcesView 的批量入口与文案。
4. 修改 TaskCenter 类型、标题、统计和状态。
5. 验证 LRCLIB 严格串行和限流等待。

### 阶段 D：视觉与发布验收

1. 启动前后端。
2. 桌面与移动端截图检查。
3. 修复布局、空状态、滚动和固定操作栏。
4. 执行完整后端测试与前端构建。
5. 升级版本、更新文档和 Changelog。

## 10. 测试清单

### 后端

- 歌词源配置默认值和保存后独立性。
- 旧设置迁移网易云/咪咕状态，LRCLIB 默认启用。
- LRCLIB User-Agent、参数编码、精确查询、404 降级。
- 429 `Retry-After`、串行间隔、缓存、熔断。
- 标题/艺术家/专辑/时长评分和版本词惩罚。
- 同步歌词优先，纯文本回退，纯音乐处理。
- 空歌词默认拒绝覆盖。
- `.lrc`、SongFile、Song、内嵌标签一致性。
- 元信息应用不改变歌词。
- 歌词应用不改变元信息。
- 切歌后锁定原 song_id。
- 批量 only_missing、overwrite 和限流统计。

### 前端

- 设置页三导航桌面/移动端。
- 歌词源保存、测试、禁用联动。
- 单曲歌词入口与目标歌曲锁定。
- 缺少签名提示。
- 自动/指定源切换。
- 候选选择、详情、预览、覆盖确认。
- 空候选不能保存。
- 来源故障/限流后可换源重试。
- 切歌后不覆盖新歌曲 UI。
- 移动端单列布局和固定操作栏。
- 批量任务创建和任务中心状态。

## 11. 验收标准

> 实施记录（0.13.0）：`git diff --check`、Python 语法编译与前端生产构建已通过；歌词 Provider/LRCLIB 专项 5 项 `unittest` 已通过。仓库原有播放选择测试因当前本机 Python 环境缺少运行依赖 `mutagen` 未能导入，未出现测试断言失败；桌面与移动端截图视觉验收仍建议在部署环境补跑。


- 元信息与歌词在前端入口、设置、API、Provider、任务类型、日志上完全独立。
- LRCLIB 符合文档中的 User-Agent、串行、间隔和 429 要求。
- 用户可以预览并确认歌词，不会被空数据误覆盖。
- 单曲和批量均不存在切歌/并发写错歌曲问题。
- 数据库迁移兼容既有数据。
- Python 测试、前端构建、`git diff --check` 全部通过。
- 桌面与移动端完成视觉验收，无溢出、遮挡、空白状态或不可达操作。
- 版本号、`X-App-Version`、README、AGENTS、CHANGELOG、产品说明一致。

## 12. 接手时建议执行的首批命令

```bash
python3 -m py_compile app/models.py app/database.py app/schemas.py app/routers/settings.py app/routers/library_extra.py app/services/lyrics_source_registry.py app/services/lyrics_provider.py app/services/lrclib_provider.py app/services/domestic_lyrics_provider.py app/services/lyrics_search_service.py

git diff --check
git status --short
```

随后检查：

```bash
grep -R "lyrics" -n app/routers/library_extra.py web/src/components/player/PlayerPanel.vue web/src/views/SettingsView.vue
```

若 Node 包管理器可用：

```bash
cd web && pnpm build
```

## 13. 工作区注意事项

- 当前存在未跟踪 `.claude/`，不是本任务创建，不要擅自提交或删除。
- 当前所有相关文件均处于未提交状态，后续编辑必须基于现有 diff，不要重置工作区。
- 之前子 Agent 尝试因 Provider HTTP 403 失败，没有产生任何代码或有效报告。
