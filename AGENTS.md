# AGENTS.md — 拾音 Sonpick

面向后续 AI Agent / 协作者的项目操作手册。改代码前先读本文件与 `product-overview.md`、`CHANGELOG.md`。

---

## 1. 项目定位

可部署在 NAS 上的**个人音乐下载与管理** Web 应用。

- 搜索/批量下载音乐（基于 `musicdl`，当前主要 QQ 音乐源）
- 曲库：播放、转码 MP3、删除
- WebDAV：连接配置、目录浏览、代理播放、套件上传（音频+封面+歌词）
- 操作日志：下载 / 上传 / 删除 / 转码可查询
- 单用户密码登录（JWT）+ 白天/黑夜主题 + 底部全局播放器

**非目标**：多用户、公网商用、版权绕过。仅供个人学习与备份。

当前版本（以代码为准）：`0.5.0-rc5`（`setup_app.py` / `web/package.json` / `app/main.py` 的 `APP_VERSION` 必须一致）。

---

## 2. 技术栈

| 层 | 技术 |
|----|------|
| 后端 | FastAPI + SQLAlchemy 2.0 + SQLite |
| 前端 | Vue 3 + Vite + Naive UI + Pinia + Axios |
| 下载 | 内嵌 `musicdl/`（editable install） |
| 转码 | 系统 `ffmpeg` |
| 部署 | Docker / docker-compose；默认镜像**不含 Node** |

包管理：本项目前端 **优先 pnpm**（`packageManager` 字段）；无 pnpm 时再 yarn/npm。发布脚本默认 pnpm。

---

## 3. 目录结构（关键）

```text
music/
├── app/                      # FastAPI 后端
│   ├── main.py               # 入口、路由挂载、静态资源、/health、X-App-Version
│   ├── config.py             # 环境变量 Settings
│   ├── database.py           # SQLite 引擎（惰性初始化）+ 轻量迁移
│   ├── models.py             # User / AppSettings / Task / Song / OperationLog
│   ├── schemas.py            # Pydantic 模型（含 TaskOut、Settings*、OperationLogOut）
│   ├── security.py           # 密码哈希 + JWT
│   ├── routers/              # API 路由
│   └── services/             # 业务：musicdl / webdav / convert / task_worker / operation_log
├── web/                      # 前端源码
│   ├── src/views/            # 页面
│   ├── src/stores/           # Pinia
│   ├── src/api/client.js     # Axios 封装
│   └── dist/                 # 构建产物（Docker 默认 COPY 这里）
├── musicdl/                  # 下载引擎源码
├── deploy/                   # NAS 轻量部署包（无 Node 构建）
├── scripts/prepare-deploy.sh # 同步 app + web/dist + musicdl 到 deploy/
├── Dockerfile                # 运行时镜像（需本地已 build 前端）
├── Dockerfile.full           # 应急：容器内 Node 构建前端
├── docker-compose.yml
├── CHANGELOG.md
├── product-overview.md
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
- SQLite 增量字段：在 `database._ensure_columns` 添加，**不要**假设生产库会重建

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
| `/library` | LibraryView | 曲库 |
| `/player` | PlayerView | 播放器 |
| `/sources` | SourcesView | 歌曲源（local/webdav）管理 |
| `/logs` | LogsView | 操作日志 |
| `/settings` | SettingsView | 存储路径/默认格式/自动转码/自动上传总开关 |

**配置归属**：

- WebDAV 地址/账号密码/冲突策略/侧车/删本地/远程子目录 → **只在歌曲源页**
- 设置页可保留「自动上传」总开关，并链接到歌曲源页细项，避免双源维护

### 5.2 UI / 工程

- 组件库：Naive UI；图标：`@vicons/ionicons5`
- 新 Naive 组件要在 `web/src/main.js` **import 并注册**（未全量 unplugin 自动引入时尤其注意）
- 全局播放器：Pinia `player` store；音频 URL 常带 `token` query
- 主题：`theme` store；`App.vue` 使用 `n-config-provider` + dialog/message provider
- 前端文案：当前仓库以中文硬编码为主；**若新增 React 代码**，全局规则要求走 i18n、禁止硬编码用户可见字符串。现有 Vue 页面保持项目既有风格，不强制一次性 i18n 化

### 5.3 构建

```bash
cd web
pnpm install && pnpm build   # 优先
# fallback: yarn build / npm run build
```

产物：`web/dist/`。改前端后部署前必须重新 build（默认 Docker 不再容器内构建）。

---

## 6. 版本与变更纪律（必须）

语义化版本，允许预发布：`MAJOR.MINOR.PATCH` 或 `MAJOR.MINOR.PATCH-rcN`。

| 变更类型 | 版本怎么动 |
|----------|------------|
| 新功能 | 提升正式版本位（按影响选 minor/patch） |
| 仅 bugfix | **只升 rc**（如 `0.5.0-rc5` → `0.5.0-rc5`），不抬正式位 |
| 每次改代码 | 前后端版本号**必须一致** |

必须同步的位置：

1. `setup_app.py` → `version=...`
2. `web/package.json`（及 lock 中顶层 version）
3. `app/main.py` → `APP_VERSION`
4. `CHANGELOG.md` 追加条目
5. `product-overview.md` 中「当前设计要点」版本与要点

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

环境变量见 `.env.example`：`SECRET_KEY`、`ADMIN_PASSWORD`、`STORAGE_PATH`、`DATABASE_PATH`、`DATA_DIR`。

自检：

```bash
curl -sS http://127.0.0.1:8000/health
```

---

## 8. 部署（NAS / Docker）

### 8.1 生产唯一路径

| 项 | 值 |
|----|-----|
| SSH | `Host qnap` → `nas.liuyuanjun.com:9022` user `admin` |
| 远端目录 | `/home/admin/Docker/sonpick` |
| 发布命令 | `./scripts/deploy-nas.sh`（可加 `--force-build`） |
| 前端构建 | 开发机 **pnpm**，产物进 `deploy/web/dist` |
| NAS 构建 | 仅 Python 镜像，**无 Node** |

```bash
./scripts/deploy-nas.sh --force-build
# 远端
ssh qnap 'curl -sS http://127.0.0.1:8301/health'
docker compose logs 见远端目录
```

只打包：`./scripts/prepare-deploy.sh` 或 `./scripts/deploy-nas.sh --pack-only`。

### 8.2 数据与密钥

- `data/` `downloads/` `logs/` 留在 NAS；rsync **不覆盖/不删除** 这些目录与 `.env`
- 首次自动从 `.env.example` 生成 `.env`，请改 `SECRET_KEY` / `ADMIN_PASSWORD`

### 8.3 502 / Restarting

1. `ssh qnap 'cd /home/admin/Docker/sonpick && docker compose ps && docker compose logs --tail=200'`
2. `curl http://127.0.0.1:8301/health`
3. 常见：schemas 缺模型导致 ImportError 启动失败



## 9. Agent 工作流（改代码时）

1. **先读再改**：相关 router/service/view 与 `models`/`schemas` 一起看，避免 API 签名漂移  
2. **窄改动**：复用现有 Naive UI / Pinia / 服务层模式，不引入未在 `requirements.txt` / `package.json` 声明的库  
3. **schemas 与 routers 同步**：新增 response_model 必须在 `schemas.py` 定义  
4. **服务调用对齐**：改 `MusicDLService` / `ConvertService` / `WebDAVService` 签名时，同步 `task_worker` 与 routers  
5. **WebDAV 配置单源**：细项放 WebDAV 页；设置页不恢复整套连接表单  
6. **文件操作写日志**：下载/上传/删除/转码走 `operation_log_service`  
7. **版本 + CHANGELOG + product-overview** 同一次改完  
8. **部署相关**：若影响运行镜像，更新 `Dockerfile`/`deploy/` 并跑 `prepare-deploy.sh`  
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

**待办（product-overview）**

- WebSocket 进度体验优化
- 歌词显示
- 播放列表/队列
- 更多音乐源
- remote-only 曲库完整体验

---

## 11. 快速检查清单（PR / 发版前）

- [ ] `APP_VERSION` == `setup_app.py` == `web/package.json`
- [ ] `CHANGELOG.md` 已写本版要点
- [ ] `product-overview.md` 已更新
- [ ] 新增/修改的 Pydantic 模型可被 router import
- [ ] `task_worker` 与 service 方法签名一致
- [ ] 前端 `main.js` 注册了新用到的 Naive 组件
- [ ] 需要部署时：`web/dist` 已构建，`prepare-deploy.sh` 已跑
- [ ] 无密钥进入 git

---

## 12. 相关文档

| 文件 | 用途 |
|------|------|
| `README.md` | 用户向说明与快速开始 |
| `product-overview.md` | 产品现状与待办 |
| `CHANGELOG.md` | 版本变更史 |
| `PROJECT_GUIDE.md` | 历史项目理解文档（可能编码/内容偏旧，**以本 AGENTS.md 与源码为准**） |
| `deploy/README.md` | NAS 部署目录说明 |

---

*本文件描述仓库协作约定；与全局用户规则冲突时，以更具体、更新的指令为准。*
