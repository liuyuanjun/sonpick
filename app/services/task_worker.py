import asyncio
import json
import queue
import threading
import time
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_engine
from app.models import AppSettings, Song, SongFile, Task, iso_utc
from app.services.musicdl_service import MusicDLService
from app.services.operation_log_service import write_log
from app.services.song_file_resolver import SongFileResolver
from app.services.webdav_service import WebDAVService


class WSManager:
    def __init__(self):
        self.connections: set = set()

    async def connect(self, websocket):
        await websocket.accept()
        self.connections.add(websocket)

    def disconnect(self, websocket):
        self.connections.discard(websocket)

    async def broadcast(self, data: dict):
        dead = []
        for ws in list(self.connections):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.connections.discard(ws)


ws_manager = WSManager()


class TaskEventHub:
    """In-process fan-out for task SSE subscribers."""

    def __init__(self):
        self._subs: dict[int, list[asyncio.Queue]] = {}

    def subscribe(self, task_id: int) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._subs.setdefault(int(task_id), []).append(q)
        return q

    def unsubscribe(self, task_id: int, q: asyncio.Queue) -> None:
        tid = int(task_id)
        lst = self._subs.get(tid) or []
        if q in lst:
            lst.remove(q)
        if not lst and tid in self._subs:
            self._subs.pop(tid, None)

    async def publish(self, task_id: int, payload: dict) -> None:
        tid = int(task_id)
        for q in list(self._subs.get(tid) or []):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    _ = q.get_nowait()
                except Exception:
                    pass
                try:
                    q.put_nowait(payload)
                except Exception:
                    pass

    def publish_threadsafe(self, task_id: int, payload: dict, loop: Optional[asyncio.AbstractEventLoop]) -> None:
        if not loop:
            return
        coro = self.publish(task_id, payload)
        try:
            asyncio.run_coroutine_threadsafe(coro, loop)
        except Exception as e:
            try:
                coro.close()
            except Exception:
                pass
            print(f"[task_event_hub push error] {type(e).__name__}: {e}", flush=True)


task_event_hub = TaskEventHub()


# ---------------------------------------------------------------- 调度配置
# worker 协程数：上限意义大于并行意义，实际任务并发由 lane 信号量控制
_WORKER_COROUTINES = 4
# lane：按任务类型限流。下载/转码/扫描串行（对源、CPU、SQLite 友好），刮削可并行 2
_TASK_LANES: dict[str, str] = {
    "search_download": "download",
    "batch_download": "download",
    "convert": "convert",
    "scrape": "scrape",
    "lyrics": "scrape",
    "scan": "scan",
    "cleanup": "scan",
}
_LANE_LIMITS: dict[str, int] = {"download": 1, "convert": 1, "scrape": 2, "scan": 1, "default": 2}
# reconcile 兜底周期：捞回"队列未就绪期间入 DB"或漏 enqueue 的 pending 任务
_RECONCILE_INTERVAL_SECONDS = 30
# emit 事件批量落库/广播周期
_FLUSH_INTERVAL_SECONDS = 0.5


class TaskWorker:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="sonpick-task")
        self._running = False
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._running_futures: dict[int, Future] = {}
        self._future_lock = threading.Lock()
        self._watchdog_task: Optional[asyncio.Task] = None
        self._loop_push_failures = 0
        # 内存调度队列（process_loop 内在事件循环上创建）
        self._queue: Optional[asyncio.Queue] = None
        self._lane_sems: dict[str, asyncio.Semaphore] = {}
        self._queued_ids: set[int] = set()
        self._ids_lock = threading.Lock()
        # emit 进度事件队列（线程安全），flusher 协程批量消费
        self._event_queue: "queue.Queue[tuple[int, str, Optional[int]]]" = queue.Queue()

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

    def _push_to_loop(self, coro) -> bool:
        """把协程推回主事件循环。

        loop 失效（热重载、异常关闭）时不再让异常传播误杀任务，也不静默丢失：
        节流记日志（前 5 次 + 每 100 次）并 close 协程，避免 "never awaited" 警告。
        """
        loop = self.loop
        if loop is None:
            coro.close()
            return False
        try:
            asyncio.run_coroutine_threadsafe(coro, loop)
            return True
        except Exception as e:
            try:
                coro.close()
            except Exception:
                pass
            self._loop_push_failures += 1
            n = self._loop_push_failures
            if n <= 5 or n % 100 == 0:
                print(f"[loop push error] {type(e).__name__}: {e}（累计 {n} 次）", flush=True)
            return False

    async def process_loop(self):
        """调度主循环：内存队列 + N 个 worker 协程 + flusher + reconcile 兜底。

        DB 只做持久化（claim/终态/恢复），不再每秒轮询；enqueue 即时调度，
        reconcile 每 30s 捞回漏网 pending（原子 claim 保证不会重复执行）。
        """
        self._running = True
        get_engine()
        self._queue = asyncio.Queue()
        self._lane_sems = {name: asyncio.Semaphore(limit) for name, limit in _LANE_LIMITS.items()}
        children = [
            asyncio.create_task(self._worker_loop(i)) for i in range(_WORKER_COROUTINES)
        ] + [
            asyncio.create_task(self._flush_loop()),
            asyncio.create_task(self._reconcile_loop()),
        ]
        self._recover_pending()
        try:
            await asyncio.gather(*children)
        except asyncio.CancelledError:
            for child in children:
                child.cancel()
            raise

    async def _worker_loop(self, idx: int):
        assert self._queue is not None
        while self._running:
            task_id = await self._queue.get()
            try:
                lane = self._lane_for(task_id)
                sem = self._lane_sems.get(lane) or self._lane_sems["default"]
                async with sem:
                    if not self._running:
                        continue
                    future = asyncio.get_running_loop().run_in_executor(
                        self.executor, self._run_sync, task_id
                    )
                    with self._future_lock:
                        self._running_futures[task_id] = future
                    future.add_done_callback(
                        lambda f, tid=task_id: self._remove_future(tid)
                    )
                    await future
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"[worker_loop {idx} error] {e}", flush=True)
                traceback.print_exc()
            finally:
                with self._ids_lock:
                    self._queued_ids.discard(task_id)

    def _lane_for(self, task_id: int) -> str:
        db = SessionLocal()
        try:
            row = db.query(Task.type).filter(Task.id == task_id).first()
            return _TASK_LANES.get(row[0], "default") if row else "default"
        except Exception:
            return "default"
        finally:
            db.close()

    def _pending_ids(self) -> list[int]:
        db = SessionLocal()
        try:
            return [
                r[0]
                for r in db.query(Task.id)
                .filter(Task.status == "pending")
                .order_by(Task.id.asc())
                .all()
            ]
        except Exception as e:
            print(f"[pending scan error] {e}", flush=True)
            return []
        finally:
            db.close()

    def _recover_pending(self):
        ids = self._pending_ids()
        for tid in ids:
            self.enqueue(tid)
        if ids:
            print(f"[task_worker] 启动恢复 {len(ids)} 个遗留 pending 任务", flush=True)

    async def _reconcile_loop(self):
        """兜底：捞回队列未就绪期间入 DB / 漏 enqueue 的 pending 任务。"""
        while self._running:
            await asyncio.sleep(_RECONCILE_INTERVAL_SECONDS)
            try:
                for tid in self._pending_ids():
                    self.enqueue(tid)
            except Exception as e:
                print(f"[reconcile error] {e}", flush=True)
                traceback.print_exc()

    # ------------------------------------------------------------ emit 管线

    async def _flush_loop(self):
        while self._running:
            await asyncio.sleep(_FLUSH_INTERVAL_SECONDS)
            try:
                self._flush_events()
            except Exception as e:
                print(f"[flusher error] {e}", flush=True)
                traceback.print_exc()

    def _flush_events(self):
        """把累积的进度事件按任务合并后一次落库 + 广播（线程安全，可被 worker 线程同步调用）。"""
        events = []
        while True:
            try:
                events.append(self._event_queue.get_nowait())
            except queue.Empty:
                break
        if not events:
            return
        # 按任务合并：日志按序拼接，percent/message 取最后一条
        merged: dict[int, dict] = {}
        order: list[int] = []
        for task_id, message, percent in events:
            slot = merged.get(task_id)
            if slot is None:
                slot = merged[task_id] = {"logs": [], "percent": None, "message": None}
                order.append(task_id)
            slot["logs"].append(message)
            if percent is not None:
                slot["percent"] = percent
            slot["message"] = message

        snapshots: dict[int, dict] = {}
        db = SessionLocal()
        try:
            for task_id in order:
                task = db.get(Task, task_id)
                if not task:
                    continue
                progress = json.loads(task.progress_json or "{}")
                logs = progress.get("logs", [])
                now_iso = datetime.now(timezone.utc).isoformat()
                logs.extend({"t": now_iso, "m": m} for m in merged[task_id]["logs"])
                progress["logs"] = logs[-100:]
                if merged[task_id]["percent"] is not None:
                    progress["percent"] = merged[task_id]["percent"]
                progress["message"] = merged[task_id]["message"]
                task.progress_json = json.dumps(progress, ensure_ascii=False)
                task.updated_at = datetime.now(timezone.utc)
            db.commit()
            for task_id in order:
                task = db.get(Task, task_id)
                if task:
                    snapshots[task_id] = task.to_dict()
        except Exception as e:
            print(f"[flusher db error] {e}", flush=True)
            try:
                db.rollback()
            except Exception:
                pass
        finally:
            try:
                db.close()
            except Exception:
                pass

        for task_id in order:
            last = merged[task_id]
            snapshot = snapshots.get(task_id)
            self._push_to_loop(
                ws_manager.broadcast({
                    "type": "task_progress",
                    "task_id": task_id,
                    "message": last["message"],
                    "percent": last["percent"],
                    "status": (snapshot or {}).get("status"),
                    "progress": (snapshot or {}).get("progress") or {"message": last["message"], "percent": last["percent"]},
                })
            )
            if snapshot:
                task_event_hub.publish_threadsafe(task_id, snapshot, self.loop)

    def emit(self, task_id: int, message: str, percent: Optional[int] = None):
        """进度事件入队（非阻塞 O(1)），flusher 协程批量落库 + 广播。

        percent 为 None 时保留原百分比（仅更新消息/日志）。
        loop 未运行（单测/脚本场景）时回退为同步直写。
        """
        if self.loop is None or not self._running:
            self._emit_sync(task_id, message, percent)
            return
        self._event_queue.put((task_id, message, percent))

    def _emit_sync(self, task_id: int, message: str, percent: Optional[int] = None):
        """emit 的同步直写实现（每次 2 个 session），仅作回退路径使用。"""
        db = SessionLocal()
        try:
            task = db.get(Task, task_id)
            if task:
                progress = json.loads(task.progress_json or "{}")
                logs = progress.get("logs", [])
                logs.append({"t": datetime.now(timezone.utc).isoformat(), "m": message})
                progress["logs"] = logs[-100:]
                if percent is not None:
                    progress["percent"] = percent
                progress["message"] = message
                task.progress_json = json.dumps(progress, ensure_ascii=False)
                task.updated_at = datetime.now(timezone.utc)
                db.commit()
        except Exception as e:
            print(f"[emit error] {e}", flush=True)
            try:
                db.rollback()
            except Exception:
                pass
        finally:
            try:
                db.close()
            except Exception:
                pass

        snapshot = None
        db2 = SessionLocal()
        try:
            task2 = db2.get(Task, task_id)
            if task2:
                snapshot = task2.to_dict()
        except Exception:
            snapshot = None
        finally:
            try:
                db2.close()
            except Exception:
                pass

        if self._push_to_loop(
            ws_manager.broadcast({
                "type": "task_progress",
                "task_id": task_id,
                "message": message,
                "percent": percent,
                "status": (snapshot or {}).get("status"),
                "progress": (snapshot or {}).get("progress") or {"message": message, "percent": percent},
            })
        ) and snapshot:
            task_event_hub.publish_threadsafe(task_id, snapshot, self.loop)

    def _run_sync(self, task_id: int):
        get_engine()
        db = SessionLocal()
        status = "failed"
        try:
            # 原子 claim：仅当任务仍处 pending 才认领，按 rowcount 判归属。
            # 多进程/多 worker 部署下同一任务不会被重复执行；已取消任务天然认领失败。
            started_at = datetime.now(timezone.utc)
            claimed = db.execute(
                update(Task)
                .where(Task.id == task_id, Task.status == "pending")
                .values(
                    status="running",
                    worker_thread_id=threading.current_thread().ident,
                    started_at=started_at,
                    updated_at=started_at,
                )
                .execution_options(synchronize_session=False)
            ).rowcount
            db.commit()
            if not claimed:
                return
            task = db.get(Task, task_id)
            if not task:
                return

            payload = json.loads(task.payload_json or "{}")
            settings = db.get(AppSettings, 1)

            if task.type == "scan":
                from app.services.library_scan_service import LibraryScanService

                scan_source = payload.get("source", "all")
                scan_source_ids = payload.get("source_ids")

                # 节流：percent 变化或距上次 >=2s 才落库/广播，避免大曲库扫描打爆 SQLite
                _emit_state = {"last": 0.0, "pct": None}

                def _scan_emit(msg: str, pct: Optional[int] = None, _tid=task_id):
                    now = time.monotonic()
                    changed = pct is not None and pct != _emit_state["pct"]
                    if changed or now - _emit_state["last"] >= 2.0:
                        _emit_state["last"] = now
                        if pct is not None:
                            _emit_state["pct"] = pct
                        self.emit(_tid, msg, pct)

                self.emit(task_id, "正在扫描曲库...", 5)
                scan_svc = LibraryScanService(db)
                result = scan_svc.scan(source=scan_source, source_ids=scan_source_ids, emit=_scan_emit)
                heal = result.get("heal_stats", {}) or {}
                msg = (
                    f"扫描完成: 新增 {result.get('total_added', 0)}, "
                    f"更新 {result.get('total_updated', 0)}"
                )
                if heal.get("healed"):
                    msg += f", 路径恢复 {heal['healed']}"
                if heal.get("marked_unavailable"):
                    msg += f", 失效标记 {heal['marked_unavailable']}"
                if heal.get("deduped_songs"):
                    msg += f", 清理重复失效 {heal['deduped_songs']}"
                if heal.get("refreshed_songs"):
                    msg += f", 展示路径回填 {heal['refreshed_songs']}"
                if heal.get("cleaned_stale_versions"):
                    msg += f", 清理冗余版本 {heal['cleaned_stale_versions']}"
                result["ok"] = True
                result["message"] = msg
                task.result_json = json.dumps(result, ensure_ascii=False)
                task.status = "completed"
                status = "completed"
                task.updated_at = datetime.now(timezone.utc)
                db.commit()
                self.emit(task_id, msg, 100)
                return

            if task.type == "cleanup":
                from app.services.library_cleanup_service import LibraryCleanupService

                def _cleanup_emit(msg: str, pct: Optional[int] = None, _tid=task_id):
                    self.emit(_tid, msg, pct)

                self.emit(task_id, "正在清理失效记录...", 5)
                result = LibraryCleanupService(db).run(emit=_cleanup_emit)
                msg = (
                    f"清理完成: 恢复 {result.get('healed', 0)}, "
                    f"清理 {result.get('deleted', 0)}, "
                    f"跳过 {result.get('blocked', 0)}"
                )
                result["ok"] = True
                result["message"] = msg
                task.result_json = json.dumps(result, ensure_ascii=False)
                task.status = "completed"
                task.updated_at = datetime.now(timezone.utc)
                db.commit()
                self.emit(task_id, msg, 100)
                return

            if task.type == "scrape":
                from app.services.scrape.job import run_scrape_job

                def _emit(msg: str, pct: int = 0, _tid=task_id):
                    self.emit(_tid, msg, pct)

                result = run_scrape_job(
                    db,
                    source_id=payload.get("source_id"),
                    song_ids=payload.get("song_ids"),
                    allow_network=bool(payload.get("allow_network", True)),
                    overwrite=bool(payload.get("overwrite", False)),
                    write_file_tags=bool(payload.get("write_file_tags", True)),
                    limit=int(payload.get("limit") or 20),
                    emit=_emit,
                )
                task.result_json = json.dumps(result, ensure_ascii=False)
                task.status = "completed"
                status = "completed"
                task.updated_at = datetime.now(timezone.utc)
                db.commit()
                self.emit(task_id, "刮削完成", 100)
                return

            if task.type == "lyrics":
                from app.services.lyrics_job import run_lyrics_job

                result = run_lyrics_job(
                    db,
                    song_ids=payload.get("song_ids"),
                    source_id=payload.get("source_id") or "auto",
                    only_missing=bool(payload.get("only_missing", True)),
                    overwrite=bool(payload.get("overwrite", False)),
                    write_file_tags=bool(payload.get("write_file_tags", True)),
                    library_source_id=payload.get("library_source_id"),
                    emit=lambda message, percent=0: self.emit(task_id, message, percent),
                    is_cancelled=lambda: self._is_cancelled(task_id, db),
                )
                if result.get("cancelled"):
                    task.status = "cancelled"
                    status = "cancelled"
                else:
                    task.status = "completed"
                    status = "completed"
                task.result_json = json.dumps(result, ensure_ascii=False)
                task.updated_at = datetime.now(timezone.utc)
                db.commit()
                self.emit(task_id, result.get("message") or "歌词任务完成", 100)
                return

            if task.type == "convert":
                from app.services.convert_service import ConvertService

                song_id = int(payload.get("song_id") or 0)
                song = db.get(Song, song_id)
                if not song:
                    raise RuntimeError(f"歌曲不存在: {song_id}")
                title = f"{song.artist or ''} - {song.title}".strip(" -")
                self.emit(task_id, f"转码 MP3: {title}", 10)
                try:
                    mp3_file = ConvertService(db).convert_song_to_mp3(song)
                    song.updated_at = datetime.now(timezone.utc)
                    db.commit()
                    write_log(
                        db,
                        action="convert",
                        target="local",
                        status="success",
                        title=title,
                        message="转码为 MP3",
                        local_path=str(mp3_file.local_path),
                        song_id=song.id,
                        task_id=task_id,
                    )
                    task.result_json = json.dumps({"ok": True, "local_path": str(mp3_file.local_path), "format": mp3_file.format}, ensure_ascii=False)
                    task.status = "completed"
                    status = "completed"
                    task.updated_at = datetime.now(timezone.utc)
                    db.commit()
                    self.emit(task_id, f"转码完成: {title}", 100)
                except Exception as exc:
                    write_log(
                        db,
                        action="convert",
                        target="local",
                        status="failed",
                        title=title,
                        message=str(exc),
                        song_id=song_id,
                        task_id=task_id,
                    )
                    raise
                return

            music = MusicDLService(db, emit=self.emit)

            if task.type in ("search_download", "batch_download"):
                keywords = payload.get("keywords") or [payload.get("keyword")]
                keywords = [k for k in keywords if k]
                prefer = payload.get("prefer", "any")
                selected_source = str(payload.get("source") or "all").strip()
                music_sources = None if selected_source == "all" else [selected_source]
                total = max(len(keywords), 1)
                storage = Path(settings.storage_path if settings else "./downloads")
                storage.mkdir(parents=True, exist_ok=True)

                for idx, kw in enumerate(keywords):
                    if self._is_cancelled(task_id, db):
                        status = "cancelled"
                        task.status = "cancelled"
                        self.emit(task_id, "已取消", int(idx / total * 100))
                        return

                    pct = int(idx / total * 100)
                    self.emit(task_id, f"搜索: {kw}", pct)
                    try:
                        results = music.search(kw, prefer=prefer, music_sources=music_sources)
                    except Exception as e:
                        self.emit(task_id, f"搜索失败: {e}", pct)
                        write_log(
                            db,
                            action="download",
                            target="local",
                            status="failed",
                            title=kw,
                            message=f"搜索失败: {e}",
                            task_id=task_id,
                            detail={"keyword": kw},
                        )
                        continue

                    if not results:
                        self.emit(task_id, f"未找到: {kw}", pct)
                        write_log(
                            db,
                            action="download",
                            target="local",
                            status="failed",
                            title=kw,
                            message="搜索无结果",
                            task_id=task_id,
                            detail={"keyword": kw},
                        )
                        continue

                    item = results[0]
                    song_name = getattr(item, "song_name", None) or kw
                    singers = getattr(item, "singers", None) or ""
                    self.emit(task_id, f"下载: {song_name} - {singers}", pct)
                    try:
                        song = music.download_one(
                            task_id=task_id,
                            keyword=kw,
                            song_name=song_name,
                            singers=singers,
                            prefer=prefer,
                            output_dir=storage,
                            music_sources=music_sources,
                            picked=item,
                        )
                        if song is None:
                            raise RuntimeError("未找到可下载版本，或下载文件落盘失败")
                        # 曲库重复决策：保留两者并入同一逻辑 Song；替换走安全流程
                        dup_action = payload.get("duplicate_action")
                        log_message = f"下载完成 ({song.format or ''})"
                        replaced_path = None
                        if dup_action == "replace" and payload.get("replace_song_file_id"):
                            from app.services.download_duplicate_service import apply_replace

                            song = apply_replace(
                                db,
                                song,
                                int(payload["replace_song_file_id"]),
                                payload.get("matched_song_id"),
                                task_id=task_id,
                            )
                            replaced = db.get(SongFile, int(payload["replace_song_file_id"]))
                            replaced_path = replaced.local_path if replaced else None
                            log_message = f"下载完成并替换已有本地版本 ({song.format or ''})"
                        elif dup_action == "keep_both" and payload.get("matched_song_id"):
                            from app.services.download_duplicate_service import apply_keep_both

                            song = apply_keep_both(db, song, payload.get("matched_song_id"))
                            log_message = f"下载完成（保留两个版本）({song.format or ''})"
                        downloaded_file = SongFileResolver(db).resolve_local(song)
                        write_log(
                            db,
                            action="download",
                            target="local",
                            status="success",
                            title=f"{song.artist or ''} - {song.title}".strip(" -"),
                            message=log_message,
                            local_path=replaced_path or downloaded_file.local_path,
                            song_id=song.id,
                            task_id=task_id,
                            detail={
                                "cover_path": song.cover_path,
                                "lrc_path": song.lrc_path,
                                "format": song.format,
                                "duplicate_action": dup_action,
                                "replace_song_file_id": payload.get("replace_song_file_id"),
                            },
                        )
                    except Exception as e:
                        self.emit(task_id, f"下载失败: {e}", pct)
                        write_log(
                            db,
                            action="download",
                            target="local",
                            status="failed",
                            title=kw,
                            message=str(e),
                            task_id=task_id,
                            detail={"keyword": kw},
                        )
                        continue

                    if settings and not settings.lossless_preferred and settings.auto_convert_when_lossless_not_preferred:
                        try:
                            from app.services.convert_service import ConvertService
                            self.emit(task_id, "转码 MP3...", pct)
                            mp3_file = ConvertService(db).convert_song_to_mp3(song)
                            write_log(
                                db,
                                action="convert",
                                target="local",
                                status="success",
                                title=f"{song.artist or ''} - {song.title}".strip(" -"),
                                message="自动转码 MP3",
                                local_path=str(mp3_file.local_path),
                                song_id=song.id,
                                task_id=task_id,
                            )
                        except Exception as e:
                            self.emit(task_id, f"转码失败: {e}", pct)
                            write_log(
                                db,
                                action="convert",
                                target="local",
                                status="failed",
                                title=f"{song.artist or ''} - {song.title}".strip(" -"),
                                message=str(e),
                                song_id=song.id,
                                task_id=task_id,
                            )

                    if settings and settings.auto_upload_webdav:
                        try:
                            self.emit(task_id, "上传 WebDAV...", pct)

                            def _cb(msg: str, _pct=pct):
                                self.emit(task_id, msg, _pct)

                            ws = WebDAVService(db)
                            result = ws.upload_song(song, task_id=task_id, progress_cb=_cb)
                            self.emit(
                                task_id,
                                f"上传完成: {result.get('webdav_path')} ({result.get('status')})",
                                pct,
                            )
                        except Exception as e:
                            self.emit(task_id, f"上传失败: {e}", pct)
                            write_log(
                                db,
                                action="upload",
                                target="webdav",
                                status="failed",
                                title=f"{song.artist or ''} - {song.title}".strip(" -"),
                                message=str(e),
                                local_path=SongFileResolver(db).resolve_local(song).local_path,
                                song_id=song.id,
                                task_id=task_id,
                            )

            task.status = "completed"
            task.result_json = json.dumps({"ok": True})
            status = "completed"
            task.updated_at = datetime.now(timezone.utc)
            db.commit()
            self.emit(task_id, "完成", 100)
        except Exception as e:
            print(f"[_run_sync error] {e}", flush=True)
            traceback.print_exc()
            # worker 的 Session 可能已处于 PendingRollbackError（DB 层崩溃），
            # 必须用全新 Session 写终态，否则任务状态会永远卡在 running
            self._mark_failed(task_id, e)
            status = "failed"
        finally:
            # 终态快照前先冲刷进度事件队列，保证 SSE/WS 终态含最新进度
            try:
                self._flush_events()
            except Exception as e:
                print(f"[finally flush error] {e}", flush=True)
            db2 = SessionLocal()
            try:
                task = db2.get(Task, task_id)
                if task:
                    task.updated_at = datetime.now(timezone.utc)
                    db2.commit()
                    # 终态再推一次，防止 SSE 漏事件
                    if task.status in {"completed", "failed", "cancelled"} and self.loop:
                        task_event_hub.publish_threadsafe(task_id, task.to_dict(), self.loop)
            except Exception as e:
                print(f"[finally db error] {e}", flush=True)
                try:
                    db2.rollback()
                except Exception:
                    pass
            finally:
                try:
                    db2.close()
                except Exception as e:
                    print(f"[finally close error] {e}", flush=True)
            try:
                db.close()
            except Exception:
                pass
            self._push_to_loop(
                ws_manager.broadcast({
                    "type": "task_update",
                    "task_id": task_id,
                    "status": status,
                })
            )

    def _mark_failed(self, task_id: int, exc: Exception):
        """用全新 Session 写入 failed 终态（调用方的 Session 可能已不可用）。"""
        db = SessionLocal()
        try:
            task = db.get(Task, task_id)
            if not task or task.status in {"completed", "failed", "cancelled"}:
                return
            task.status = "failed"
            task.error_message = str(exc)
            task.result_json = json.dumps(
                {"ok": False, "error": str(exc), "message": f"任务失败: {exc}"},
                ensure_ascii=False,
            )
            task.updated_at = datetime.now(timezone.utc)
            db.commit()
        except Exception as e:
            print(f"[_mark_failed error] {e}", flush=True)
            try:
                db.rollback()
            except Exception:
                pass
        finally:
            try:
                db.close()
            except Exception:
                pass
        self.emit(task_id, f"失败: {exc}", 100)

    def _is_cancelled(self, task_id: int, db: Session | None = None) -> bool:
        check_db = SessionLocal()
        try:
            status = check_db.query(Task.status).filter(Task.id == task_id).scalar()
            return status is None or status == "cancelled"
        finally:
            check_db.close()

    def _remove_future(self, task_id: int):
        with self._future_lock:
            self._running_futures.pop(task_id, None)

    async def _watchdog(self):
        """Periodically scan stale running tasks, mark orphan/lost ones as failed."""
        STALE_THRESHOLD_MINUTES = 30
        CHECK_INTERVAL_SECONDS = 60
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)  # initial delay
        while self._running:
            try:
                db = SessionLocal()
                try:
                    cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_THRESHOLD_MINUTES)
                    stale_tasks = (
                        db.query(Task)
                        .filter(
                            Task.status == "running",
                            Task.updated_at < cutoff,
                        )
                        .all()
                    )
                    for task in stale_tasks:
                        tid = task.id

                        with self._future_lock:
                            future = self._running_futures.get(tid)

                        # 判定依据只看 future，不看线程 ident：
                        # 线程池的工作线程执行完任务后仍然存活（空闲复用），
                        # "线程活着" 不代表 "任务还在跑"。
                        # future 不在字典里只有两种可能：任务已结束（done_callback
                        # 已移除）或进程重启后 orphaned——两种情况都不可能再更新状态。
                        lost = future is None or future.done()

                        if lost:
                            task.status = "failed"
                            task.error_message = (
                                "任务异常中断：worker 已结束但未写入终态"
                                f"（最后更新：{iso_utc(task.updated_at) or 'N/A'}）"
                            )
                            progress = json.loads(task.progress_json or "{}")
                            progress["percent"] = 0
                            progress["message"] = "任务异常中断（worker 丢失或进程重启）"
                            task.progress_json = json.dumps(progress, ensure_ascii=False)
                            task.updated_at = datetime.now(timezone.utc)
                            db.commit()

                            # push final state
                            self._push_to_loop(
                                ws_manager.broadcast({
                                    "type": "task_update",
                                    "task_id": tid,
                                    "status": "failed",
                                })
                            )
                            task_event_hub.publish_threadsafe(tid, task.to_dict(), self.loop)

                            print(f"[watchdog] marked task {tid} as failed (stale/lost thread)", flush=True)

                            with self._future_lock:
                                self._running_futures.pop(tid, None)
                finally:
                    db.close()
            except Exception as e:
                print(f"[watchdog error] {e}", flush=True)
                traceback.print_exc()

            await asyncio.sleep(CHECK_INTERVAL_SECONDS)

    def stop(self):
        self._running = False

    def enqueue(self, task_id: int):
        """把任务放入内存队列即时调度（可被任意线程调用）。

        队列未就绪（启动前/关闭后）时不入队：pending 已持久化在 DB，
        由 reconcile 兜底或下次启动恢复，原子 claim 保证不重复执行。
        """
        q, loop = self._queue, self.loop
        if q is None or loop is None or not loop.is_running():
            return
        with self._ids_lock:
            if task_id in self._queued_ids:
                return
            self._queued_ids.add(task_id)
        try:
            loop.call_soon_threadsafe(q.put_nowait, task_id)
        except Exception:
            with self._ids_lock:
                self._queued_ids.discard(task_id)


worker = TaskWorker()
