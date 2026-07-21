# 拾音 Sonpick - 个人音乐下载与管理 Web 应用

一个可部署在 NAS 上的音乐下载 Web 小应用。基于 [musicdl](https://github.com/CharlesPikachu/musicdl) 实现搜索和下载，支持 WebDAV 上传、本地/WebDAV 音乐播放、白天/黑夜模式切换。

## 功能特性

- 🎵 **搜索与批量下载**：按歌曲/歌手搜索或导入歌单文本，任务中心异步执行并支持取消
- 📚 **多版本曲库**：一首逻辑歌曲可关联多个本地/WebDAV、FLAC/MP3 文件版本；按可用性、格式偏好与曲源优先级自动选择播放版本
- 📁 **曲库管理**：扫描、浏览、整理、刮削、转码 MP3、上传 WebDAV；文件移动后自动同步版本记录与侧车资源
- ☁️ **WebDAV 集成**：歌曲源配置、目录浏览、代理播放、音频+封面+歌词套件上传
- 🎧 **播放器与元数据**：全局播放器、歌词、封面、队列与播放历史；无可用文件版本会明确提示且禁止播放
- ✅ **任务中心**：下载、扫描、转码、刮削任务统一显示；WebSocket/SSE 推送进度和终态，完成/失败 toast 提示
- 📝 **操作日志**：下载、上传、删除、转码、整理等记录可查询
- 🌓 **主题与认证**：白天/黑夜主题；单用户密码登录与 JWT 认证
- ⚙️ **设置与歌曲源**：存储路径、格式目录、自动转码/上传、WebDAV 和刮削源设置

## 技术栈

- 后端：FastAPI + SQLite + SQLAlchemy 2.0
- 前端：Vue 3 + Vite + Naive UI + Pinia
- 下载引擎：musicdl
- 部署：Docker + docker-compose

## 快速开始

### 1. 克隆项目并进入目录

```bash
cd /Users/yuanjun/Work/my-projects/music
```

### 2. NAS 一键发布（推荐）

开发机（已配置 SSH Host `qnap`）：

```bash
./scripts/deploy-nas.sh --force-build
```

同步到 `/home/admin/Docker/sonpick`，NAS 仅构建 Python 镜像。前端使用 **pnpm** 构建。

### 2b. 使用 Docker Compose 本地部署


```bash
# 复制环境变量配置
cp .env.example .env

# 编辑 .env，设置强密码
# SECRET_KEY=your-strong-secret-key
# ADMIN_PASSWORD=your-admin-password

# 构建并启动
docker-compose up --build -d
```

访问 `http://your-nas-ip:8301`，使用 `ADMIN_PASSWORD` 中设置的密码登录。

### 3. 手动运行开发环境

```bash
# 后端
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e ./musicdl

# 前端（pnpm；Docker 运行镜像不含 Node）
cd web
pnpm install
pnpm build
cd ..

# 启动后端（生产模式会提供 web/dist；开发时通常配合 pnpm dev）
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 曲库与文件版本

- `Song` 是逻辑歌曲：用于列表、收藏、歌单、历史及聚合封面/歌词缓存。
- `SongFile` 是唯一物理文件真相：保存 local/WebDAV 路径、格式、侧车封面/歌词、可用状态与曲源优先级。
- 播放、上传、转码、刮削写标签和删除都通过版本解析器选择 `SongFile`；没有可用版本时页面会禁用播放并给出提示。
- 启动时 SQLite 迁移会把历史 `Song` 路径回填为 `SongFile`，随后删除旧路径列；路径异常可通过重新扫描修复。

### 任务与通知

- 下载、批量下载、扫描、转码、刮削均为后台任务；扫描接口会立即返回任务 ID，不阻塞 HTTP 请求。
- 任务中心经 WebSocket `/ws/progress` 实时更新；单任务可通过 SSE `GET /api/tasks/{id}/events?token=...` 订阅。
- worker 每 60 秒检查长时间无更新的 running 任务；线程已失联或任务僵尸化时会标记失败并推送终态。

### 部署与健康检查

运行镜像不含 Node。发布脚本先在开发机构建 `web/dist`，再同步 `deploy/` 到 NAS 并构建 Python 镜像。发布后检查：

```bash
curl -sS http://127.0.0.1:8301/health
```

响应应包含当前版本，且所有 HTTP 响应带 `X-App-Version`。


| 变量 | 说明 | 默认值 |
|------|------|--------|
| `SECRET_KEY` | JWT 和 WebDAV 密码加密密钥 | `change-me-in-production` |
| `ADMIN_PASSWORD` | 管理员初始密码 | `admin` |
| `STORAGE_PATH` | 音乐文件存储路径 | `./downloads` |
| `DATABASE_PATH` | SQLite 数据库路径 | `./data/music.db` |
| `DATA_DIR` | 数据目录 | `./data` |

## 使用指南

### 首次登录

首次访问时，输入 `ADMIN_PASSWORD` 中设置的密码即可登录，系统会自动创建管理员账户。

### 搜索下载

1. 进入「搜索下载」页面
2. 输入歌名或歌手，点击搜索
3. 在结果中选择想要的歌曲
4. 选择优先格式（FLAC / MP3 / 任意）
5. 点击「下载选中」

### 导入歌单下载

1. 进入「导入下载」页面
2. 粘贴歌单文本，每行一首，格式：`歌名 - 歌手`
3. 选择优先格式
4. 点击「开始批量下载」

### 本地曲库

- 播放：点击歌曲行的「播放」按钮
- 转码 MP3：对于 FLAC 等格式，可转码为 320kbps MP3
- 上传 WebDAV：将本地文件上传到配置的 WebDAV 服务器

### WebDAV 播放

1. 进入「WebDAV」页面，点击「连接配置」填写地址、用户名、密码并保存
2. 连接成功后浏览远程文件；未配置或连接失败会给出明确提示
3. 点击音频文件行的「播放」按钮即可播放

### 白天/黑夜模式

点击页面右上角的太阳/月亮图标即可切换。

## 项目结构

```
music/
├── app/                    # 后端代码
│   ├── main.py             # FastAPI 入口
│   ├── config.py           # 配置
│   ├── database.py         # SQLite 数据库
│   ├── models.py           # 数据模型
│   ├── schemas.py          # Pydantic 模型
│   ├── security.py         # 认证与加密
│   ├── routers/            # API 路由
│   └── services/           # 业务逻辑
├── web/                    # 前端代码
│   ├── src/
│   │   ├── views/          # 页面
│   │   ├── components/     # 组件
│   │   ├── stores/         # Pinia 状态
│   │   └── api/            # API 客户端
│   └── package.json
├── musicdl/                # musicdl 源码
├── scripts/                # 原有下载脚本
│   ├── batch_download.py
│   └── batch_convert_to_mp3.py
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
└── README.md
```

## 已知限制

1. **下载源有限**：目前主要依赖 QQMusicClient，部分 VIP/版权歌曲可能无法下载。
2. **下载耗时**：无损 FLAC 文件较大，下载可能需要数十秒，请耐心等待。
3. **WebDAV 兼容性**：不同 WebDAV 服务器对路径处理有差异，如遇列表为空请检查路径格式。
4. **浏览器播放格式**：FLAC 在某些浏览器上可能无法播放，建议下载 MP3 格式或使用转码功能。

## 安全提示

- 部署到公网时务必修改 `SECRET_KEY` 和 `ADMIN_PASSWORD`
- WebDAV 密码会加密存储，但安全性依赖于 `SECRET_KEY`
- 建议仅在家庭内网或配合反向代理 + HTTPS 使用

## 开发计划

- [x] 后端骨架（认证、设置、搜索、下载、曲库、WebDAV）
- [x] 前端页面（登录、搜索、导入、曲库、WebDAV、设置）
- [x] 全局播放器
- [x] 白天/黑夜模式
- [x] Docker 部署
- [ ] WebSocket 进度实时推送优化
- [ ] 歌词显示
- [ ] 播放列表/队列
- [ ] 更多音乐源支持

## 许可证

仅供个人学习和备份使用。请尊重音乐版权，支持正版音乐。
