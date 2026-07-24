# AGENTS.md — 拾音 Sonpick

面向后续 AI Agent / 协作者的项目操作手册。改代码前先读本文件与 `CHANGELOG.md`。

---

## 0. 规范

- 我提出的要求可能是错的或者是外行的或者是不完整的，如果我的要求不是最佳实践，你应该及时提醒和询问，而不是迎合我的想法去修改。要避免产品设计走偏。
- 如果我的指令不完整、不明确、不合理、不一致，请随时告诉我询问我，而不是自己猜测或盲目执行。
- 当需要外部信息时，比如三方文档、数据源、API 文档等，如果使用你的内置工具查询不到，先询问我查找粘贴给你，而不是直接猜测编造。
- 要适当注意性能问题，尽量避免循环高频查询、一次载入大量数据、重复计算等。对于复杂的计算或数据处理，建议分批处理或使用缓存。
- 当代码进行了更新后，要及时更新 `AGENTS.md`、`README.md`、`CHANGELOG.md` 和其它相关文档。保持文档与代码的一致性。

---

## 1. 项目定位

可部署在 NAS 上的**个人音乐下载与管理** Web 应用。

- 搜索/批量下载音乐（基于 `musicdl`，当前主要 QQ 音乐源）
- 曲库：播放、转码 MP3、删除
- WebDAV：连接配置、目录浏览、代理播放、套件上传（音频+封面+歌词）
- 操作日志：下载 / 上传 / 删除 / 转码可查询
- 单用户密码登录（JWT）+ 白天/黑夜主题 + 底部全局播放器

**非目标**：多用户、公网商用、版权绕过。仅供个人学习与备份。

当前版本（以代码为准）：`0.12.1`（`setup_app.py` / `web/package.json` / `app/main.py` 的 `APP_VERSION` 必须一致）。

---

## 2. 技术栈

| 层 | 技术 |
|----|------|
| 后端 | FastAPI + SQLAlchemy 2.0 + SQLite |
| 前端 | Vue 3 + Vite + Naive UI + Pinia + Axios |
| 下载 | 内嵌 `musicdl/`（editable install） |
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
├── musicdl/                  # 下载引擎源码
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
| `/api/search` | `search.py` | 搜索 |
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
- **SongFile 是物理文件唯一真相源**：所有播放、上传、转码、删除、整理、刮削和标签写入必须通过 `SongFileResolver` 或明确 SongFile 查询选择版本；禁止重新引入 `Song.local_path` / `Song.webdav_path`。
- `Song.cover_path` / `Song.lrc_path` 是聚合缓存；`SongFile.cover_path` / `SongFile.lrc_path` 是版本侧车资源。扫描和选中版本时可回填聚合缓存。
- 扫描接口 `/api/library/scan` 和 `/api/sources/{source_id}/scan` 会创建 `type=scan` 的异步任务；前端经任务中心/单任务 SSE 接收终态。
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
- `TaskWorker`：后台线程池消费 `pending` 任务；进度写 `Task.progress_json` + WS 广播
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

---

## 7. 本地开发

```bash
# 后端
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e ./musicdl
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 前端（开发）
cd web && yarn && yarn dev
```

环境变量见 `.env`：`SECRET_KEY`、`STORAGE_PATH`、`DATABASE_PATH`、`DATA_DIR`。

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

---

## 10.1 架构速查（原 CLAUDE.md 合并内容）

### 后端分层

- `app/routers/`：薄路由层，约定 `except HTTPException: raise` + 兜底 `HTTPException(400, f"动作失败: {type(e).__name__}: {e}")`
- 关键服务备注：
  - `task_worker.py`：后台任务（线程池 max_workers=2，**线程不是进程**）
  - `musicdl_service.py`：搜索/下载，按格式落盘（`_format_base_dir`）
  - `library_organize_service.py`：曲库整理（preview/apply × local/webdav）
  - `library_scan_service.py` / `library_scan.py`：扫描入库
  - `scrape/`：元数据刮削管线（MusicBrainz → 网易/QQ/咪咕）
  - `media_meta_service.py`：标签/时长/封面读取（mutagen→tinytag→ffprobe；**无比特率工具**）
  - `convert_service.py`：转码 MP3（`LOSSLESS_FORMATS = {flac,wav,aiff,alac,ape}` 是全库唯一的无损判断权威）
  - `library_layout.py`：目录规范 `Artist/Album/Title.ext`、cover.jpg、同名 lrc、`sanitize_component`

### 任务系统细节

- `Task.status`：`pending/running/completed/failed/cancelled`；类型：`scan/scrape/convert/search_download/batch_download`
- 执行模型：线程池内跑同步函数，`worker_thread_id` 记录线程 ident（旧任务为 NULL）
- **watchdog**（60s 周期）：future 完成但状态仍 running、线程消亡、或**无 worker_thread_id 且任务时长超 4 小时**（历史遗留任务）→ 标记 `failed`
- 前端 TaskCenter 抽屉打开时 10s 兜底轮询
- 注意：**整理（reorganize）不走任务系统**，是同步 HTTP（前端 timeout 120s/600s）；扫描、下载、转码和刮削走 TaskWorker 异步任务

### 曲库整理规则（library_organize_service）

- 元数据优先级：DB（刮削结果）→ 内嵌标签 → 文件名解析；**缺专辑默认跳过**（`skip_missing_album`），失败文件进 `_failed/` 并写 `.error.txt`
- 目标 base 按文件决定（`_local_base_for_file`）：
  1. 开「按格式归档」(`relocate_format_dirs`)：按扩展名分流到无损/MP3 存放目录
  2. 内置曲库未开归档：文件留在其当前所在格式目录内整理（MP3 里的→MP3/歌手/专辑，LOSSLESS 里的同理）
  3. 其他：**整理到选择的目录**（`root/relative_dir/歌手/专辑/歌曲`）
- 目标已存在同一首歌：**保留音质好的**（无损>有损，同类比文件大小）；源更差→删源（抢救 .lrc）、SongFile 指向保留文件；源更好→替换目标。preview 标注 `dedup_keep_existing`/`replace_lower_quality`，结果含 `deduped` 计数
- WebDAV 整理基于 SongFile.webdav_path，目标同样带所选目录前缀

### 易踩的坑

- **music.js 手工列字段**：`previewReorganize`/`applyReorganize` 等函数逐个列 body 字段，新增后端参数时必须同步加上（`relocate_format_dirs` 曾因此被丢，开关形同虚设）
- macOS 路径比较要先 `resolve()`（`/var` ↔ `/private/var`），`_format_base_dirs` 返回已 resolve 的路径
- SQLite 读回的 datetime 可能是 naive，比较前归一化 tz

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
