# Changelog

## 0.5.3-rc28

### 修复
- 修复浅色模式播放队列背景过暗、文字可读性差的问题
- 播放器列表与右侧舞台接缝渐变改为跟随当前封面主色，和播放器背景氛围保持一致

## 0.5.3-rc27

### 改进
- 优化播放器页滚动条样式：改为细窄低对比滑块，支持浅色/暗色主题，减少歌曲列表边缘突兀感

## 0.5.3-rc26

### 改进
- 重做播放器页列表与播放器之间的明暗主题过渡：使用主题变量、低对比雾面底色和柔光接缝，补齐黑暗模式观感

## 0.5.3-rc25

### 改进
- 优化播放器页歌曲列表与右侧播放器之间的视觉过渡，去除硬黑线，改为半透明雾面背景与柔光渐变衔接

## 0.5.3-rc24

### 改进
- 播放器页面移除外层内容边距，舞台区域贴合可用空间展示

## 0.5.3-rc23

### 改进
- 隐藏播放器叠层模式歌词区域滚动条，保留歌词滚动能力与沉浸观感

## 0.5.3-rc22

### 改进
- 播放器封面、叠层、歌词三个舞台模式改为同时展示图标按钮，当前项高亮，另外两项可直接点击切换

## 0.5.3-rc21

### 改进
- 播放器顶部操作改为图标按钮，并通过悬浮提示展示封面、叠层、歌词、标签、刮削、队列文案
- 刮削按钮使用魔法棒图标，队列按钮保留数量角标

## 0.5.3-rc20

### 改进
- 优化播放器叠层模式：黑胶自适应放大并移至右上，歌词偏左展示且背景更透明
- 扩大封面模式唱片尺寸与封面占比，封面占黑胶直径约三分之二

## 0.5.3-rc19

### 改进
- 合并歌曲源与曲库页面，统一为左右结构的「曲库」页面
- 左侧曲库卡片保留添加、编辑、删除、测试、扫描、默认上传、整理和刮削功能
- 右侧支持「歌曲」与「浏览」模式，按所选曲库刷新歌曲列表或文件目录
- 侧边导航调整为概览、播放器、下载、曲库、日志、设置，并将 `/sources` 重定向到 `/library`

### 后端
- `/api/songs` 支持按 `source_id` 过滤歌曲
- 新增本地曲库只读浏览接口 `/api/sources/{source_id}/browse`

## 0.5.3-rc18

### 改进
- 新增根目录 `docker-compose.prod.yml` 作为 NAS 生产部署 Compose 模板
- `scripts/prepare-deploy.sh` 不再内联生成 Compose，改为复制 `docker-compose.prod.yml` 到 `deploy/docker-compose.yml`
- 后续修改 NAS Compose 配置只需改 `docker-compose.prod.yml`

## 0.5.3-rc17

### 修复
- 禁用歌曲源后，曲库 `/songs` 不再返回该源歌曲
- 播放器歌曲/收藏/历史/艺术家/专辑/歌单明细均过滤禁用源歌曲
- 概览统计按启用源歌曲计算收藏数与元数据完整度

## 0.5.3-rc16

### 修复
- `/app/downloads` 内置本地曲库源锁定名称和路径，后端拒绝修改
- `/app/downloads` 内置本地曲库源后端禁止删除
- 歌曲源页面对内置源显示「内置」标记，禁用名称/根目录输入，并隐藏删除按钮

## 0.5.3-rc15

### 修复
- 候选无 `cover_url` 时，QQ 来源会用 songmid 请求 `musicu.fcg` 获取 album mid 并拼封面 URL
- remote/WebDAV 歌曲采用候选时，会从候选 id / webdav_path / lrc_path 中提取 QQ songmid 兜底找封面
- `cover_result.lookup` 返回 QQ 封面补全详情，避免只看到 `missing cover_url`

## 0.5.3-rc14

### 修复
- 播放器歌词解析修复：正确解包 Axios response 的 `data`，避免接口有歌词但前端显示暂无歌词
- 封面下载按来源设置 Referer（网易/QQ/咪咕），并用图片魔数识别 JPEG/PNG/WebP/GIF，避免 Content-Type 不准导致误判失败
- `cover_result` 返回下载 URL，便于继续排查封面失败

## 0.5.3-rc13

### 修复
- 统一封面提取：支持 musicdl `SongInfo.cover_url`、raw_data 网易 `al.picUrl`、QQ album mid 拼图等来源
- SmartCN / musicdl / 候选接口统一返回 `cover_url`、`cover_source`、`has_cover`
- 封面下载返回 `cover_result`，失败时包含 HTTP/content-type/错误原因
- 自动刮削与手动采用候选均写 `cover.jpg`、DB `cover_path`，并写入音频内嵌封面
- 播放器候选表展示封面来源，采用后提示封面下载失败原因

## 0.5.3-rc12

### 新增
- 播放器新增「标签」按钮：展示当前歌曲 DB 信息与音频内嵌标签/封面状态
- 播放器「刮削」改为候选弹窗：自动评分/手动选择源，用户点击「采用」后写入 DB 与文件标签
- 新增 API：`/songs/{id}/tags`、`/songs/{id}/scrape/candidates`、`/songs/{id}/scrape/apply`

### 修复
- 候选采用时会下载封面并写入内嵌标签，便于排查“有专辑无封面”问题

## 0.5.3-rc11

### 修复
- 修复 QQ 标签串位：`title=songmid / artist=歌名 / album=歌手` 会还原为 `title=歌名 / artist=歌手`
- 匹配打分增强：候选歌手包含目标歌手（如 `刘惜君,王赫野` 包含 `王赫野`）按强命中计分
- 候选标题含 `伴奏` 而目标不含时降权，避免误选伴奏版
- Provider 命中后允许更新串位歌曲的 title/artist/album，确保刷新页面可见

## 0.5.3-rc10

### 改进
- 刮削前用本地 mutagen/tinytag/ffprobe 读取 `duration` 并写回 Song（不靠网络）
- 匹配打分加强时长项：±2s 高加成，差 >30s 强惩罚；SmartCN/musicdl 均使用本地 duration
- 联网刮削日志标注 `duration=... (local)` 便于核对

## 0.5.3-rc9

### 增强（参考 music-tag-web 策略，自研实现）
- 新增匹配打分 `scrape/match.py`：繁简归一 + title/artist/album 0/1/2 分 + 时长加成
- 新增华语直连：`netease_http` / `migu_http`（urllib，不经 musicdl）
- 新增 `SmartCNProvider`：网易/咪咕/QQ 并行搜索，统一打分取 Top1，日志输出 score=
- 默认刮削链：MusicBrainz → SmartCN → musicdl 兜底
- `write_audio_tags` 支持 lyrics/year/track + FLAC/MP3/M4A 内嵌封面
- 刮削写库后同步写标签（含歌词/封面侧车回写内嵌）

## 0.5.3-rc8

### 修复
- 刮削查询拆分：`画 赵雷` / `画-赵雷` → title=`画` artist=`赵雷`，避免整串当歌名搜
- musicdl 单源超时从 ~3s 提到 ≥15s（NAS 上 8 条结果后仍会拖几秒，3s 必超时）
- pipeline 单 provider/总超时放宽；本地拆分结果即使网络未命中也会写回 title/artist

## 0.5.3-rc7

### 修复
- 整理预览/应用：优先使用 DB 刮削结果（专辑/艺人），不再被空内嵌标签盖掉
- `_song_by_local` 路径匹配容错（resolve/后缀/歌名兜底），避免刮削后对不上库内歌曲导致「缺专辑跳过」
- 缺专辑时打 `reorganize skip_no_album` 日志，便于核对 song_id / db_album

## 0.5.3-rc6

### 修复
- 播放器播放队列在明亮模式下改用 Naive 主题变量（文字/背景/边框/高亮），不再固定暗色白字

## 0.5.3-rc5

### 改进
- 任务进度改为 SSE：`GET /api/tasks/{id}/events`（支持 `Authorization` 或 `?token=`）
- 前端刮削/播放器等待任务改用 EventSource，不再每 1.5s 轮询 `GET /api/tasks/{id}`
- 任务 emit 同步推送完整 Task 快照到 SSE 订阅者

## 0.5.3-rc4

### 调试
- 刮削日志输出每个源的搜索结果（前 8 条：title/artist/album/duration）
- 输出匹配命中/未命中分数与候选摘要
- pipeline 输出 provider 查询与命中字段

## 0.5.3-rc3

### 修复
- 刮削搜索词清洗：去掉 QQ songmid 前缀（如 `002mNoNz3sZvaI 人间道` → `人间道`）、曲序号与质量标签
- 匹配阈值放宽：无艺人信息时仍可按歌名命中网易/咪咕结果
- 刮削任务会先本地清洗标题再联网；乱码 mid 即使未命中网络也会写回干净歌名
- 整理预览联网改为短时 MusicBrainz 探测（清洗后查询），避免 musicdl 拖垮接口

### 说明
- 日志里 `Searching 002mNoNz3sZvaI 人间道` 即旧行为；rc3 后应变为 `Searching 人间道`
- 整理请默认关联网，先刮削再整理

## 0.5.3-rc2

### 修复
- 单曲 enrich 错误导入 `is_local_file`（应从 `media_meta_service` 导入）导致 500
- 播放时不再同步联网刮削；`POST /songs/{id}/enrich` 默认异步返回 `task_id`
- 刮削命中歌词时写入同名 `.lrc` 并回填 `lrc_path`

### 新增
- 播放器舞台右上角「刮削」按钮（当前曲异步任务 + 轮询）
- 播放器列表「刮削本页」（最多 50 首，异步任务）

## 0.5.3-rc1

### 新增
- 刮削改为异步任务（`Task.type=scrape`），前端轮询进度；结果写库，可选写回音频内嵌标签
- 刮削缓存表 `scrape_cache`，避免重复打外网
- musicdl 刮削链：Netease → QQ → Migu（与下载源解耦，下载仍默认 QQ）
- MusicDLService 支持可配置 `music_sources`（搜索/刮削）

### 修复 / 行为
- 整理默认跳过缺专辑条目，不再批量堆到 `Unknown Album`
- 多源刮削管线：MusicBrainz → musicdl 华语源串行兜底


## 0.5.2-rc2

### 修复
- 整理预览 `limit` 不再生效于扫描阶段：改为 `os.walk` 早停，收齐 N 首即返回（解决 Favorite 大目录扫全树超时、无日志）
- 整理预览/应用默认关闭联网补专辑；可选开启
- 预览默认不读音频时长，减少 NAS 随机读

### 优化
- 增加 `sonpick.reorganize` 扫描耗时日志；预览响应含 `elapsed_ms`


## 0.5.2-rc1

### 新增
- 元数据刮削改为可插拔多源管线：`app/services/scrape/`，按优先级兜底（默认 MusicBrainz → musicdl）
- MusicBrainz + Cover Art Archive 作为稳定优先源；musicdl/QQ 降为限时兜底

### 优化
- 刮削默认关闭网络、数量默认 20，避免反代超时
- 单源超时约 8s、整次网络总预算约 15–20s，避免 musicdl 卡死整请求

### 变更
- 单曲 enrich / 批量刮削 / 整理缺专辑补全 / resolve_song_meta 网络层统一走 scrape pipeline


## 0.5.1-rc1

### 新增
- 歌曲源「整理」支持表单：选择整理目录、最大数量（默认 20）、是否包含 `_failed`
- 新增 `GET /api/sources/{id}/reorganize/dirs` 列出可选子目录；预览/应用支持 `relative_dir` / `include_failed` / `limit`

### 优化
- 整理预览默认不再扫整库，需确认条件后生成预览再应用


## 0.5.0-rc8

### 修复
- 整理预览 `NameError: parse_filename_meta`：补全 `library_organize_service` 对 `library_layout.parse_filename_meta` 的导入
- 整理/刮削接口异常 `detail` 附带异常类型，前端歌曲源页完整展示错误文案

## 0.5.0-rc7

### 修复
- 文件名解析支持 `歌名-歌手`（如 画-赵雷）与 `歌名 - 歌手`，避免整理预览全成 Unknown Artist

### 优化
- 整理时若已解析出歌名+歌手但缺专辑：按歌名/歌手/时长网络匹配补全专辑（musicdl）
- 匹配打分加入时长容差（约 ±3s）；预览展示元数据来源

## 0.5.0-rc6

### 修复
- 修复歌曲源页 `scrapeSource` 标识符与 API 导入冲突导致前端构建失败

## 0.5.0-rc5

### 新增
- 歌曲源内置「整理」：预览后确认再 apply；按 `艺术家/专辑/歌名` 落盘，失败进 `_failed/`
- 歌曲源内置「刮削」：内嵌→侧车→可选网络，补全/纠正元数据
- WebDAV 浏览入口改到歌曲源操作（`/webdav?source_id=`），侧栏不再单独挂 WebDAV

### 优化
- WebDAV 列表/流支持 `source_id`；服务端支持 `exists_path` / `move_path` / `copy_path`

## 0.5.0-rc4

### 优化
- `scripts/reorganize_library.py` 可独立在 NAS 运行：默认根目录=脚本所在目录；`-r/--root` 指定曲库根
- 默认只整理文件，不依赖 app/DB；可选 `--with-db` / `--enrich`
- 文档明确依赖：标准库必选，`mutagen` 强烈建议

## 0.5.0-rc3

### 新增
- 曲库目录规范模块 `app/services/library_layout.py`：`艺术家/专辑/歌名` + `cover.jpg` / `artist.jpg` / 同名歌词
- 统一元数据管线 `resolve_song_meta`：内嵌 → 目录侧车 → DB → 可选网络补全
- 整理脚本 `scripts/reorganize_library.py`（默认 dry-run，`--apply` / `--enrich`）
- 下载页展示「曲库目录与命名规范」说明

### 优化
- 扫描/播放/封面读取统一走侧车命名约定；新下载写入规范目录并尽量生成 `cover.jpg`

## 0.5.0-rc2

### 修复
- 扫描优先读取音频内嵌标签（title/artist/album），不再把 Favorite/Downloads 等收藏目录误判为艺术家
- 本地/远程歌词侧车匹配增强：同 stem 大小写、模糊名、`.txt` 兜底；无侧车时尝试写出内嵌歌词
- 无时间轴纯文本歌词可在播放器展示（不再因解析不到时间戳而空白）

### 优化
- 新下载按元信息落盘：`艺术家/专辑/歌名.ext`（歌词与封面同目录）

## 0.5.0-rc1

### 新功能
- 多媒体源（local / webdav）：可添加多个本地与 WebDAV 源，维护连接状态、扫描目录与上传策略
- 新增「歌曲源」页：列表展示连通状态、上次扫描时间、歌曲数、默认上传标记；支持测试连接/扫描/设默认上传
- 扫描支持按 `source_ids` 或全部源；播放器「扫描曲库」改为弹窗选源，不再跳转设置
- 自动上传走默认 WebDAV 源；曲库手动上传可下拉选择源（默认源带标记）
- 「本地曲库」更名为「曲库」，列表展示歌曲来源
- 搜索下载与导入下载合并为「下载」页 Tab；搜索默认 20 条并支持分页
- 概览页展示歌曲数、元信息完整度、源统计与任务概况

### 兼容
- 启动时从旧 AppSettings 种子化默认本地/WebDAV 源并回填 `library_source_id`
- 旧 `/search`、`/import`、`/webdav` 路由重定向到新页面


## 0.4.0-rc17

### 修复

- 歌词加载支持同名侧车兜底：`lrc_path` 为空/失效时按 `local_path`/`webdav_path` 同 stem 查找 `.lrc`，并回填数据库
- 扫描更新时同步刷新失效的本地/远程 `lrc_path`

## 0.4.0-rc16

### 优化

- 重排黑胶几何：居中响应式尺寸，封面标签约 42% 盘径，避免右侧裁切溢出
- 新增舞台三模式：封面 / 叠层 / 歌词（`stageView` 切歌保留 + localStorage）
- 叠层模式：虚化透明黑胶作底，歌词在上，附可读性遮罩

## 0.4.0-rc15

### 优化

- 歌词默认字号加大（18px），支持 A-/A+ 调节（14–28），本地记忆
- 封面/歌词视图状态切歌时保留，并写入 localStorage
- 明亮模式播放器改为浅色舞台，与页面整体风格协调；深色模式保持沉浸感

## 0.4.0-rc14

### 修复

- 修复 LRC 歌词只展示不高亮：`GlobalPlayer` 进度更新改为走 `setProgress`，同步 `lyricIndex`
- 歌词滚动改为 `scrollIntoView(center)`，切换歌曲重置，手动滚动 2.5s 后恢复自动跟唱

## 0.4.0-rc13

### UI

- 播放器右侧改为 QQ 音乐风格沉浸台：封面主色透明渐变背景
- 大号黑胶唱片可溢出裁切，封面与歌词切换显示（点击封面看歌词）
- 歌词全幅高亮滚动，控制区与信息区更聚焦

## 0.4.0-rc12

### UI

- 歌曲列表改为自定义行布局，封面强制 40×40 裁剪，彻底避免原图撑爆
- 右侧播放台压缩唱片区，歌词区 flex 占满剩余高度并可滚动

## 0.4.0-rc11

### 修复

- 修复播放器 store 导出未定义的 `toggle` 导致 `ReferenceError: toggle is not defined`，连带 `togglePlay`/`playList` 失效

## 0.4.0-rc10

### 修复

- 修复 SQLite 连接池耗尽：`QueuePool limit ... connection timed out`
- SQLite 改用 `NullPool` + WAL/`busy_timeout`，适配多线程封面与后台任务
- 任务轮询/进度上报会话确保关闭；封面物化增加 miss 缓存，避免并发 WebDAV 打爆连接

## 0.4.0-rc9

### 修复

- 修复暂停/播放按钮报错：`player.toggle is not a function`（统一为 `togglePlay`，并保留 `toggle` 别名）

## 0.4.0-rc8

### UI

- 歌曲列表序号列加宽，三位数不再换行
- 封面缩略图固定 40×40 并 `object-fit: cover`，避免原图撑爆行高
- 「歌曲/专辑」列限制宽度，播放器页右侧舞台占比加大

## 0.4.0-rc7

### UI

- 播放器页去掉四周外边距与圆角边框，铺满内容区（仅预留底部全局播放器高度）

## 0.4.0-rc6

### UI

- 播放器布局重排：队列改为舞台内分栏，避免遮挡唱片/控制条
- 歌曲列表合并「歌曲 / 专辑」列，压缩行高，标题与副信息防溢出
- 播放面板/歌词/底栏全局播放器间距与截断优化

## 0.4.0-rc5

### 构建

- Docker 构建默认改用阿里云镜像源：Debian apt、PyPI；`Dockerfile.full` 的 npm 使用 npmmirror

## 0.4.0-rc4

### 修复 / 增强

- 扫描入库补齐歌曲时长（mutagen/tinytag/ffprobe）
- 扫描/下载提取内嵌封面并缓存到 `data/covers/`
- `/api/songs/{id}/cover` 支持从本地音频内嵌封面或 WebDAV 侧车物化缓存
- 下载任务写入 musicdl `duration_s`，失败时回退读本地文件
- 艺术家/专辑封面优先选择已有本地封面的代表曲

## 0.4.0-rc3

### 修复

- 修复 `WebDAVService.list` 遮蔽内置 `list` 导致注解 `list[dict]` 在类定义阶段报错，容器无法启动

## 0.4.0-rc2

### 功能

- 新增曲库扫描：支持本地目录与 WebDAV 递归扫描入库
- 设置页增加扫描目录、排除 glob、音频扩展名与「立即扫描」
- 扫描结果写入曲库（local/remote/both），可在播放器浏览与播放
- 播放器空库引导：提示前往设置扫描，并优化侧栏/内容区间距与卡片密度

## 0.4.0-rc1

### 功能

- 新增独立「播放器」页面：我喜欢的 / 歌单 / 艺术家 / 专辑 / 歌曲 / 最近播放
- 漂亮播放面板：唱片旋转封面、进度、音量、上一首/下一首、四种播放模式
- 歌词展示：LRC 解析、逐行高亮、自动居中滚动、点击跳转
- 播放队列：加入/移除/清空/跳转；底部迷你播放器同步控制
- 歌单 CRUD、收藏、播放历史与曲库统计 API
- 修复封面接口 `/api/songs/{id}/cover`（支持 token query）

## 0.3.1-rc3

### 修复

- WebDAV 未配置时 `list` 对 `None` 调用 `rstrip` 导致页面刷屏 500
- WebDAV 列表项/路径空值防护；前端错误 toast 去重

## 0.3.1-rc2

### 功能 / 部署

- 正式采用 NAS 运行包方案：`deploy/` + `scripts/deploy-nas.sh`
- 开发机默认 **pnpm** 构建前端，rsync 到 `qnap:/home/admin/Docker/sonpick`
- 远端仅 Python 镜像构建，不再拉 Node
- rsync 保护远端 `data/` `downloads/` `logs/` `.env`

## 0.3.1-rc1

### 修复

- 补回缺失的 `TaskOut` schema，修复容器启动 ImportError 导致的 502 / Restarting

## 0.3.1

### 修复

- 修复任务下载调用与 `MusicDLService` API 不一致导致的运行失败
- 修复 `ConvertService` 初始化与无效 `task_id` 字段
- 数据库引擎改为惰性初始化，避免 import 阶段路径问题
- 增加 `/health` 健康检查；Docker 默认使用预构建前端，避免每次拉 Node 镜像
- 新增 `deploy/` 轻量部署目录与 `scripts/prepare-deploy.sh`

### 调整

- compose 挂载 `./logs`；uvicorn 开启 `--proxy-headers` 适配反代

## 0.3.0

### 功能

- WebDAV 上传策略可配置：下载后自动上传、上传封面/歌词、同名冲突策略（重命名/覆盖/跳过）、上传后删除本地、远程子目录
- WebDAV 套件上传：音频 + 封面 + 歌词（同 stem）；冲突策略对每个文件生效；跳过时不删本地
- 上传路径与浏览根目录对齐，不再硬编码 `/music`
- 新增「操作日志」页面与 `/api/logs`：记录下载/上传/删除/转码，支持筛选、搜索、清空
- 曲库删除写入操作日志；下载任务自动上传结果写入任务进度与操作日志

### 调整

- 设置页仅保留自动上传总开关，细项在 WebDAV 页维护
- 前后端版本同步为 `0.3.0`，`X-App-Version` 同步

## 0.2.0

### 功能

- WebDAV 连接配置整合到 WebDAV 页面：支持内嵌可折叠配置表单（地址/用户名/密码/自动上传）
- WebDAV 页面状态机：`checking / not_configured / error / ready`，未配置引导设置，连接失败可重试
- WebDAV 浏览器 UI 优化：顶栏连接状态、面包屑、目录/音频图标色、文件类型标签、操作区分区

### 调整

- 设置页移除 WebDAV 地址/用户名/密码表单项，保留「自动上传 WebDAV」开关并引导至 WebDAV 页配置
- 后端 API 响应增加 `X-App-Version` 头，与应用版本号同步

## 0.1.0

- 初始版本：搜索下载、导入下载、本地曲库、WebDAV、全局播放器、主题切换、Docker 部署