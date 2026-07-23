# CLAUDE.md — 拾音 Sonpick

NAS 部署的个人音乐下载与管理 Web 应用。改代码前先读本文件，再按任务需要读 `AGENTS.md`（协作规范/部署/版本纪律/待办）、`CHANGELOG.md`（版本历史）。

## 技术架构

**后端**：FastAPI + SQLAlchemy 2.0 + SQLite（`data/music.db`），入口 `app/main.py`。
**前端**：Vue 3 + Vite + Naive UI + Pinia，源码 `web/src/`，构建产物 `web/dist/`（**pnpm 优先**；部署前必须重新 build，Docker 镜像不含 Node）。
**下载引擎**：内嵌 `musicdl/`（editable install，主要 QQ 音乐源）。
**部署**：打 `v*` tag 触发 GitHub Actions 构建多架构镜像（GHCR / Docker Hub / 阿里云 ACR 三推）；`deploy/` 目录已废弃不再入库。NAS 发布：`./scripts/deploy-nas.sh`（远端 pull 镜像重启）。

### 后端分层

- `app/routers/`：薄路由层，约定 `except HTTPException: raise` + 兜底 `HTTPException(400, f"动作失败: {type(e).__name__}: {e}")`。新增 response_model 必须在 `app/schemas.py` 定义（缺失会导致容器启动失败 502）。
- `app/services/`：业务层。关键服务：
  - `task_worker.py` — 后台任务（线程池 max_workers=2，**线程不是进程**）
  - `musicdl_service.py` — 搜索/下载，按格式落盘（`_format_base_dir`）
  - `library_organize_service.py` — 曲库整理（preview/apply × local/webdav）
  - `library_scan_service.py` / `library_scan.py` — 扫描入库
  - `scrape/` — 元数据刮削管线（MusicBrainz → 网易/QQ/咪咕）
  - `media_meta_service.py` — 标签/时长/封面读取（mutagen→tinytag→ffprobe；**无比特率工具**）
  - `convert_service.py` — 转码 MP3（`LOSSLESS_FORMATS = {flac,wav,aiff,alac,ape}` 是全库唯一的无损判断权威）
  - `webdav_service.py` / `operation_log_service.py`（`write_log` 写操作日志）
  - `library_layout.py` — 目录规范：`Artist/Album/Title.ext`、cover.jpg、同名 lrc、`sanitize_component`
- `app/models.py`：User / AppSettings（单行 id=1）/ MediaSource / Song / **SongFile** / Task / OperationLog 等。SQLite 加列走 `database._ensure_columns`，生产库不可重建。

### 任务系统（任务中心）

- `Task.status`：`pending/running/completed/failed/cancelled`；类型：`scan/scrape/convert/search_download/batch_download`。
- 执行模型：线程池内跑同步函数，`worker_thread_id` 记录线程 ident（旧任务为 NULL）。无 pid/start_time 字段，时长用 `created_at` 推算。
- **watchdog**（`task_worker._watchdog`，60s 周期）：future 完成但状态仍 running、线程消亡、或**无 worker_thread_id 且任务时长超 4 小时**（历史遗留任务）→ 标记 `failed`。
- 进度推送：WebSocket `/ws/progress` + SSE `GET /api/tasks/{id}/events`（支持 `?token=`，EventSource 不能设 header）。
- 前端：`web/src/components/TaskCenter.vue`（抽屉，非路由页），抽屉打开时 10s 兜底轮询。
- 注意：**整理（reorganize）不走任务系统**，是同步 HTTP（前端 timeout 120s/600s）；扫描、下载、转码和刮削走 TaskWorker 异步任务。

### 数据流与实时

前端 `web/src/api/music.js`（Axios 封装）→ `/api/*` 路由 → service → SQLite/文件系统。`Song.status`: `local/uploaded/both/remote`。

**SongFile 是文件路径的真相源**（0.8.0 起）：一首歌可有多个版本行（local_path 唯一约束、webdav_path），播放、上传、转码、删除、整理与标签写入都以 SongFile 为准。`Song` 不保存物理路径，只保留逻辑歌曲与聚合封面/歌词缓存；扫描或解析选中版本后可回填该缓存。

## 业务架构

| 域 | 入口（视图/路由） | 说明 |
|----|------|------|
| 搜索/导入下载 | DownloadView `/api/search` `/api/download` | musicdl 搜索，任务异步下载，按格式落到 MP3/无损目录 |
| 曲库 | LibraryView `/api/songs` | 播放、转码 MP3、上传 WebDAV、删除、整理、刮削 |
| 歌曲源 | SourcesView `/api/sources` | local/webdav 源 CRUD；**内置本地曲库**（root=storage_path，名称/路径锁定不可删）；扫描、整理 |
| 整理 | `library_organize_service` | 见下节 |
| WebDAV | WebDAVView `/api/webdav` | 浏览、代理播放、套件上传（音频+封面+歌词） |
| 任务中心 | TaskCenter `/api/tasks` | 见上节 |
| 操作日志 | LogsView `/api/logs` | action: download/upload/delete/convert/reorganize；status: success/failed/skipped/renamed/partial |
| 设置 | SettingsView `/api/settings` | 存储路径、`mp3_output_path`、`lossless_output_path`（默认 `<storage>/MP3`、`/LOSSLESS`）、自动转码/上传 |
| 认证 | LoginView `/api/auth` | 单用户密码 + JWT；音频 URL 常带 `?token=` |

### 曲库整理规则（library_organize_service，preview 生成计划 / apply 执行）

- 元数据优先级：DB（刮削结果）→ 内嵌标签 → 文件名解析；**缺专辑默认跳过**（`skip_missing_album`），失败文件进 `_failed/` 并写 `.error.txt`。
- 目标 base 按文件决定（`_local_base_for_file`）：
  1. 开「按格式归档」(`relocate_format_dirs`)：按扩展名分流到无损/MP3 存放目录；
  2. 内置曲库未开归档：文件留在其当前所在格式目录内整理（MP3 里的→MP3/歌手/专辑，LOSSLESS 里的同理）；
  3. 其他：**整理到选择的目录**（`root/relative_dir/歌手/专辑/歌曲`）。
- 目标已存在同一首歌：**保留音质好的**（无损>有损，同类比文件大小）；源更差→删源（抢救 .lrc）、SongFile 指向保留文件；源更好→替换目标。preview 标注 `dedup_keep_existing`/`replace_lower_quality`，结果含 `deduped` 计数。
- WebDAV 整理基于 SongFile.webdav_path，目标同样带所选目录前缀。

## 易踩的坑

- **music.js 手工列字段**：`previewReorganize`/`applyReorganize` 等函数逐个列 body 字段，新增后端参数时必须同步加上（`relocate_format_dirs` 曾因此被丢，开关形同虚设）。
- macOS 路径比较要先 `resolve()`（`/var` ↔ `/private/var`），`_format_base_dirs` 返回已 resolve 的路径。
- SQLite 读回的 datetime 可能是 naive，比较前归一化 tz。
- 版本号四处同步：`setup_app.py`、`web/package.json`、`app/main.py` APP_VERSION、CHANGELOG.md；bugfix 只升 rc。当前 0.10.0-rc4。
- 新 Naive UI 组件要在 `web/src/main.js` 注册。
- 自检：后端 `curl localhost:8000/health`；前端 `cd web && pnpm build`。

## 本地开发

```bash
source venv/bin/activate && uvicorn app.main:app --port 8000 --reload   # 后端
cd web && pnpm install && pnpm dev                                       # 前端
```
