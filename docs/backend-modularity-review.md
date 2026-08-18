# 后端模块化与治理评审（Sonpick / 拾音）

> 评审范围：并发整改（ff53320）**之外**的后端架构。
> 前置阅读：`docs/backend-concurrency-review.md`、`docs/backend-architecture-proposal.md`（P0–P4 已完成）。
> 结论先行：**"各自为政"的病根没有随并发整改一起消失，它在另外五个维度同样成立**——
> 并发只是其中一个症状。本评审按"同一根因的其它表现"组织，均附源码证据与优先级。

---

## 0. 一句话结论

ff53320 把**线程**收口了，但**外部 HTTP、源注册表、格式权威、分层边界、日志、封面下载**仍然各自为政——
每个 provider / service 都在自己的角落里重新发明一遍基础能力。这不是"还差几个 TODO"，而是同一个
"AI 长时间迭代、局部实现、缺乏统一抽象"模式的**平行复发**。

---

## 🔴 严重（Critical）：正确性 / 刚建立的治理原则被违反

### C1. 格式权威双定义且内容矛盾（`LOSSLESS_FORMATS` 有对错之分）

AGENTS.md §10.1 明确写：`convert_service.py` 的 `LOSSLESS_FORMATS = {flac,wav,aiff,alac,ape}` 是
**"全库唯一的无损判断权威"**。但实际存在第二个同名常量：

- `app/services/convert_service.py:18` → `{"flac","wav","aiff","alac","ape"}`
- `app/services/song_file_resolver.py:10` → `{"flac","wav","aiff","alac","ape","dsf","dff"}`

两处内容**不一致**（resolver 多出 `dsf/dff`）。后果：

- 同一首 `dsf`/`dff`（DSD）文件，**播放选择**（`song_file_resolver`）当作无损优先，
  但**转码/无损判断**（`convert_service`）当作有损。
- "唯一权威"这句约定在代码里是假的——权威被复制且走样。这是"各自为政"最精确的教科书案例。

**建议**：删掉 `song_file_resolver.py` 的重复定义，统一 `from app.services.convert_service import LOSSLESS_FORMATS`
（或下沉到 `app/services/constants.py`）。连同下面的 L1 一起做。

### C2. 外部调用治理只收口了约 3/8（P4 的"已挂接"远未覆盖）

P4 建立的 `host_limiter.py` 是"新增外部 HTTP 调用必须挂接 `get_limiter(host)`"的唯一治理组件，
但实际只挂了 **3 处**：

| 已挂接 | 未挂接（裸 `urlopen`） |
|--------|------------------------|
| `netease_http.py:48`（music.163.com） | `musicbrainz.py:36`（MusicBrainz + Cover Art Archive）|
| `migu_http.py:34`（m.music.migu.cn） | `deezer.py:29`（api.deezer.com）|
| `lrclib_provider.py:37`（lrclib.net） | `itunes.py:43`（iTunes）|
| | `acoustid.py:53`（api.acoustid.org）|
| | `cover_utils.py:209/258`（封面下载：QQ `u.y.qq.com` / 163 / 咪咕）|
| | `musicdl_service.py:554`（封面下载，走 `requests`）|

**最痛的后果**：MusicBrainz 对 API 有**硬性 1 req/s** 速率限制，违反会返回 503 甚至封禁；
现在它完全不经过任何限流器，只靠 scrape lane（并发 2）粗放约束。其它源（Deezer/iTunes/AcoustID）同理。

**根因**：每个 provider 都自己写了一份 `_http_json`/`_do` 内联 HTTP 助手
（`musicbrainz.py:26`、`deezer.py` 内联、`itunes.py` 内联、`acoustid.py` 内联、`cover_utils.py:49` 还自建了
IPv4 opener）。**HTTP 层没有统一的 client 抽象**，所以限流、超时、UA、错误处理都被各自复制。

---

## 🟠 高（High）：架构混乱 / 高维护成本 / 高未来风险

### H1. 两套源注册表 + 跨注册表 hack（刮削 vs 歌词）

- `app/services/scrape/source_registry.py`：7 个源，字段 `{id,name,tier,enabled,auto_enabled,priority,region}`
- `app/services/lyrics_source_registry.py`：3 个源，字段 `{id,name,enabled,auto_enabled,priority,timeout,capabilities,description}`

两套**字段 schema 不同**、却各有一份几乎同构的 `source_configs` / `dump_*_configs` / `select_*_configs`
（同一套"deepcopy 默认 + merge 存储 + 排序"逻辑复制了两遍）。`netease` / `migu` 同时出现在两套里。

更明显的坏味道是**跨注册表 hack**：`lyrics_source_registry.py:53-72` 在歌词源未单独配置时，
去读 `scrape_raw`（刮削配置）来继承网易/咪咕的开关状态。两个本应独立的"源"靠读对方的存储互相传染配置。

**建议**：抽象一层 `SourceConfig`（id/name/enabled/auto_enabled/priority + 类型专属扩展字段），
刮削与歌词都从它派生；"歌词源继承刮削源开关"这种一次性兼容逻辑集中到一处并标注为迁移。

### H2. 分层反向依赖：service / database import router

共享常量与 helper 定义在了**路由层**，被服务层和数据层反向 import：

- `app/routers/settings.py:29,60` 定义 `_parse_json_list`、`_ensure_settings`
- `app/routers/settings.py:18,26` 定义 `DEFAULT_SCAN_EXCLUDE`、`DEFAULT_SCAN_EXTS`
- 反向引用方：`app/services/library_scan_service.py:14`、`app/services/webdav_service.py:14`、
  `app/database.py:365`（种子源时 import）

`_ensure_settings`（"确保单行 settings 存在"）是**纯数据访问职责**，却住在 router 里。这制造了
`router → service → router` 的近循环依赖，也让"settings 的获取与播种"没有唯一实现点
（`webdav_service`、`database._seed_media_sources`、`settings.py` 各自维护一份获取/播种逻辑）。

**建议**：把 `_ensure_settings` / `_parse_json_list` / 扫描默认常量下沉到 `app/services/settings_service.py`
或 `app/core/constants.py`；router 与 service 都从那里取，消灭反向 import。

### H3. 封面下载三套实现 + 未声明的 `requests` 依赖

同一件"下载封面到本地"存在三个实现：

1. `app/services/musicdl_service.py:549` `_download_cover` —— 用 `requests`（`554` 行 `import requests` 在**函数内**）
2. `app/services/scrape/pipeline.py:205` `_download_cover` —— 用 `urllib`
3. `app/services/scrape/cover_utils.py:189` `download_cover_with_diagnostics` —— 用 `urllib` + 自建 IPv4 opener

附带问题：`requests` 在代码里被使用（`musicdl_service.py:554`），但 `requirements.txt` **未声明**
（只声明了 `aiohttp`、`webdavclient3`）。现在能跑全靠 `musicdl` 的传递依赖——上游一旦改动即静默崩坏。

**建议**：统一到 `cover_utils.download_cover_with_diagnostics`（它已含 referer/IPv4/诊断信息），
删掉另两套；要么显式声明 `requests`，要么把 `musicdl_service._download_cover` 也改回 urllib。

---

## 🟡 中（Medium）：一致性 / 卫生

### M1. 日志体系不一致：`print()` 与 `logging` 混用

- 全库 25 处 `print()`，其中 **19 处在刚重构的 `task_worker.py`**（`[loop push error]`、`[flusher error]`、
  `[watchdog error]`…），另有 `database.py` 迁移打印、`cli.py` 交互输出。
- 对比：`musicdl_service.py` / `netease_http.py` / `migu_http.py` 用 `logging.getLogger("sonpick.scrape")`。

刚做完并发整改的文件还在用 `print()` 报错——日志维度根本没被纳入整改范围。容器 stdout 下
`print` 与 `logging` 会交错、无时间戳/级别/模块名，排障时不可 grep、不可分级。

**建议**：`task_worker.py` / `database.py` 迁移统一改 `logging`；`cli.py` 保留 `print`（面向终端）。

### M2. SQLite 单写者纪律未落实（提案 §2 写了"收口单 writer"，但没做）

提案目标架构里明确有"写：收口为单 writer（写队列或全局写锁保护）"，但 `backend-architecture-proposal.md`
的"明确不做"里没有它，代码里也没有写锁/写队列。目前只靠 **lane 上限**（download=1/convert=1/scrape=2/scan=1）
间接缓解：

- scrape=2 意味着 **2 个并发刮削可同时写** SQLite；
- 同步 HTTP 端点（整理/扫描/转码，走 `def` 端点）跑在 FastAPI 的 **40 线程 anyio 池**里，与任务 lane 互不知晓，
  会和任务 worker 并发写。

`NullPool + WAL + busy_timeout=30000` 现在能扛住，但这是"靠超时兜底"而非"靠纪律"。一旦并发继续放开，
写争用会重新冒头（正是并发评审 M1 预警过的"可扩展性悬崖"）。

**建议**：至少为"写路径"引入一个进程内 `threading.Lock`（或分 lane 写锁），收口在数据访问层；
不要靠 SQLite busy_timeout 当唯一防线。

### M3. 双线程池并存（FastAPI 线程池 + execution 内核嵌套）

所有路由都是 `def`（同步）端点，FastAPI 会放进自己的 anyio 线程池（默认 40）；而服务内部又
`execution.submit(...)` 到 `sonpick-io` 池（10）再走 lane 信号量。于是：

`FastAPI 40 线程池 → service → sonpick-io 10 线程池 → lane`

两层受控池嵌套。虽然比之前的"裸线程满天飞"干净得多，但仍是两个并发模型叠加，资源上限不直观、
排障要同时看两处。搜索 SSE 端点（`search.py:120` `def search_stream`）正是"同步端点里再 submit 到内核"的典型。

**建议**：可选优化——把这些端点改 `async def`，阻塞调用统一 `execution.submit`，去掉 FastAPI 那一层；
或至少在 AGENTS.md 里写明"端点用 `def`、阻塞一律走 execution"的单一约定，避免新人再加一层。

---

## 🟢 低（Low）：代码卫生

### L1. 音频扩展名 / 格式常量多处定义

- `convert_service.py:18` `LOSSLESS_FORMATS`（见 C1）
- `song_file_resolver.py:10` `LOSSLESS_FORMATS`（重复，见 C1）
- `library_organize_service.py:43` `AUDIO_EXTS = {".mp3",".flac",...}`
- `library_layout.py:31` `AUDIO_EXTS`
- `routers/settings.py:26` `DEFAULT_SCAN_EXTS = "mp3,flac,m4a,..."`（字符串形式）
- `database.py:83` 迁移 DDL 里**又硬编码了一份**同款默认值

格式/扩展名是"什么是音频、什么是无损"的元问题，现在有 5+ 处定义且形式（set vs tuple vs string）不一。
建议统一到一处常量模块，迁移 DDL 里那处硬编码至少加注释指向权威来源。

---

## ✅ 已做对的地方（避免重做 / 保持）

- **会话获取一致**：所有 service 统一接收 `db: Session` 参数（依赖注入），没有叶子函数自建 Session；
  `Session(engine)` 只出现在 `database.py` 种子逻辑。这是全项目做得最干净的一层，别动。
- **并发内核收口**：`execution.py` 已消灭自建池 / 裸线程（搜索 SSE、播放转码均已接入），C2 的遗留是
  HTTP 治理维度，不是线程维度。
- **SSE 搜索已接入内核**：`search.py:165` `executor_submit(run_search, lane="search")`，裸线程已清零。

---

## 整改路线（按 收益/风险 排序）

| 阶段 | 内容 | 工作量 | 风险 | 收益 |
|------|------|--------|------|------|
| **R1 常量与权威收口** | 统一 `LOSSLESS_FORMATS`（修 C1）、音频扩展名（L1）、封面下载三合一（H3） | 0.5 天 | 极低 | 消除一个真正确性分歧 + 三处重复实现 |
| **R2 外部 HTTP 层统一** | 新建 `app/services/http_client.py`（统一 UA/超时/错误/get_limiter），把 musicbrainz/deezer/itunes/acoustid/cover_utils 全部收编（修 C2） | 2–3 天 | 低 | P4 治理真正落地；MusicBrainz 1req/s 不再裸奔 |
| **R3 分层与源注册表** | `_ensure_settings`/扫描常量下沉（H2）；`SourceConfig` 统一刮削/歌词注册表（H1）；补声明 `requests` 或去掉 | 2–3 天 | 中 | 消灭反向 import 与跨注册表 hack，源系统真正可插拔 |
| **R4 日志收口** | `task_worker`/`database` 迁移 `print→logging`（M1） | 0.5 天 | 极低 | 排障可分级/可 grep |
| **R5 单写者纪律** | 写路径进程内写锁（M2）；可选端点 async 化（M3） | 1–2 天 | 中 | 为任务继续并行化扫清 SQLite 障碍 |

**推荐顺序**：R1（顺手、零风险、立刻止血 C1 正确性 bug）→ R4（最便宜）→ R2（把 P4 未竟的治理收尾）
→ R3 → R5。R1+R4 一个下午可做完；R2+R3 是"各自为政"根治的主力。

> 与并发整改一致的纪律：bugfix 性质只升 rc；每个阶段独立发 rc 并同步 `AGENTS.md` / `CHANGELOG.md`。
