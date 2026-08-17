# 后端并发架构改造提案（Sonpick / 拾音）

> 状态：**✅ P0–P4 全部完成**（0.15.0-rc18 ~ rc21，2026-08-17）
> 日期：2026-08-17
> 前置阅读：`docs/backend-concurrency-review.md`（并发现状评审，结论已经源码逐条核实）
> 本文档是后端并发架构的目标设计与改造路线图，作为后续 P1–P4 实施的依据。
>
> **实施说明**：① 为减少结构扰动，新模块落在 `app/services/`（`execution.py` /
> `host_limiter.py`），未新建 `app/core/` 包；`task_worker.py` 原地重构。
> ② P1/P2 交织实施（P1 依赖 P2 的执行内核），合并发于 rc19；P3=rc20，P4=rc21。

---

## 1. 设计前提：本项目的"最优"不是通用最优

| 约束 | 对设计的含义 |
|------|--------------|
| 单用户、NAS（ARM、内存小） | 并发量级峰值 <10；**不需要高吞吐，需要可预测、低资源、可自愈** |
| 单进程、SQLite | 不引入 Redis/Celery 等中间件；写路径必须保持单写者纪律 |
| 阻塞 I/O 为主（musicdl 同步请求、ffmpeg、WebDAV、mutagen） | asyncio + 受控线程池是正确路线，纯 async 重写是负收益 |
| 运维能力低、无人值守 | 任何挂死必须自愈（超时、watchdog、重启恢复）；任何失败必须可见（日志/任务中心） |

目标架构的关键词：**一个事件循环、一个受控执行引擎、一条写路径、一套外部调用治理**。
评判标准不是"线程少"，而是"并发策略是否集中、可调、可观测"。

## 2. 目标架构

```
┌─ FastAPI 路由层（薄：鉴权/校验/入队/返回句柄，同步 def 端点逐步迁 async）
│
├─ app/core/execution.py        ← 全项目唯一的"线程里跑阻塞调用"入口
│    ├─ BlockingExecutor        单例 ThreadPoolExecutor(N≈6, 命名线程)
│    ├─ run_blocking(fn, lane, timeout, cancel_event)
│    └─ run_with_hard_timeout() 短命池模式的唯一实现（带僵尸线程计数指标）
│         ▲ 收口替换现有 8+ 处自建池
│         （musicdl_service.py:196,255,943、smart_cn_provider.py:33,104、
│           musicdl_provider.py:51、search.py 裸线程、library.py 裸线程）
│
├─ app/core/tasks.py            ← 任务系统
│    ├─ asyncio.Queue 内存队列（DB 只做持久化 + 重启恢复 pending）
│    ├─ M 个 worker 协程 × Lane 并发策略：download=1, convert=1, scrape=2, search=4
│    ├─ 原子 claim：UPDATE tasks SET status='running' WHERE id=? AND status='pending'
│    │   按 rowcount 判归属（多进程/多 worker 天然安全）
│    └─ watchdog 保留（防挂死自愈），阈值按 lane 可配
│
├─ app/core/events.py           ← 进程内事件总线
│    ├─ emit() 只做非阻塞 put 事件（不再每次开 2 个 DB session）
│    ├─ flusher 协程：批量/节流（≥500ms 或 ≥20 条）落库 progress_json
│    └─ WS / SSE / 单任务订阅都是 subscriber，搜索进度与任务进度同一套
│
├─ app/core/httpguard.py        ← 外部资源治理
│    ├─ HostLimiter(host)：信号量 + 最小间隔 + 429 退避（per-host 而非全局锁）
│    │   → LRCLIB/网易/咪咕/QQ/musicdl 各挂各的，替代 lrclib_provider 类级大锁
│    └─ 强制 timeout（连接/读分离）；musicdl 不能注入超时的走 run_with_hard_timeout
│
├─ 数据层
│    ├─ 读：WAL 下自由读（现状即可）
│    └─ 写：收口为单 writer（写队列或全局写锁保护）——为任务真并行扫清 SQLite 障碍
│
└─ lifespan 集中管理：executor / limiter / eventbus / queue 显式 startup+shutdown，
    消灭 import 期副作用（worker = TaskWorker() 模块级单例）
```

### 关键决策的理由

1. **保留线程跑阻塞 I/O，但全项目只剩 2 个池**：共享 executor + 硬超时 helper 内部的受控短命池。`max_workers=1` 池是对不可中断阻塞调用做硬超时的唯一 CPython 手段，不能简单删——要收口成一个带指标的工具函数，并为超时后仍在跑的僵尸线程预留池容量（否则共享池会被挂死的调用耗尽槽位）。
2. **任务调度从"轮询 DB"改为"内存队列 + DB 持久化"**：调度延迟从 1s 轮询降到即时，DB 只剩 claim/终态/恢复三次交互。这是当前架构与未来任何扩展（重试、优先级、按 lane 并行）之间真正的分水岭。
3. **进度上报与持久化解耦**：现在 `emit()` 每次 tick 开 2 个 session 同步 commit，是热路径上最重的点。事件总线 + flusher 批量落库后，worker 线程的 emit 变成 O(1) 内存操作。
4. **限流器是通用组件而不是某个 provider 的私货**：LRCLIB 的全局锁只是症状，病根是"每个外部源自己想办法"。per-host `HostLimiter` 一次实现，所有源挂接。
5. **任务并行度做成 lane 配置而非全局开关**：下载/上传串行（对源友好、规避 SQLite 写争用）、搜索可并行 4、转码限 1（CPU）。比"串行 or 并行"二选一更符合实际。

## 3. 改造路线（按 收益/风险 排序）

| 阶段 | 内容 | 工作量 | 风险 | 收益 | 状态 |
|------|------|--------|------|------|------|
| **P0 正确性修复** | ① 原子 claim ② `run_coroutine_threadsafe` 容错 + 日志 ③ `get_running_loop()` ④ 全量 HTTP 超时审计 ⑤ 文档同步 | ~1 天 | 极低 | 消除多进程重复执行、静默失败两类正确性隐患 | ✅ 已完成（0.15.0-rc18） |
| **P1 收编裸线程** | ① 搜索 SSE：裸线程 → 受控 executor + 信号量限并发（≤3）② 播放自动转码：改为 `type=convert` 任务走任务系统（天然获得进度/日志/取消/防重复，删 `_converting_song_ids` 内存去重） | 2–3 天 | 低 | 消灭无上限线程；转码从黑盒变可见任务 | ✅ 已完成（0.15.0-rc19） |
| **P2 并发内核** | 新建 `execution.py`（共享 executor + `run_with_hard_timeout` + lane 信号量），替换全部自建池 | 3–5 天 | 中（搜索超时/取消语义需回归测试） | "满天飞"根治；线程数可观测、有上限 | ✅ 已完成（0.15.0-rc19） |
| **P3 任务系统重构** | 内存队列 + lane worker 协程 + 事件总线 + flusher；启动恢复 pending；lifespan 收口生命周期 | 5–8 天 | **最高**（需充分测试：取消、watchdog、重启恢复、SSE 终态不丢） | 调度即时化、emit 轻量化、多 lane 并行 | ✅ 已完成（0.15.0-rc20） |
| **P4 外部治理** | `HostLimiter` 组件；LRCLIB 全局锁改造；各源挂接；统一 timeout 配置项 | 2–3 天 | 低 | 限流从全局互斥变 per-host 并行且守规矩 | ✅ 已完成（0.15.0-rc21） |

### P0 实施记录（0.15.0-rc18）

- **原子 claim**：`task_worker._run_sync` 改用 ORM `update(Task).where(id, status='pending').values(...)`，按 `rowcount` 判归属，未抢到直接返回。多进程/多 worker 下同一任务不会被重复执行。
- **loop 推送容错**：新增 `TaskWorker._push_to_loop()`，收口 worker 内全部 `run_coroutine_threadsafe`（emit / 终态广播 / watchdog）：失败时节流记日志（前 5 次 + 每 100 次）并 `coro.close()` 防 "never awaited" 警告；不再让异常传播误杀任务，也不再静默丢失。`TaskEventHub.publish_threadsafe` 同步加日志。
- **`get_running_loop()`**：`task_worker.process_loop` 与 `main.lifespan` 均已修正。
- **HTTP 超时审计结论**：全部 urllib/requests 调用均有 timeout；webdavclient3 默认 30s；WebDAV 代理播放的 aiohttp 会话补上 `connect=15/sock_connect=15`（total 保持 None，长流播放不受影响）。
- **文档同步**：`AGENTS.md` §10.1 watchdog 描述更新为实际行为（30 分钟无更新 + 只看 future 状态）。

### P1/P2 实施记录（0.15.0-rc19）

- **统一并发内核** `app/services/execution.py`：共享线程池（`sonpick-io`，max_workers=10）+ lane 信号量（search=4 / scrape=2 / download=2，worker 线程内 acquire）+ `run_with_hard_timeout`（超时线程弃置为僵尸、计入 `zombie_threads()` 指标，不占共享池槽位；`HardTimeoutError` 继承 `FuturesTimeout` 兼容既有 except）。
- **裸线程清零**：SSE 搜索改提交执行内核（search lane）；播放自动转码改为创建 `type=convert` 任务（按 pending/running 任务去重），删 `_converting_song_ids`。
- **6 处自建池全部替换**：`musicdl_service`（搜索重试、多源并行、刮削 lookup）、`smart_cn_provider`（QQ、并行搜索）、`musicdl_provider`。
- **顺带真修复**：三处 `with ThreadPoolExecutor` 的"假超时"（超时后 shutdown(wait=True) 仍等僵尸）改为真实硬超时。
- 回归测试：`tests/test_execution.py`（6 项）、`tests/test_search_concurrency.py`（5 项）。

### P3 实施记录（0.15.0-rc20）

- **调度**：1s 轮询 DB → `asyncio.Queue` 即时调度；`enqueue()` 真实入队（`call_soon_threadsafe`，任意线程可调，去重集合防重）；4 个 worker 协程 × lane 信号量（download=1 / convert=1 / scrape=2 / scan=1），线程池 `sonpick-task` max_workers=4。
- **恢复**：启动 `_recover_pending()` 入队遗留 pending；reconcile 每 30s 兜底；原子 claim 兜底防重。
- **emit 管线**：事件入队（O(1)）→ flusher 每 0.5s 按任务合并一次落库 + 广播；终态前强制冲刷；loop 未运行回退 `_emit_sync` 直写（测试/脚本兼容）。
- **修复 `get_engine()` 覆盖绑定 bug**：`SessionLocal.configure` 改为仅在未绑定时执行（此前会把测试绑定的临时库覆盖回默认库并误写真实数据；已在测试中捕获，dev 库污染行已清理）。
- 回归测试：`tests/test_task_lifecycle.py`（7 项，含 process_loop 端到端）。

### P4 实施记录（0.15.0-rc21）

- **`app/services/host_limiter.py`**：per-host 并发槽 + 预约制最小间隔 + 429 冷却退避；`on_blocked` 回调支持快速失败；`reset()` 供测试/运维。
- **LRCLIB**：类级全局大锁 → `get_limiter("lrclib.net", 并发2/间隔0.3s)`；429 快速失败语义、缓存、任务中心"限流等待"统计不变。
- **网易云 / 咪咕** `_http_json` 挂接 limiter（各 host 并发 2/间隔 0.3s）。
- **未挂接**：musicdl（QQ 等）三方库无法注入传输层，仍由 lane 信号量 + 硬超时约束。
- 回归测试：`tests/test_host_limiter.py`（5 项）。

### 明确不做（过度设计）

- ❌ Celery/RQ + Redis：与"单进程零外部依赖"非目标冲突，运维成本远超收益
- ❌ SQLAlchemy async 全量改写：SQLite + 单写者纪律下无收益，改动面巨大
- ❌ 多 uvicorn worker：P0 的原子 claim 使其"变得安全"，但单用户场景没有动机开启
- ❌ 进度推送 SSE→WS 统一替换：两套并存有历史原因（EventSource 简单），不值得动

## 4. 最终态对比

| 指标 | 现状（改造前） | 达成（改造后） |
|------|------|------|
| 自建线程池位置 | 8+ 处，散在叶子函数 | 2 处（`execution.py` 共享池 + 硬超时 helper；任务池 `sonpick-task` 专责任务体）✅ |
| 裸线程 | 2 处无上限（搜索 SSE、播放自动转码） | 0 ✅ |
| 任务调度延迟 | 1s 轮询 | 即时（内存队列）+ 30s reconcile 兜底 ✅ |
| 任务并发 | 伪并行（max_workers=2 实际=1） | lane 化（download=1/convert=1/scrape=2/scan=1），保守默认可真并行 ✅ |
| 每次 emit 的 DB 开销 | 2 session + 2 commit | 0（flusher 每 0.5s 批量落库）✅ |
| 外部限流 | 全局大锁（LRCLIB）/ 无（其他源） | per-host HostLimiter（LRCLIB/网易/咪咕）✅ |
| 任务重复执行风险 | 多进程下有竞态窗口 | 原子 claim 消除 ✅ |
| 刮削"超时" | 假超时（with 池退出仍等僵尸） | 真硬超时 + 僵尸指标 ✅ |
| 挂死自愈 | watchdog 30min | 保留 + 硬超时僵尸计数 ✅ |

## 5. 实施纪律

- 每个阶段独立发 rc（bugfix 性质只升 rc，不抬正式版本位），前后端版本号保持一致。
- P2 动搜索超时/取消语义前，先补 `musicdl_service` 的并发行为测试（超时、取消、单源失败不影响其他源）。
- P3 动任务系统前，先补任务生命周期测试（入队→claim→终态、取消、watchdog 判死、重启恢复）。
- 每阶段完成后更新本文档状态列与 `AGENTS.md` 相关章节。
