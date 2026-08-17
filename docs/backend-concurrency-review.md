# 后端并发架构评审（Sonpick / 拾音）

> 评审范围：FastAPI 后端的线程 / 协程 / 线程池使用。
> 结论先行：**"线程池满天飞"的判断成立**。问题不在"用了线程"，而在于
> （1）并发策略没有集中管理、（2）线程池在叶子层被层层嵌套创建、
> （3）一个号称支持并行的 worker 实际是全局串行的、（4）请求路径上还散落着不受托管的裸线程。
> 阻塞式 I/O（musicdl 网络请求、ffmpeg 转码）用线程跑在 asyncio 里——这本身是正确的，
> 错的是"无策略、无上限、无复用"。

---

## 🔴 严重（Critical）：正确性与容量

### C1. `TaskWorker` 是伪并行：全局串行，`max_workers=2` 形同虚设
- **证据**：`app/services/task_worker.py:104-148`
  `process_loop` 每次从 DB 取**一个** pending 任务，提交到 executor 后立刻 `await future`，
  该任务跑完才取下一个。尽管 `ThreadPoolExecutor(max_workers=2)`，但协程同时只持有一个 future，
  所以**任意时刻只有 1 个任务在跑**，第 2 个工作线程几乎永远闲置。
- **后果**：一个长任务（大曲库扫描、批量刮削、挂起的网络下载）会**阻塞队列里所有其他任务**——
  下载、转码、WebDAV 上传全部排队。所谓"线程池"提供了并行假象，实际吞吐 = 1。
- **附带放大效应**：watchdog 的"卡死"判定阈值 30 分钟（`task_worker.py:660`）。
  若一个下载阻塞在网络调用上（无超时），整个队列会被它独占 30 分钟。
- **建议**：要么明确定义"单 worker 串行"并写进文档/测试，要么真正并发——
  用 `asyncio.wait` + 并发上限批量提交，而非逐个 `await`。

### C2. 跨线程→协程的桥接完全依赖一个全局事件循环单点
- **证据**：`app/main.py:46-49` 启动时 `worker.set_loop(loop)` 捕获 loop；
  所有进度/WS 广播经 `asyncio.run_coroutine_threadsafe(..., self.loop)` 推回
  （`task_worker.py:84, 193, 607, 704`）。
- **后果**：`self.loop` 是单点且无失效兜底——所有异常都被 `except: pass` 吞掉
  （`task_worker.py:85, 193`）。一旦 loop 引用失效（热重载、异常关闭序列），
  **每个 `emit` 静默失败**，进度与 WS 推送悄悄全部丢失，且无任何日志。

---

## 🟠 高（High）：资源失控 / 架构混乱

### H1. 请求路径上的"裸线程"（thread-per-request），无上限、无托管
- **证据**：
  - `app/routers/search.py:162` `threading.Thread(target=run_search, daemon=True).start()`
    —— 每个 `/search/stream` 请求起一个裸守护线程。
  - `app/routers/library.py:44` `threading.Thread(target=_convert_mp3_in_background, ...).start()`
    —— 每次播放自动转码起一个裸守护线程。
- **后果**：没有任何 executor / 队列 / 上限。并发搜索 + 自动转码叠加 → 线程数无界增长。
  这些线程脱离任何监督：无指标、无与关闭流程的取消协同（仅 `daemon=True` 靠进程退出兜底）。
- **架构不一致**：`convert` 既作为 task_worker 的 `type=convert` 任务存在，又被 library.py 用裸线程另搞一套——
  **同一能力两套并行机制**，状态/进度/取消语义都不统一。

### H2. 线程池嵌套 / 满天飞（朋友指出的核心症状）
一次搜索的线程层级：
- 层 A：`task_worker` 线程 **或** `search.py` 裸线程
- 层 B：`musicdl_service._search_sources` → `ThreadPoolExecutor(max(min(len(sources),4)))`
  （`musicdl_service.py:255`）
- 层 C：每个源内部 `_search_one_source` 又建 `ThreadPoolExecutor(max_workers=1)`，
  **每次搜索/每次重试都新建并在 finally 里 shutdown**（`musicdl_service.py:196, 215`）
- 刮削侧：`smart_cn_provider.py:104` `ThreadPoolExecutor(max(1,len(tasks)))`、
  `musicdl_provider.py:51` `ThreadPoolExecutor(max_workers=1)`
  —— 刮削任务扫 N 首歌就新建销毁 N 个短命线程池。
- **后果**：
  - 一个"搜索"可瞬时铺开 1 + ≤4 + ≤4 个线程，跨越 3 层嵌套池；
  - 池在热路径上被反复创建/销毁 → 线程抖动、GC 压力；若提前 return 跳过 `__exit__` 还有泄漏风险
    （目前靠上下文管理器兜住，但本质脆弱）。
  - 并发原语被撒在叶子函数里，而非集中策略——这是典型的 AI 拼装痕迹。

### H3. 多进程部署下 scheduler 重复运行（重复执行风险）
- **证据**：`worker = TaskWorker()` 在模块导入时即创建（`task_worker.py:734`），
  `lifespan` 里每个进程各起一个 `process_loop` + `watchdog`（`main.py:48-49`）。
- **后果**：若用多 uvicorn worker（或 gunicorn 多进程），**每个进程各跑一个调度器**，
  同时轮询同一张 `tasks` 表抢 pending 任务，`process_loop` 的"查 pending→置 running"存在竞态窗口
  （`task_worker.py:112-116` 与 `_run_sync` 的 commit 之间），可能**同一任务被执行两次**。
  当前单容器部署侥幸不出问题，但这是隐藏的可移植性炸弹。

---

## 🟡 中（Medium）：正确性与可维护性

### M1. SQLite 多线程写与"靠运气串行"耦合
- **证据**：`database.py:27-34` 用 `NullPool` + `check_same_thread=False` + WAL + `busy_timeout=30000`，
  防护做得不错；但代码**隐性依赖** C1 的全局串行来避免写争用。
- **后果**：一旦 C1 被修复为真并行，SQLite 单写者锁立刻成为瓶颈/争用风暴；
  而 `emit()` 在每次进度 tick 都开 2 个 session 并同步 commit（`task_worker.py:150-206`）。
  这是一颗"可扩展性悬崖"——现在不出事只是因为被串行盖住了。

### M2. `emit()` 在热路径上做重活且线程不安全假设脆弱
- **证据**：`task_worker.py:150-206`。每次调用：开 `db` → 读/写/commit → 再开 `db2` 取快照 →
  `run_coroutine_threadsafe` 推 loop。被 worker 线程和 search 裸线程共同调用。
- **后果**：进度持久化 + 广播耦合在一个阻塞调用里，且由任意线程触发；规模稍大即成为瓶颈与故障点。

### M3. SSE 取消不彻底 + 线程泄漏
- **证据**：`search.py:142-159, 188-189`。客户端断开只 `cancelled.set()`，
  但取消仅在**重试边界**被检查，进行中的 HTTP 请求无法强杀。
- **后果**：用户反复搜索后关掉标签页，会留下一堆孤儿搜索线程把整轮网络请求跑完——
  浪费 CPU/带宽，突发下线程堆积。

### M4. 全局 `threading.Lock` 串行化外部 API（LRCLIB）
- **证据**：`lrclib_provider.py:26, 52` `_lock` 在 `time.sleep(delay)` + 最长 18s 的
  `urlopen` 期间一直持有。
- **后果**：全进程所有 lrclib 调用被一把锁串行。作为限流机制正确，但实现成全局互斥——
  若歌词任务将来并行化（因 C1 现在不能），它直接变成吞吐天花板。

---

## 🟢 低（Low）：代码卫生 / 可演进性

- **L1. 轮询式调度**：`process_loop` 每秒 `SELECT ... status='pending'`，watchdog 每 60s 轮询。
  事件驱动（通知/队列）更低延迟更省资源，但当前规模可接受。
- **L2. `asyncio.get_event_loop()`**：`task_worker.py:132` 在运行中的协程里应使用
  `get_running_loop()`，`get_event_loop()` 在 3.12+ 某些场景会告警。
- **L3. CORS `allow_origins=["*"]` + `allow_credentials=True`**（`main.py:58-64`）：
  非并发问题，但作为架构师必须指出——这是无效/不安全的 CORS 配置，且 `SECRET_KEY` 默认值是安全隐患
  （项目已有告警，需确保生产必改）。
- **L4. 单例 executor 生命周期与 loop 脱节**：executor 在 import（主线程、无 loop）即建，
  与运行期 loop 的绑定靠 `set_loop`，测试/重载场景下语义模糊。

---

## 整改建议（含权衡）

**核心原则：保留线程用于阻塞 I/O（这是对的），但把并发策略集中化、复用化、上限化。**
不要因为"满天飞"就删掉所有线程——那会把 ffmpeg / musicdl 的阻塞调用拖进事件循环，直接卡死整个 API。

- **A. 最小改动、收益最大（推荐先做）**
  1. 修 C1：把逐个 `await future` 改为"按并发上限批量提交 + `asyncio.wait`"，
     真正利用 `max_workers`。或明确接受串行并写文档/测试。
  2. 消嵌套（H2）：删掉 `max_workers=1` 的"为单个阻塞调用套一层池"写法
     （`musicdl_service.py:196`、`musicdl_provider.py:51`、`smart_cn_provider.py:104`），
     改用**一个模块级共享 executor**，靠 `future.result(timeout=...)` 实现超时。
  3. 收编裸线程（H1）：把 search / 自动转码也接入同一套 worker/共享 executor，
     不要再手写 `threading.Thread`。

- **B. 更干净（中等工作量）**
  用单一 `asyncio.Queue` + N 个 worker 协程，协程内 `await loop.run_in_executor(shared_executor, ...)`。
  对 NAS 单用户场景已绰绰有余，且天然支持背压与统一取消。

- **C. 过度设计（不推荐）**
  Celery / RQ + Redis：引入额外基础设施，与项目"个人 NAS、单进程、零外部依赖"的非目标冲突。

- **D. 顺手修的并发正确性**
  - H3：把"查 pending→置 running"改成**原子 claim**（`UPDATE tasks SET status='running'
    WHERE id=? AND status='pending'`，按 rowcount 判定归属），多 worker 下也不会重复执行。
  - M3：SSE 取消用可中断的 HTTP（带 `timeout` 的短连接 + 周期性检查 `cancelled`），
    或对 musicdl 客户端注入可取消的传输层。
  - L3：CORS 改为明确的前端源白名单，去掉 `allow_credentials=True` 与 `*` 的组合。

> 优先级排序：**C1 → H1/H2 → H3 → M 系列 → L 系列**。
> C1 与 H2 解决后，"线程池满天飞"的体感会消失大半，且吞吐从 1 提升到真正的并发上限。
