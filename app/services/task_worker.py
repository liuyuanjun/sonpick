import asyncio
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.database import SessionLocal, get_engine
from app.models import AppSettings, Song, Task
from app.services.musicdl_service import MusicDLService
from app.services.operation_log_service import write_log
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
        try:
            asyncio.run_coroutine_threadsafe(self.publish(task_id, payload), loop)
        except Exception:
            pass


task_event_hub = TaskEventHub()


class TaskWorker:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=2)
        self._running = False
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

    async def process_loop(self):
        self._running = True
        # ensure engine bound in worker threads context
        get_engine()
        while self._running:
            task_id = None
            db = SessionLocal()
            try:
                task = (
                    db.query(Task)
                    .filter(Task.status == "pending")
                    .order_by(Task.id.asc())
                    .first()
                )
                if task:
                    task_id = task.id
            except Exception as e:
                print(f"[process_loop error] {e}", flush=True)
                traceback.print_exc()
                task_id = None
            finally:
                try:
                    db.close()
                except Exception:
                    pass

            if task_id is not None:
                try:
                    await asyncio.get_event_loop().run_in_executor(
                        self.executor, self._run_sync, task_id
                    )
                except Exception as e:
                    print(f"[process_loop executor error] {e}", flush=True)
                    traceback.print_exc()
                    await asyncio.sleep(1)
            else:
                await asyncio.sleep(1)

    def emit(self, task_id: int, message: str, percent: int = 0):
        db = SessionLocal()
        try:
            task = db.get(Task, task_id)
            if task:
                progress = json.loads(task.progress_json or "{}")
                logs = progress.get("logs", [])
                logs.append({"t": datetime.now(timezone.utc).isoformat(), "m": message})
                progress["logs"] = logs[-100:]
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

        if self.loop:
            asyncio.run_coroutine_threadsafe(
                ws_manager.broadcast({
                    "type": "task_progress",
                    "task_id": task_id,
                    "message": message,
                    "percent": percent,
                    "status": (snapshot or {}).get("status"),
                    "progress": (snapshot or {}).get("progress") or {"message": message, "percent": percent},
                }),
                self.loop,
            )
            if snapshot:
                task_event_hub.publish_threadsafe(task_id, snapshot, self.loop)

    def _run_sync(self, task_id: int):
        get_engine()
        db = SessionLocal()
        status = "failed"
        try:
            task = db.get(Task, task_id)
            if not task or task.status == "cancelled":
                return
            task.status = "running"
            task.updated_at = datetime.now(timezone.utc)
            db.commit()

            payload = json.loads(task.payload_json or "{}")
            settings = db.get(AppSettings, 1)

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
                        write_log(
                            db,
                            action="download",
                            target="local",
                            status="success",
                            title=f"{song.artist or ''} - {song.title}".strip(" -"),
                            message=f"下载完成 ({song.format or ''})",
                            local_path=song.local_path,
                            song_id=song.id,
                            task_id=task_id,
                            detail={
                                "cover_path": song.cover_path,
                                "lrc_path": song.lrc_path,
                                "format": song.format,
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
                                local_path=song.local_path,
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
            task = db.get(Task, task_id)
            if task:
                task.status = "failed"
                task.error_message = str(e)
                task.result_json = json.dumps({"ok": False, "error": str(e)})
                task.updated_at = datetime.now(timezone.utc)
                db.commit()
                self.emit(task_id, f"失败: {e}", 100)
            status = "failed"
        finally:
            try:
                task = db.get(Task, task_id)
                if task:
                    task.updated_at = datetime.now(timezone.utc)
                    db.commit()
                    # 终态再推一次，防止 SSE 漏事件
                    if task.status in {"completed", "failed", "cancelled"} and self.loop:
                        task_event_hub.publish_threadsafe(task_id, task.to_dict(), self.loop)
            except Exception as e:
                print(f"[finally db error] {e}", flush=True)
                try:
                    db.rollback()
                except Exception:
                    pass
            finally:
                try:
                    db.close()
                except Exception as e:
                    print(f"[finally close error] {e}", flush=True)
            try:
                if self.loop:
                    asyncio.run_coroutine_threadsafe(
                        ws_manager.broadcast({
                            "type": "task_update",
                            "task_id": task_id,
                            "status": status,
                        }),
                        self.loop,
                    )
            except Exception as e:
                print(f"[finally ws error] {e}", flush=True)

    def _is_cancelled(self, task_id: int, db: Session) -> bool:
        task = db.get(Task, task_id)
        return task is None or task.status == "cancelled"

    def stop(self):
        self._running = False

    def enqueue(self, task_id: int):
        """For compatibility with routers that call worker.enqueue."""
        pass


worker = TaskWorker()
