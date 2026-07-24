# 拾音 Sonpick

> 当前版本：`0.12.1-rc1`

部署在 NAS 上、供个人使用的音乐下载与管理 Web 应用。它将搜索下载、本地曲库、WebDAV 曲库、播放和文件操作收在一个单用户界面中。

Sonpick 仅用于个人学习与已获授权内容的备份管理，不面向多用户或公网商用，也不用于绕过版权或平台限制。

## 功能

- 搜索歌曲或导入文本列表批量下载，当前主要使用 QQ 音乐源
- 曲库扫描、浏览、整理、刮削、转码 MP3 和删除文件
- 本地与 WebDAV 多媒体源；同一逻辑歌曲可保留多个 FLAC、MP3 或远端版本
- WebDAV 套件上传：音频与可选封面、歌词一起上传，支持重命名、覆盖或跳过冲突
- 全局播放器、封面、同步歌词、播放队列、收藏、歌单、艺术家、专辑和播放历史
- 下载、扫描、转码和刮削任务中心，实时展示任务状态与操作日志
- 单用户密码登录、JWT 认证，以及明暗主题和移动端适配

## 架构

| 层 | 技术 |
|---|---|
| 后端 | FastAPI、SQLAlchemy 2.0、SQLite |
| 前端 | Vue 3、Vite、Naive UI、Pinia |
| 下载 | 内嵌 `musicdl/`（editable install） |
| 媒体处理 | 系统 `ffmpeg` |
| 部署 | Docker Compose；生产镜像不包含 Node |

曲库中 `Song` 表示逻辑歌曲，`SongFile` 是本地或 WebDAV 物理文件版本的唯一真相来源。播放、转码、上传与删除都会先选择实际可用的 `SongFile`；同一首歌可同时拥有本地和远端、无损和 MP3 等版本。

## 日常使用

1. 首次打开站点会引导设置管理员密码（至少 6 位）。设置后用该密码登录；密码存储在数据库中，不再依赖环境变量。
2. 修改密码：登录后点击顶栏的钥匙图标，验证旧密码后设置新密码。
3. 忘记密码：在部署服务器上执行以下命令，按提示输入新密码即可重置（需要能访问容器的 shell 权限）：
   ```bash
   docker exec -it sonpick python -m app.cli reset-password
   ```
4. 在「下载」页搜索或导入歌曲列表。搜索结果会标记已存在或疑似已存在的曲目；下载前可以选择保留两个版本或替换指定本地版本。
5. 在「曲库」页管理本地和 WebDAV 来源、扫描目录、浏览文件、整理或刮削。WebDAV 地址、账号、密码及上传冲突策略只在这里配置。
6. 在「设置」页调整存储路径、格式偏好、自动转码和自动上传总开关。
7. 从曲库或播放器页面播放歌曲。播放器支持队列、歌词点击跳转与进度条拖动；暂停时定位进度不会自动开始播放。

下载、扫描、转码、刮削均以后台任务执行。可从顶栏任务中心查看进度、结果和失败信息；文件操作会写入「操作日志」。

## Docker 部署

Sonpick 可部署在任何支持 Docker Compose 的 NAS、家庭服务器或 Linux 主机上。发布镜像已包含前端页面与全部后端依赖（amd64 与 arm64），无需安装 Node 或 Python。

### 使用预构建镜像（推荐）

```bash
mkdir sonpick && cd sonpick
curl -fsSL https://raw.githubusercontent.com/liuyuanjun/sonpick/main/docker-compose.yml -o docker-compose.yml
mkdir -p data downloads logs
```

创建 `.env` 设置登录密码与密钥：

```dotenv
SECRET_KEY=replace-with-a-long-random-value
```

按需修改 `docker-compose.yml` 的端口（`ports`）和音乐目录挂载（`volumes` 中 `/app/downloads` 对应的宿主机路径），然后启动：

```bash
docker compose up -d
docker compose ps
docker compose logs -f --tail=100
```

在浏览器打开 `http://<server-address>:<host-port>`，首次访问会提示设置管理员密码。健康检查地址为 `http://<server-address>:<host-port>/health`，应返回类似 `{"status":"ok","version":"..."}` 的响应；所有 HTTP 响应也会带 `X-App-Version` 头。

镜像同时发布到三个仓库，默认 compose 使用 GHCR；网络环境受限时可任选其一，通过 `SONPICK_IMAGE` 覆盖：

```bash
# Docker Hub
SONPICK_IMAGE=<dockerhub-user>/sonpick:latest docker compose up -d
# 阿里云 ACR（国内网络通常更稳定）
SONPICK_IMAGE=registry.cn-beijing.aliyuncs.com/<namespace>/sonpick:latest docker compose up -d
```

升级时修改 compose 或 `.env` 中的镜像 tag 后执行 `docker compose pull && docker compose up -d`。请保留 `data/`、音乐目录和 `.env`——应用会自动执行轻量 SQLite 迁移，不要通过删除数据库来升级。

### 从源码构建镜像

```bash
git clone <repository-url> sonpick
cd sonpick
docker build -t sonpick:local .
# 国内构建可加速：--build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
```

构建产物为多阶段镜像，前端在镜像内自动构建。随后将 compose 中 `SONPICK_IMAGE` 指向 `sonpick:local` 即可。

## 本地开发

### 前置条件

- Python 3.10 或更高版本
- Node.js 与项目声明的 pnpm（当前为 `pnpm@10.33.0`）
- `ffmpeg`：转码功能需要；曲库中其他功能可先运行

### 启动后端

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r musicdl/requirements.txt
pip install -e ./musicdl

# 可选：在项目根目录创建 .env，填入本地开发配置
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

后端默认读取项目根目录的 `.env`；该文件未纳入版本控制。可按需设置：

```dotenv
SECRET_KEY=replace-with-a-long-random-value
STORAGE_PATH=/absolute/path/to/music
DATABASE_PATH=/absolute/path/to/data/music.db
DATA_DIR=/absolute/path/to/data
```

未设置时，开发环境默认使用项目内的 `downloads/` 和 `data/music.db`。不要将真实 WebDAV 密码、JWT 或生产 `SECRET_KEY` 提交到仓库。

### 启动前端

另开一个终端：

```bash
cd web
pnpm install
pnpm dev
```

前端开发服务器默认运行在 `http://127.0.0.1:5173`，并将 `/api` 和 `/ws` 代理到 `http://127.0.0.1:8000`。构建生产静态资源：

```bash
pnpm build
```

构建产物为 `web/dist/`，后端检测到它存在时会负责托管前端；可用下列命令快速检查后端：

```bash
curl -sS http://127.0.0.1:8000/health
```

## 数据、来源与任务

| 位置 | 用途 | 注意事项 |
|---|---|---|
| `data/` | SQLite 数据库 | 生产环境保留，不要通过删库重建升级 |
| `downloads/` | 本地音乐文件 | 容器中通常挂载为 `/app/downloads` |
| `logs/` | Compose 挂载点 | 应用主日志通常用 `docker compose logs` 查看 |
| `.env` | 本地或 NAS 密钥 | 不提交；发布脚本不会覆盖 NAS 上的版本 |

应用启动时会执行轻量 SQLite 迁移并初始化默认本地来源。扫描接口会创建异步任务，而不会在请求中长时间阻塞。对已有音乐目录或 WebDAV 内容重新入库时，请在「曲库」页选择对应来源后执行扫描。

WebDAV 上传按音频文件逐个处理冲突策略：`rename`、`overwrite` 或 `skip`。启用“上传后删除本地文件”时，只有音频确实上传、覆盖或重命名成功才会删除本地文件；因冲突跳过的文件不会删除。

## 项目结构

```text
music/
├── app/                      # FastAPI 路由、模型和服务
├── web/                      # Vue 源码；web/dist 为生产构建产物
├── musicdl/                  # 内嵌下载引擎
├── .github/workflows/        # 发版 workflow：tag 触发镜像构建与三仓库推送
├── scripts/
│   └── deploy-nas.sh         # 项目维护者的 NAS 一键部署脚本
├── Dockerfile                # 多阶段镜像（前端构建 + Python 运行时）
├── docker-compose.yml        # 基于预构建镜像的通用示例
├── CHANGELOG.md              # 版本变更记录
└── AGENTS.md                 # 协作与发布约定
```

## 限制与安全

- 当前下载源有限，VIP、版权限制或接口变动可能导致下载失败。
- 浏览器对 FLAC 的支持不一致，必要时可在曲库中转码为 MP3。
- 不同 WebDAV 服务端的路径与目录列表行为可能不同；连接异常时先用曲库来源管理中的测试功能确认配置。
- remote-only（上传后删除本地）的完整曲库体验仍在完善中。
- 生产环境务必修改 `SECRET_KEY`（至少 32 字符的随机字符串）；启动时会检测默认值并打安全警告。WebDAV 密码经过加密保存，其安全性依赖于 `SECRET_KEY`。注意：修改 `SECRET_KEY` 后已存储的 WebDAV 密码将无法解密，需重新填写。
- 忘记密码时可通过 CLI 重置（详见上方「日常使用」），命令为 `docker exec -it sonpick python -m app.cli reset-password`。
- 建议仅部署在可信内网，或通过 HTTPS 反向代理对外提供访问。反向代理需支持 WebSocket `/ws/progress`。

## 相关文档

- [变更记录](CHANGELOG.md)：版本历史

## 许可证

仅供个人学习与个人音乐管理使用。请尊重音乐版权并支持正版内容。
