# AGENTS.md — 拾音 Sonpick

面向后续 AI Agent / 协作者的项目操作手册。改代码前先读本文件与 `CHANGELOG.md`。

---

## 0. 规范

- 事实与逻辑才是第一重要，对不符合事实逻辑的用户需求要反驳，要提问，要纠正，绝对禁止迎合用户需求。
- 我提出的要求可能是错的或者是外行的或者是不完整的，如果我的要求不是最佳实践，你应该及时提醒和询问，而不是迎合我的想法去修改。要避免产品设计走偏。
- 如果我的指令不完整、不明确、不合理、与实际情况不一致，请随时告诉我询问我，而不是自己猜测或盲目执行。
- 所有的改动都要先评估架构是否合理，是否有更优的方案，不用局限于只实现当前，发现了就直接提出建议或询问用户是否需要重构。早改比留历史包袱好。
- 整体结构很重要！永远要有整体考虑，要避免为实现单一局部目的破坏整体，如无法避免要向用户提出警告。
- 当需要外部信息时，比如三方文档、数据源、API 文档等，如果使用你的内置工具查询不到，先询问我查找粘贴给你，而不是直接猜测编造。
- 要适当注意性能问题，尽量避免循环高频查询、一次载入大量数据、重复计算等。对于复杂的计算或数据处理，建议分批处理或使用缓存。
- 要时刻注意整体架构，功能尽量模块化，考虑全面，封装完善，可复用，可扩展，减少耦合，尽量避免多次实现相同功能，比如本项目的多个下载源，多个刮削源这种情况，要模块化可插拔，避免耦合度高。功能设计要模块化，一次实现多处调用，尽可能避免重复实现。
- 工作过程中如果发现bug、脏代码或者可优化的地方要及时提醒我并询问我是否需要修改。
- 当代码进行了更新后，要及时更新 `AGENTS.md`、`README.md`、`CHANGELOG.md` 及相关文档。保持文档与代码的一致性。产品边界与交互约定写在本文件 §1.1 与 `README.md`，勿再维护独立的 `product-overview.md`。

---

## 1. 项目定位

可部署在 NAS 上的**个人音乐下载与管理** Web 应用。

- 搜索/批量下载音乐（基于 `musicdl`，当前主要 QQ 音乐源）
- 曲库：播放、转码 MP3、删除
- WebDAV：连接配置、目录浏览、代理播放、套件上传（音频+封面+歌词）
- 操作日志：下载 / 上传 / 删除 / 转码可查询
- 单用户密码登录（JWT）+ 白天/黑夜主题 + 底部全局播放器

**非目标**：多用户、公网商用、版权绕过。仅供个人学习与备份。

当前版本（以代码为准）：`0.15.1-rc7`（`setup_app.py` / `web/package.json` / `app/main.py` 的 `APP_VERSION` 必须一致）。

### 1.1 歌词与元信息边界

- **刮削信息**：标题、艺术家、专辑、年份、风格和封面。
- **获取歌词**：同步歌词、纯文本歌词和纯音乐标记。
- 两类功能分别配置来源、测试、排序、启停，并使用独立 API、任务类型和操作日志。
- 空歌词不会覆盖已有内容；清空歌词必须通过独立确认操作。
- 单曲和批量任务均锁定歌曲 ID；播放器只在目标歌曲仍为当前歌曲时刷新界面。

**歌词来源**

- LRCLIB：无需 API Key，公共服务，后端串行节流，优先同步歌词，支持纯文本和纯音乐。
- 网易云音乐：搜索候选后按歌曲 ID 获取歌词。
- 咪咕音乐：搜索候选后按版权 ID 获取歌词。

**主要交互**

- 播放器顶部提供「刮削信息」和「获取歌词」两个独立入口。
- 播放器：随机播放全部先获取当前筛选范围的轻量可播放歌曲池，在前端洗牌后按随机队列播放；当前随机轮次不重复，上一曲通过播放历史回退，文件版本仍由播放接口按需经 `SongFileResolver` 解析。
- 歌词工作台支持查询条件、候选、当前/候选比较、保存和明确清空。
- 元信息候选采用前会逐项比较；封面显示新旧图片、图片尺寸和旧文件大小；旧封面缺失时默认选择候选封面，已有旧封面时默认保留。
- 刮削信息与歌词保存/清空会写入同一逻辑歌曲的全部可用本地 `SongFile` 版本及各自侧车；WebDAV 版本只展示并明确标记为远端只读。
- 刮削与歌词工作台的「歌曲文件」区域必须列出全部本地/WebDAV 版本，不使用表单输入框展示文件位置。弹窗打开时应通过 `GET /api/songs/{song_id}/files`（复用 `SongFileResolver.describe_files`，与播放同源）拉取权威文件列表，而不是依赖内存里的 `player.current.versions`——后者仅部分列表接口（曲库 `list_songs`、重检 `recheck_song`）会填充，来自歌单/历史/搜索等上下文时会缺失，导致「暂无歌曲文件记录」。
- 曲库、播放器列表与来源页可创建批量歌词任务。
- 任务中心展示匹配、写入、纯音乐、跳过已有、未命中、限流等待和失败统计。

---

## 2. 技术栈

| 层 | 技术 |
|----|------|
| 后端 | FastAPI + SQLAlchemy 2.0 + SQLite |
| 前端 | Vue 3 + Vite + Naive UI + Pinia + Axios |
| 下载 | `musicdl`（PyPI 精确钉版，Dependabot 周检跟踪上游并自动开 PR） |
| 转码 | 系统 `ffmpeg` |
| 部署 | Docker / docker-compose；多阶段 Dockerfile 镜像内构建前端；GHCR / Docker Hub / 阿里云 ACR 三发 |

包管理：本项目前端 **优先 pnpm**（`packageManager` 字段）；无 pnpm 时再 yarn/npm。发布脚本默认 pnpm。

---

## 3. 目录结构（关键）

```text
music/
├── app/                      # FastAPI 后端
│   ├── main.py               # 入口、路由挂载、静态资源、/health、X-App-Version
│   ├── config.py             # 环境变量 Settings
│   ├── database.py           # SQLite 引擎（惰性初始化）+ 轻量迁移
│   ├── models.py             # User / AppSettings / MediaSource / Task / Song / SongFile / OperationLog
│   ├── schemas.py            # Pydantic 模型（含 TaskOut、SongOut、Settings*、OperationLogOut）
│   ├── security.py           # 密码哈希 + JWT
│   ├── routers/              # API 路由
│   └── services/             # 业务：musicdl / webdav / convert / task_worker / operation_log
├── web/                      # 前端源码
│   ├── src/views/            # 页面
│   ├── src/stores/           # Pinia
│   ├── src/api/client.js     # Axios 封装
│   └── dist/                 # 构建产物（Docker 默认 COPY 这里）
├── .github/workflows/release.yml # tag 触发：版本校验 + 多架构镜像构建 + 三仓库推送
├── scripts/deploy-nas.sh     # NAS 一键部署（远端 pull 镜像 → up -d → 健康检查）
├── Dockerfile                # 多阶段：Node 构建前端 → Python 运行时
├── docker-compose.yml        # 基于预构建镜像的通用示例（SONPICK_IMAGE 可覆盖）
├── CHANGELOG.md
├── README.md
└── AGENTS.md                 # 本文件
```

运行时数据（勿提交密钥/大文件逻辑依赖）：

- `data/`：SQLite（默认 `data/music.db`）
- `downloads/`：本地音乐
- `logs/`：compose 挂载点（应用主日志仍多在容器 stdout）

---

## 4. 后端约定

### 4.1 入口与可观测性

- 应用：`app.main:app`
- 健康检查：`GET /health` → `{"status":"ok","version":"..."}`
- 全站响应头：`X-App-Version` = `APP_VERSION`
- 静态前端：挂载 `web/dist`（生产）；开发可前后端分离
- WebSocket：`/ws/progress`（任务进度）
- uvicorn 生产参数建议：`--proxy-headers --forwarded-allow-ips '*'`（compose 已用）

### 4.2 路由前缀

| 前缀 | 文件 | 说明 |
|------|------|------|
| `/api/auth` | `auth.py` | 登录、JWT |
| `/api/settings` | `settings.py` | 系统/WebDAV 相关设置 |
| `/api/search` | `search.py` | 搜索；`/search/stream` 为 SSE 流式搜索（progress/heartbeat/result 事件） |
| `/api/download` | `download.py` | 创建下载任务 |
| `/api/songs` | `library.py` | 曲库、播放、转码、上传、删除 |
| `/api/webdav` | `webdav.py` | 列表、流式播放 |
| `/api/tasks` | `tasks.py` | 任务查询 |
| `/api/sources` | `sources.py` | 多媒体源 CRUD / 测试 / 默认上传 / 扫描 |
| `/api/logs` | `logs.py` | 操作日志列表/清空 |

改路由时：同步前端 `web/src/api` 调用与 `router.js` 页面；`schemas.py` 的 response model **必须存在**（曾因缺 `TaskOut` 导致容器 Restarting + 502）。

### 4.3 数据模型要点

- `AppSettings`：单行（`id=1`）。WebDAV 连接与上传策略字段：
  - `auto_upload_webdav`
  - `webdav_upload_sidecar`（封面/歌词）
  - `webdav_conflict_policy`：`rename` \| `overwrite` \| `skip`（默认 `rename`）
  - `webdav_delete_local_after_upload`（仅音频真正上传/覆盖/重命名成功后删本地；`skip` 不删）
  - `webdav_remote_dir`
- `Song.status`：`local` / `uploaded` / `both` / `remote`（历史值需兼容）
- `OperationLog.action`：`download` / `upload` / `delete` / `convert`
- SQLite 迁移顺序：`init_db()` 依次执行建表、`_ensure_columns`、默认媒体源、SongFile 索引以及路径责任迁移；迁移会将历史 Song 路径/侧车回填到 SongFile 后重建 `songs` 表删除旧路径列。
- SQLite 单写者纪律：`database.py` 在数据访问层（engine 事件）用进程内 `RLock` 串行化写事务——执行写语句（INSERT/UPDATE/DELETE/REPLACE/CREATE/ALTER/DROP）前取锁，提交/回滚时释放；纯读事务不阻塞。业务代码无需感知此锁，也不要自建写锁绕过它。
- **SongFile 是物理文件唯一真相源**：所有播放、上传、转码、删除、整理、刮削和标签写入必须通过 `SongFileResolver` 或明确 SongFile 查询选择版本；禁止重新引入 `Song.local_path` / `Song.webdav_path`。
- **Song 不记录来源**：歌曲与来源的归属只由 `SongFile.library_source_id` 承载。可见性过滤（喜欢/艺术家/专辑/历史/歌单/统计）、批量任务按来源选歌、来源歌曲数统计，统一使用 `app/services/library_visibility.py`（`active_song_query` / `active_song_filter` / `has_version_in_source` / `count_songs_in_source`）；禁止再按 Song 判断来源或重新加回 `Song.library_source_id`。
- **元数据 L0（展示/刮削成功只认）**：`Song` 文本字段 + 封面 `data/covers/by-hash/{sha}`（`Song.cover_path` 指向它）+ 歌词指针/provenance。侧车 `cover.jpg` / `.lrc` 与内嵌标签是 L1/L2 写穿；格式不支持内嵌（如 WMA）为 `unsupported`，不算刮削失败。详见 `docs/metadata-l0-cover-refactor.md`。
- `Song.cover_path` / `Song.lrc_path` 是 L0 指针（封面应为 by-hash）；`SongFile.cover_path` / `SongFile.lrc_path` 是版本侧车资源。扫描和选中版本时可回填 L0。
- 扫描接口 `/api/library/scan` 和 `/api/sources/{source_id}/scan` 会创建 `type=scan` 的异步任务；前端经任务中心/单任务 SSE 接收终态。
- **扫描不覆盖已存在的 Song 文本元数据**：扫描仅补充缺失字段（title/artist/album 为空或仅为通用目录名时），绝不反向用文件名/目录派生值覆盖用户已刮削或手动修正的标题/艺人/专辑。封面/歌词侧车与时长/大小等物质事实可刷新，但文本归属数据以用户修正为准。回归测试要点：刮削修正后再次扫描不得回退。
- 失效记录管理：`GET /api/songs?availability=available|all|unavailable` 筛选；`POST /api/songs/{id}/recheck` 单歌重检（本地 stat + WebDAV 探测，连接失败保留原状态）；`POST /api/library/cleanup/preview` 分析 + `POST /api/library/cleanup` 创建 `type=cleanup` 异步任务（`library_cleanup_service`：文件还在→恢复 available，确认失联→仅删 DB 记录，存储不可达→跳过防误删）。
- `Task.created_at` 表示入队时间，`Task.started_at` 表示 worker 实际开始执行时间；排队等待与任务耗时必须分别使用这两个时间计算。

### 4.3.1 搜索曲库比对与下载重复决策

- `library_match_service.match_search_results(db, items)`：搜索接口对一页结果批量比对，内存索引，禁止 N+1；三级匹配（平台曲目 ID / 规范化 artist+title+album+时长容差 / artist+title 疑似），版本差异（remix/live/伴奏/重制等）只判 `possible_duplicate`。
- 搜索结果附 `library_match`：`status` / `song_id` / `versions[]`（location、format、size_bytes、replaceable）；不暴露服务器绝对路径；大小缺失时仅对命中的本地文件 stat。
- 下载接口可选字段 `duplicate_action`（`keep_both` / `replace`）、`replace_song_file_id`、`matched_song_id`；缺省保持旧行为；`replace` 缺有效目标返回 422；决策随任务 payload 传递，worker 执行前重新校验 SongFile。
- `download_duplicate_service`：`apply_keep_both` 把新版本并入同一逻辑 Song；`apply_replace` 先校验下载结果，再同目录临时文件 + `os.replace` 近似原子替换，失败不动旧文件；remote-only（WebDAV）版本不提供替换。

### 4.4 服务层

- `library_layout.py`：曲库目录/命名规范（Artist/Album/Title、cover.jpg、artist.jpg、同名 lrc）
- `resolve_song_meta`（`media_meta_service`）：内嵌→侧车→DB→可选网络
- 整理：`scripts/reorganize_library.py`（默认可独立运行，根=脚本目录；dry-run / `--apply`；可选 `--with-db`）


- `MusicDLService`：搜索/下载；`download_one` 签名以源码为准（含 `task_id/keyword/...`），`task_worker` 必须匹配
- `WebDAVService`：
  - list/stream/upload **共用** URL 根拆分逻辑，禁止再写死 `/music`
  - 上传为套件：音频 + 可选封面/歌词（同 stem）
  - 冲突策略按文件生效；写 `OperationLog`
- `ConvertService(db)`：需要 Session；`convert_to_mp3(path, song_id=...)`
- `TaskWorker`：内存队列 + 4 worker 协程消费 `pending` 任务（lane 限流，见 §10.1）；进度经事件队列由 flusher 批量落库 + WS/SSE 广播
- `execution.py`：统一并发内核——共享线程池 + lane 信号量 + `run_with_hard_timeout`；**禁止**在业务代码里再自建 `ThreadPoolExecutor` / 裸 `threading.Thread`
- `host_limiter.py`：per-host 外部调用限流（并发槽 + 最小间隔 + 429 冷却）；新增外部 HTTP 调用必须挂接 `get_limiter(host)`
- `http_client.py`：统一外部 HTTP JSON 拉取（`host_from_url` / `http_json`），刮削/歌词 provider 走 urllib + per-host `HostLimiter`；新增外部 JSON 接口不要再裸 `urllib` 拼请求
- `constants.py`：媒体格式/扩展名常量的唯一权威（`LOSSLESS_FORMATS` / `AUDIO_EXTS` / `IMAGE_EXTS` / `LRC_EXTS`），禁止在业务模块重复定义
- `source_config.py`：刮削源/歌词源注册表共用的配置解析基元（`load_configs` / `dump_configs` / `select_configs`）
- `write_log(...)`：文件类操作尽量落操作日志

### 4.5 安全

- **禁止**在日志、提交、示例中输出 `SECRET_KEY`、WebDAV 密码、JWT、`.env` 明文
- WebDAV 密码：Fernet 加密存 `webdav_password_enc`；更新时**空字符串表示不修改**
- 默认 `ADMIN_PASSWORD` / `SECRET_KEY` 仅开发用；生产必须改

---

## 5. 前端约定

### 5.1 页面与职责

| 路由 | 视图 | 职责 |
|------|------|------|
| `/login` | LoginView | 登录 |
| `/` | DashboardView | 概览 |
| `/download` | DownloadView | 搜索下载 + 导入下载 |
| `/library` | LibraryView | 曲库（含 local/WebDAV 来源管理、浏览、扫描/整理/刮削） |
| `/player` | PlayerView | 播放器 |
| `/sources` | redirect → `/library` | 历史入口，统一收敛到曲库 |
| `/logs` | LogsView | 操作日志 |
| `/settings` | SettingsView | 存储路径/默认格式/自动转码/自动上传总开关 |

**配置归属**：

- WebDAV 地址/账号密码/冲突策略/侧车/删本地/远程子目录 → **只在曲库页来源管理**（移动端可用 `?manage=1` 打开底部抽屉）
- 设置页可保留「自动上传」总开关，并链接到曲库页细项，避免双源维护

### 5.2 UI / 工程

- 组件库：Naive UI；图标：`@vicons/ionicons5`
- 新 Naive 组件要在 `web/src/main.js` **import 并注册**（未全量 unplugin 自动引入时尤其注意）
- 全局播放器：Pinia `player` store；音频 URL 常带 `token` query
- 系统媒体键/线控：`web/src/composables/useMediaSession.js`（Media Session API，挂载于 `GlobalPlayer.vue`）——单击播放/暂停、双击下一曲、三击上一曲由 OS 翻译成媒体命令，网页只收 action，无法感知按键次数
- 主题：`theme` store；`App.vue` 使用 `n-config-provider` + dialog/message provider
- 前端文案：当前仓库以中文硬编码为主；**若新增 React 代码**，全局规则要求走 i18n、禁止硬编码用户可见字符串。现有 Vue 页面保持项目既有风格，不强制一次性 i18n 化

### 5.3 构建

```bash
cd web
pnpm install && pnpm build
# 无 pnpm 时先安装/启用项目声明的 pnpm 版本，不建议切换 npm/yarn。
```

产物：`web/dist/`。改前端后部署前必须重新 build（默认 Docker 不再容器内构建）。

注：本地开发仍需手动 build 才能让 `uvicorn` 直接托管前端；CI 镜像构建已在 Dockerfile 第一阶段自动完成前端 build。

---

## 6. 版本与变更纪律（必须）

语义化版本，允许预发布：`MAJOR.MINOR.PATCH` 或 `MAJOR.MINOR.PATCH-rcN`。

| 变更类型 | 版本怎么动 |
|----------|------------|
| 新功能 | 提升正式版本位（按影响选 minor/patch） |
| 仅 bugfix | **只升 rc**（如 `0.8.0-rc1` → `0.8.0-rc2`），不抬正式位 |
| 每次改代码 | 前后端版本号**必须一致** |

必须同步的位置：

1. `setup_app.py` → `version=...`
2. `web/package.json`（及 lock 中顶层 version）
3. `app/main.py` → `APP_VERSION`
4. `CHANGELOG.md` 追加条目

API 必须继续暴露 `X-App-Version`。  
用户要求 git 提交时：打 `v{版本号}` tag，并与代码一并推送（远程为 GitHub 时）。

### 6.1 版本发布辅助脚本（`scripts/version.sh`）

改版本、提交、打 tag、推送优先用脚本完成，幂等可重入，任何一步失败后**重跑同一命令即可续跑**（已完成的步骤自动跳过）：

```bash
scripts/version.sh current                 # 查看三处版本号、一致性、CHANGELOG 段落、tag/HEAD 状态
scripts/version.sh set 0.15.0-rc2          # 只改三处版本号 + 校验 CHANGELOG（缺段落自动插模板并提醒补充）
scripts/version.sh set 0.15.0-rc2 -m "fix(scan): 修复xxx"          # 改版本 + commit + 打 tag
scripts/version.sh set 0.15.0-rc2 -m "fix(scan): 修复xxx" --push   # 以上全部 + 推送分支和 tag
```

- commit 信息没带 `(版本号)` 后缀时脚本自动补上；额外要一起提交的路径用 `--include <路径>` 追加。
- `-m` 提交时脚本会 `git add -u` 一并带上**所有已跟踪文件的修改**（避免只提交版本号文件、漏掉功能代码）；未跟踪的新文件**不会**自动加入，需 `--include <路径>` 显式指定。
- tag 已存在但不指向 HEAD 时脚本只提醒不移动；确需移动先 `git tag -d v{版本号}` 再重跑。
- 推送完成后确认 release workflow 通过（`gh run list --limit 3`）再部署 NAS。

---

## 7. 本地开发

```bash
# 后端
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 前端（开发）
cd web && yarn && yarn dev
```

环境变量见 `.env`：`SECRET_KEY`、`STORAGE_PATH`、`DATABASE_PATH`、`DATA_DIR`。

升级下载引擎：改 `requirements.txt` 中 `musicdl==x.y.z` 的版本号即可（Dependabot 每周检查 PyPI 并自动开 PR）；不要重新把 musicdl 源码 vendor 进仓库。

自检：

```bash
curl -sS http://127.0.0.1:8000/health
```

---

## 8. 部署（镜像化发布 / NAS）

### 8.1 发布链路

1. 发版：打 `v{版本号}` tag 并推送 → GitHub Actions（`.github/workflows/release.yml`）校验 tag 与三处版本号一致 → 构建 linux/amd64 + linux/arm64 镜像 → 三推：
   - `ghcr.io/liuyuanjun/sonpick`
   - `<DOCKER_USERNAME>/sonpick`（Docker Hub）
   - `registry.cn-beijing.aliyuncs.com/<ALIYUN_NAMESPACE>/sonpick`
2. 所需仓库 Secrets：`DOCKER_USERNAME` / `DOCKER_PASSWORD` / `ALIYUN_USERNAME` / `ALIYUN_PASSWORD` / `ALIYUN_NAMESPACE`；GHCR 用 `GITHUB_TOKEN`，无需配置。
3. 用户部署：根 `docker-compose.yml`（默认 GHCR 镜像，`SONPICK_IMAGE` 可换源）+ `.env` → `docker compose up -d`。

### 8.2 维护者 NAS 一键部署

| 项 | 值 |
|----|-----|
| SSH | `Host qnap` → `nas.liuyuanjun.com:9022` user `admin` |
| 远端目录 | `/home/admin/Docker/sonpick` |
| 部署命令 | `./scripts/deploy-nas.sh`（默认部署 APP_VERSION；`--version` / `--latest` 可覆盖） |
| 镜像来源 | 阿里云 ACR `yuanjunl/sonpick`（`SONPICK_ACR_NAMESPACE` 或 `SONPICK_IMAGE_REPO` 可覆盖） |

脚本流程：同步根 `docker-compose.yml` → 远端 `.env` 固定 `SONPICK_IMAGE` → `docker compose pull && up -d` → 健康检查（8301）。

NAS 一次性前置：
- 私有 ACR 需 `docker login registry.cn-beijing.aliyuncs.com` 一次（或把仓库设为公开）
- 机器相关定制（如 `/vol2/@team/Music` 音乐目录挂载）放远端 `docker-compose.override.yml`，脚本不会覆盖它

```bash
./scripts/deploy-nas.sh
ssh qnap 'curl -sS http://127.0.0.1:8301/health'
```

当前项目部署于 nas.liuyuanjun.com 上，端口为 8301。服务器 ssh 端口为 9022，用户名为 admin，已配置密钥对。开发期间对安全要求不高，如需可把数据库拉取到本地分析。

### 8.3 数据与密钥

- `data/` `downloads/` `logs/` 留在 NAS；部署脚本**不覆盖/不删除** 这些目录与 `.env`（仅在缺失时创建默认 `.env`）
- 首次部署后请改 `SECRET_KEY`；管理员密码在首次访问站点时设置

### 8.4 502 / Restarting

1. `ssh qnap 'cd /home/admin/Docker/sonpick && docker compose ps && docker compose logs --tail=200'`
2. `curl http://127.0.0.1:8301/health`
3. 常见：schemas 缺模型导致 ImportError 启动失败；镜像 tag 不存在（release workflow 未完成或失败）



## 9. Agent 工作流（改代码时）

1. **先读再改**：相关 router/service/view 与 `models`/`schemas` 一起看，避免 API 签名漂移  
2. **窄改动**：复用现有 Naive UI / Pinia / 服务层模式，不引入未在 `requirements.txt` / `package.json` 声明的库  
3. **schemas 与 routers 同步**：新增 response_model 必须在 `schemas.py` 定义  
4. **服务调用对齐**：改 `MusicDLService` / `ConvertService` / `WebDAVService` 签名时，同步 `task_worker` 与 routers  
5. **WebDAV 配置单源**：细项放 WebDAV 页；设置页不恢复整套连接表单  
6. **文件操作写日志**：下载/上传/删除/转码走 `operation_log_service`  
7. **版本 + CHANGELOG** 同一次改完  
8. **部署相关**：若影响运行镜像，更新 `Dockerfile` 与 `.github/workflows/release.yml`，并确认发版 workflow 通过  
9. **验证**：
   - 后端：能 import、`/health` 有版本
   - 前端：`yarn build` 或 `vite build` 通过
   - 涉及启动路径时，优先保证 `uvicorn` 不会 ImportError
10. **回复用户用简体中文**；关键结论、版本号、风险不要含糊

### 9.1 明确不要做的事

- 不要在 bugfix 里抬正式版本号（只用 rc）
- 不要提交 `.env`、真实密码、Token
- 不要用 `cat`/`echo` 重定向批量写关键业务文件（优先编辑/补丁工具）
- 不要假设生产 SQLite 可删库重建——加列走 `_ensure_columns`
- 不要把 WebDAV 上传路径再次写死为 `/music`
- 单文件尽量 < 2000 行，超过 3000 行必须拆分

---

## 10. 已知限制与待办

**限制**

- 下载源有限；VIP/版权曲可能失败
- 部分浏览器 FLAC 播放差，可转码 MP3
- 不同 WebDAV 服务器路径/LIST 行为不一致
- remote-only（上传后删本地）曲库体验仍不完整

**待办**

- remote-only 曲库的封面/歌词远程侧车直链体验
- 更多音乐源支持
- 增量扫描策略与任务重试
- 持续补充端到端视觉回归和更多音频格式的内嵌歌词写入测试
- 可按需要增加「一键完善」编排，但仍保持元信息与歌词事务独立

---

## 10.1 架构速查（原 CLAUDE.md 合并内容）

### 后端分层

- `app/routers/`：薄路由层，约定 `except HTTPException: raise` + 兜底 `HTTPException(400, f"动作失败: {type(e).__name__}: {e}")`
- 关键服务备注：
  - `task_worker.py`：后台任务（线程池 max_workers=2，**线程不是进程**）
  - `musicdl_service.py`：搜索/下载，按格式落盘（`_format_base_dir`）
  - `library_organize_service.py`：曲库整理（preview/apply × local/webdav）
  - `library_scan_service.py` / `library_scan.py`：扫描入库；排除规则 `_is_excluded`（核心 `**/.*`/`**/.@*`/`**/@eaDir/**`/`**/#recycle/**`/`**/Thumbs.db`/`**/*.tmp`）匹配路径**任意组成部分**，支持任意深度与 `X/**` 目录树；单曲整理 `_organize_song_plan` 同样套用该排除，回收站等目录下的文件不会进入扫描/整理计划
  - `scrape/`：元数据刮削管线（MusicBrainz → 网易/QQ/咪咕）
  - `media_meta_service.py`：标签/时长/封面读取（mutagen→tinytag→ffprobe；**无比特率工具**）
  - `convert_service.py`：转码 MP3（`LOSSLESS_FORMATS` 见 `constants.py`，是全库唯一的无损判断权威，含 dsf/dff）
  - `library_layout.py`：目录规范 `Artist/Album/Title.ext`、cover.jpg、同名 lrc、`sanitize_component`

### 任务系统细节

- `Task.status`：`pending/running/completed/failed/cancelled`；类型：`scan/scrape/lyrics/convert/search_download/batch_download/cleanup`
- 执行模型：内存队列即时调度（`enqueue` 入队，任意线程可调），4 个 worker 协程按 lane 信号量限流（download=1 / convert=1 / scrape=2 含歌词 / scan=1 含 cleanup），任务体在线程池（`sonpick-task`，max_workers=4）跑同步函数，`worker_thread_id` 记录线程 ident（旧任务为 NULL）；启动恢复遗留 pending，reconcile 每 30s 兜底
- 进度管线：`emit()` 非阻塞入队，flusher 协程每 0.5s 按任务合并批量落库 + 广播；任务写终态前强制冲刷；loop 未运行时回退同步直写
- **watchdog**（60s 周期）：running 任务超 30 分钟无更新（`updated_at`）且 future 已丢失/完成（进程重启后 orphaned 同此）→ 标记 `failed`；判定只看 future，不看线程 ident
- 任务认领为原子 claim（`UPDATE ... WHERE status='pending'` 按 rowcount 判归属），多进程/多 worker 下不会重复执行
- 前端 TaskCenter 抽屉打开时 10s 兜底轮询
- 注意：**整理（reorganize）不走任务系统**，是同步 HTTP（前端 timeout 120s/600s）；扫描、下载、转码和刮削走 TaskWorker 异步任务

### 曲库整理规则（library_organize_service）

- 元数据优先级：DB（刮削结果）→ 内嵌标签 → 文件名解析；**缺专辑默认跳过**（`skip_missing_album`），失败文件进 `_failed/` 并写 `.error.txt`
- 目标 base 按文件决定（`_local_base_for_file`）：
  1. 开「按格式归档」(`relocate_format_dirs`)：按扩展名分流到无损/有损存放目录
  2. 内置曲库未开归档：文件留在其当前所在格式目录内整理（MP3 里的→MP3/歌手/专辑，LOSSLESS 里的同理）
  3. 其他：**整理到选择的目录**（`root/relative_dir/歌手/专辑/歌曲`）
- 目标已存在同一首歌：**保留音质好的**（无损>有损，同类比文件大小）；源更差→删源（抢救 .lrc）、SongFile 指向保留文件；源更好→替换目标。preview 标注 `dedup_keep_existing`/`replace_lower_quality`，结果含 `deduped` 计数
- WebDAV 整理基于 SongFile.webdav_path，目标同样带所选目录前缀

### 单曲整理（刮削弹窗「整理到标准路径」，per-song organize）
- 入口仅刮削信息弹窗：后端 `POST /songs/{song_id}/organize/preview|apply`（`library_organize_service.preview_organize_song` / `apply_organize_song`），复用 `library_organize_service` 既有路径计算，不另起一套。
- 前置条件：`song.album` 与 `song.title` 均非通用目录名/未知（前端 `canOrganizeCurrent` 同口径）；不满足时 `apply` 直接抛 `ValueError`（HTTP 400「专辑或标题不完整，无法整理到标准路径」）。
- 冲突处理：同一歌曲多版本解析到同一标准路径（如 `歌曲名.flac` 与 `歌曲名(1).flac`）→ preview 按目标分组 `conflicts`，每候选带 `format`/`file_size`/`bitrate`（码率按需 `read_audio_bitrate_kbps` 探测，失败为 `None`）；apply 按 `choices` 保留所选，缺省保「码率更高、否则体积更大」者。**执行分两遍**：PASS1 删除非保留版本、PASS2 移动保留版本，且 PASS2 跳过 PASS1 已删除的 id（避免 UNIQUE `local_path` 冲突）。
- 跨歌曲占用：目标路径已属另一首歌的既有 `SongFile` → 该版本标 `blocked`，preview 提示、`apply` 跳过（`skipped++`），**绝不覆盖或删除他人文件**。
- 空目录清理：仅在两遍执行结束后，对"被动过的源父目录"做一次 `rmdir`，且**只删直接父目录、不向上递归**（避免误删其他歌曲/共享封面）；文件缺失标 `missing`、无本地源标 `no_source`、被占用标 `blocked` 的版本均不参与移动/删除。

### 易踩的坑

- **music.js 手工列字段**：`previewReorganize`/`applyReorganize` 等函数逐个列 body 字段，新增后端参数时必须同步加上（`relocate_format_dirs` 曾因此被丢，开关形同虚设）
- macOS 路径比较要先 `resolve()`（`/var` ↔ `/private/var`），`_format_base_dirs` 返回已 resolve 的路径
- `LRC_EXTS` 是 `tuple`、`IMAGE_EXTS` 是 `frozenset`，二者不能用 `|` 直接并；要 `set(LRC_EXTS) | IMAGE_EXTS`（否则 `TypeError` 会被 `apply_organize_song` 的 `except` 吞掉，导致重复版本删不掉、PASS2 又移动触发 UNIQUE 冲突）
- SQLite 读回的 datetime 可能是 naive，比较前归一化 tz
- 整理排除只对 root 内文件生效：对 `os.path.relpath` 产生 `..`（文件落在 root 之外，常见于 macOS `/var`↔`/private/var` 软链接）的版本不加排除，避免误伤正常文件；两边路径都先用 `Path(...).resolve()` 归一

---

## 11. 快速检查清单（PR / 发版前）

- [ ] `APP_VERSION` == `setup_app.py` == `web/package.json`
- [ ] `CHANGELOG.md` 已写本版要点
- [ ] 新增/修改的 Pydantic 模型可被 router import
- [ ] `task_worker` 与 service 方法签名一致
- [ ] 前端 `main.js` 注册了新用到的 Naive 组件
- [ ] 需要发版时：打 `v{版本号}` tag，release workflow 绿后再部署
- [ ] 无密钥进入 git

---

## 12. 相关文档

| 文件 | 用途 |
|------|------|
| `README.md` | 用户向说明与快速开始 |
| `CHANGELOG.md` | 版本变更史 |
| `CLAUDE.md` | 指向本文件的软链（Claude Code 入口） |
| `scripts/deploy-nas.sh` | 维护者 NAS 一键部署脚本 |

---

*本文件描述仓库协作约定；与全局用户规则冲突时，以更具体、更新的指令为准。*
