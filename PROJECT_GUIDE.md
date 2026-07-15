# 拾音 Sonpick 项目理解文档

> 本文档面向后续维护/改动的 AI Agent，帮助你快速、准确地理解本项目。

---

## 1. 项目定位

这是一个部署在 NAS 上的个人音乐下载与管理 Web 应用。

- **核心能力**：从 QQ 音乐（通过 musicdl 库）搜索、下载歌曲，保存到本地，支持转码 MP3、上传到 WebDAV、在线播放。
- **目标用户**：个人用户，单点登录，家庭内网使用。
- **部署形态**：Docker 容器，FastAPI 后端 + Vue 3 前端。

---

## 2. 目录结构

```
music/
├── app/                          # 后端 FastAPI 应用
│   ├── main.py                   # 应用入口、路由挂载、WebSocket、静态文件
│   ├── config.py                 # Pydantic Settings，读取环境变量
│   ├── database.py               # SQLite + SQLAlchemy 2.0，初始化与 Session
│   ├── models.py                 # SQLAlchemy 数据模型
│   ├── schemas.py                # Pydantic 请求/响应模型 + WebDAV 密码加解密
│   ├── security.py               # HMAC-SHA256 密码哈希 + JWT 生成/解码
│   ├── routers/                  # API 路由（按功能拆分）
│   │   ├── auth.py               # 登录、JWT 校验
│   │   ├── settings.py           # 系统设置读写
│   │   ├── search.py             # 歌曲搜索
│   │   ├── download.py           # 单首/批量下载任务提交
│   │   ├── tasks.py              # 任务列表、详情、取消
│   │   ├── library.py            # 本地曲库、音频流、封面、转码、上传
│   │   └── webdav.py             # WebDAV 列表、流代理
│   └── services/                 # 业务逻辑
│       ├── musicdl_service.py    # 封装 musicdl 搜索/下载/文件移动/封面下载
│       ├── convert_service.py    # FFmpeg 转码 FLAC → MP3（保留封面）
│       ├── webdav_service.py     # WebDAV 客户端封装、上传、流代理
│       └── task_worker.py        # 后台任务队列 + WebSocket 进度广播
├── web/                          # 前端 Vue 3 应用
│   ├── src/
│   │   ├── main.js               # 入口：注册 Naive UI 组件
│   │   ├── App.vue               # 根组件，主题配置
│   │   ├── router.js             # Vue Router，路由守卫
│   │   ├── api/client.js         # Axios 封装 + WebSocket URL 构建
│   │   ├── stores/               # Pinia 状态管理
│   │   │   ├── auth.js           # 登录态/token
│   │   │   ├── theme.js          # 白天/黑夜模式
│   │   │   └── player.js         # 全局播放器状态
│   │   ├── views/                # 页面组件
│   │   │   ├── LoginView.vue
│   │   │   ├── LayoutView.vue    # 侧边栏 + 顶部栏 + 播放器容器
│   │   │   ├── DashboardView.vue
│   │   │   ├── SearchView.vue
│   │   │   ├── ImportView.vue
│   │   │   ├── LibraryView.vue
│   │   │   ├── WebDAVView.vue
│   │   │   └── SettingsView.vue
│   │   ├── components/
│   │   │   └── GlobalPlayer.vue  # 底部全局播放器
│   │   └── composables/
│   │       └── useWebSocket.js   # WebSocket 连接封装
│   ├── package.json
│   ├── vite.config.js
│   └── index.html
├── musicdl/                      # 第三方下载库源码（可编辑安装）
├── scripts/                      # 原有命令行脚本（保留，可被 Web 应用调用思路复用）
│   ├── batch_download.py
│   └── batch_convert_to_mp3.py
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
├── README.md
└── PROJECT_GUIDE.md              # 本文档
```

---

## 3. 后端核心设计

### 3.1 应用启动流程

`app/main.py` 的 `lifespan` 会做两件事：
1. `init_db()`：创建 SQLite 表。
2. 启动 `worker.process_loop()`：后台从队列取任务执行。

### 3.2 认证

- 登录：`POST /api/auth/login`，首次登录时用该密码创建管理员账户。
- 密码哈希：使用 `app/security.py` 中的 HMAC-SHA256 + 随机盐，避免 bcrypt 长度限制。
- Token：JWT，7 天有效期，后续请求通过 `Authorization: Bearer <token>` 传递。
- WebSocket：`/ws/progress?token=...` 通过 query 传 token。

### 3.3 数据库模型

详见 `app/models.py`：

- `User`：仅一条记录，存密码哈希。
- `AppSettings`：仅一条记录（`id=1`），存存储路径、WebDAV 配置、默认格式、自动转码/上传开关。
- `Task`：下载/转码/上传任务，含 `status`、`progress_json`、`result_json`、`error_message`。
- `Song`：本地曲库，记录文件路径、封面、歌词、WebDAV 路径等。
- `Playlist`：导入的歌单历史（当前未在前端使用）。

### 3.4 任务队列

`app/services/task_worker.py`：

- 使用 `asyncio.Queue` + `ThreadPoolExecutor(max_workers=2)`。
- `process_loop` 是异步主循环，从队列取任务 ID。
- `_run_sync` 在线程中执行阻塞操作（musicdl 搜索下载、FFmpeg 转码、WebDAV 上传）。
- `emit(task_id, message, percent)` 更新任务进度到数据库，并通过 WebSocket 广播。

**重要**：`musicdl` 的搜索/下载是阻塞且可能耗时较长的，因此必须在线程池中执行，不能放在 async 协程里。

### 3.5 与 musicdl 的集成

`app/services/musicdl_service.py`：

- 导入 musicdl 前会移除当前目录下的 `musicdl/` 源码路径，避免与已安装的包冲突。
- 初始化 `musicdl.MusicClient`，指定 `QQMusicClient`。
- `search()`：返回有效下载链接的结果列表。
- `download_one()`：搜索 → 按优先格式挑选 → 下载 → 移动文件到输出目录 → 下载封面 → 写入 `Song` 记录。
- 文件命名：`歌名-歌手.扩展名`。

### 3.6 文件下载与存储

- 配置存储路径：`settings.storage_path`（默认 `./downloads`）。
- musicdl 原始输出在 `<storage_path>/.musicdl_work/QQMusicClient/<时间戳> <关键词>/`。
- `_move_files()` 把音频、歌词文件重命名为 `歌名-歌手.*` 并平铺到 `<storage_path>`。
- 封面单独下载为 `歌名-歌手.jpg`。

### 3.7 转码

`app/services/convert_service.py`：

- 调用 `ffmpeg`。
- 命令参数：`-map 0 -c:v copy -ar 44100 -ac 2 -b:a 320k -map_metadata 0 -id3v2_version 3`。
- 输出到 `mp3/` 子目录，保留原 FLAC 不变。
- 转码成功后会在 `songs` 表中新增一条 `format='mp3'` 的记录，方便曲库直接看到 MP3。
- **注意**：会保留 FLAC 内嵌封面到 MP3。

### 3.8 WebDAV

`app/services/webdav_service.py`：

- 使用 `webdavclient3` 做上传和目录列表。
- 使用 `aiohttp` 做流代理，支持 `Range` 请求，浏览器播放器可拖动进度。
- WebDAV 密码用 Fernet 加密存储在数据库，密钥由 `SECRET_KEY` 派生。

### 3.9 音频流接口

- 本地：`/api/songs/{id}/stream`，支持 HTTP Range。
- WebDAV：`/api/webdav/stream?path=...`，后端代理并支持 Range。

---

## 4. 前端核心设计

### 4.1 技术栈

- Vue 3 Composition API
- Vite 构建
- Naive UI 组件库
- Pinia 状态管理
- Vue Router
- Axios

### 4.2 主题

- `stores/theme.js` 管理 `isDark`。
- `App.vue` 通过 `n-config-provider :theme="isDark ? darkTheme : lightTheme"` 切换。
- 主题偏好保存在 `localStorage.sonpick_theme`。

### 4.3 路由

```
/login            -> 登录页
/                 -> 仪表盘（需登录）
/search           -> 搜索下载
/import           -> 导入下载
/library          -> 本地曲库
/webdav           -> WebDAV 浏览器
/settings         -> 设置
```

### 4.4 播放器

- `components/GlobalPlayer.vue` 固定在页面底部。
- 播放源通过 `stores/player.js` 的 `src` 设置。
- 本地歌曲：`/api/songs/{id}/stream?token=...`
- WebDAV：`/api/webdav/stream?path=...&token=...`

### 4.5 API 客户端

`api/client.js`：

- 自动从 `localStorage` 读取 token 加到请求头。
- 401 时自动登出并跳转登录页。
- `wsUrl(token)` 构造 WebSocket 地址。

---

## 5. 部署

### 5.1 Docker（推荐）

```bash
cp .env.example .env
# 编辑 .env
docker-compose up --build -d
```

### 5.2 本地开发

```bash
# 后端
source venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 前端（另一个终端）
cd web
npm install
npm run dev
```

### 5.3 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `SECRET_KEY` | JWT/WebDAV 加密密钥 | `change-me-in-production` |
| `ADMIN_PASSWORD` | 初始管理员密码 | `admin` |
| `STORAGE_PATH` | 音乐存储路径 | `./downloads` |
| `DATABASE_PATH` | SQLite 路径 | `./data/music.db` |
| `DATA_DIR` | 数据目录 | `./data` |

---

## 6. 修改约定

### 6.1 后端

- 新增 API：在 `app/routers/` 下创建/修改 router，在 `app/main.py` 中注册。
- 新增数据库表：在 `app/models.py` 定义模型，重启后 `init_db()` 会自动创建表。
- 新增业务逻辑：放在 `app/services/`。
- 所有需要认证的接口都依赖 `get_current_user`。
- 密码相关操作使用 `app/security.py` 中的函数，不要自己实现哈希。

### 6.2 前端

- 新增页面：在 `web/src/views/` 创建 Vue 组件，在 `web/src/router.js` 注册。
- 新增状态：在 `web/src/stores/` 创建 Pinia store。
- 调用后端：通过 `web/src/api/client.js`。
- 需要使用的 Naive UI 组件必须在 `web/src/main.js` 中注册。

### 6.3 musicdl 包冲突

**务必注意**：项目目录下有 `musicdl/` 源码目录。在 `app/services/musicdl_service.py` 中已经做了路径清理：

```python
_script_dir = Path(__file__).resolve().parent.parent.parent
for _p in list(sys.path):
    rp = os.path.realpath(_p)
    if rp in (os.path.realpath(os.getcwd()), os.path.realpath(str(_script_dir))):
        sys.path.remove(_p)
```

如果你在其他地方也要 `import musicdl`，请复用这段逻辑，否则可能导入源码目录而不是已安装的包。

---

## 7. 常见问题与排查

### 7.1 任务一直显示 running，没有进度

- musicdl 搜索/下载可能耗时较长，尤其是 FLAC 无损文件。
- 后端 worker 在线程池中执行，文件可能已下载成功，只是进度未频繁更新。
- 查看 `<storage_path>` 下是否有新文件生成。

### 7.2 下载失败

- 检查网络是否能访问 QQ 音乐相关接口。
- 检查 `settings.storage_path` 是否有写入权限。
- 部分 VIP/版权歌曲可能无法下载。

### 7.3 WebDAV 无法播放

- 检查 WebDAV 地址、用户名、密码是否正确。
- 检查 WebDAV 服务器是否支持 Range 请求（后端代理会转发 Range）。
- 浏览器开发者工具查看 `/api/webdav/stream` 请求状态。

### 7.4 前端构建失败

- 常见原因：使用了未在 `main.js` 中注册的 Naive UI 组件。
- 检查 `package.json` 中是否有非法包名（如 `vicons/ionicons5`，应为 `@vicons/ionicons5`）。

### 7.5 bcrypt 相关问题

项目已不再使用 bcrypt/passlib，改用 HMAC-SHA256。如果后续要重新引入 bcrypt，注意 bcrypt 5.0 与 passlib 存在兼容性问题和 72 字节密码长度限制。

---

## 8. 待改进项（已知）

- [ ] 任务进度实时性：当前 `emit` 只在关键节点调用，大文件下载中间无进度，可改为在 musicdl 下载时定期回调或轮询文件大小。
- [ ] 前端全局播放器：当前只有播放/暂停/进度条，可添加播放列表、上一首/下一首。
- [ ] 歌词显示：已下载 `.lrc` 文件，但前端尚未展示。
- [ ] 批量任务重试：失败歌曲目前没有单独重试机制。
- [ ] WebDAV 目录结构：目前上传到 `/music` 目录，可配置化。
- [ ] 更多音乐源：目前仅启用 QQMusicClient。

---

## 9. 关键文件速查

| 功能 | 文件 |
|------|------|
| 应用入口 | `app/main.py` |
| 数据库模型 | `app/models.py` |
| 登录认证 | `app/routers/auth.py`、`app/security.py` |
| 系统设置 | `app/routers/settings.py` |
| 搜索 | `app/routers/search.py`、`app/services/musicdl_service.py` |
| 下载任务 | `app/routers/download.py`、`app/services/task_worker.py` |
| 曲库/流/转码 | `app/routers/library.py`、`app/services/convert_service.py` |
| WebDAV | `app/routers/webdav.py`、`app/services/webdav_service.py` |
| 前端路由 | `web/src/router.js` |
| 前端状态 | `web/src/stores/*.js` |
| 前端页面 | `web/src/views/*.vue` |
| 全局播放器 | `web/src/components/GlobalPlayer.vue` |
| 部署 | `Dockerfile`、`docker-compose.yml` |

---

## 10. 安全提示

- 修改默认的 `SECRET_KEY` 和 `ADMIN_PASSWORD`。
- 公网部署建议配合反向代理（Nginx/Caddy）和 HTTPS。
- WebDAV 密码加密存储，但加密强度取决于 `SECRET_KEY`。

---

*文档版本：2026-07-13*
