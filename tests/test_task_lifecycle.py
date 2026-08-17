"""任务系统生命周期测试（P3 重构回归保护）。

覆盖：原子 claim（pending→running→终态）、取消任务不被执行、
emit 同步回退直写、flusher 批量合并落库、enqueue 去重与离线 no-op、
process_loop 端到端（内存队列→claim→执行→终态）。
"""
import asyncio
import json
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

import app.database as database
from app.database import Base, SessionLocal
from app.models import Task
from app.services.task_worker import TaskWorker

_engine = create_engine(
    f"sqlite:///{Path(tempfile.mkdtemp()) / 'task_test.db'}",
    connect_args={"check_same_thread": False},
    poolclass=NullPool,
)
Base.metadata.create_all(_engine)


def setUpModule():
    SessionLocal.configure(bind=_engine)


def tearDownModule():
    SessionLocal.configure(bind=None)


def _create_task(status="pending", task_type="noop_test") -> int:
    db = SessionLocal()
    try:
        task = Task(type=task_type, status=status)
        db.add(task)
        db.commit()
        db.refresh(task)
        return task.id
    finally:
        db.close()


def _get_task(task_id: int) -> Task:
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        db.expunge(task)
        return task
    finally:
        db.close()


class ClaimTests(unittest.TestCase):
    def test_run_sync_claims_and_completes(self):
        tid = _create_task()
        TaskWorker()._run_sync(tid)
        task = _get_task(tid)
        self.assertEqual(task.status, "completed")
        self.assertIsNotNone(task.started_at)
        self.assertIsNotNone(task.worker_thread_id)

    def test_cancelled_task_is_not_executed(self):
        tid = _create_task(status="cancelled")
        TaskWorker()._run_sync(tid)
        self.assertEqual(_get_task(tid).status, "cancelled")

    def test_second_runner_cannot_reclaim_running_task(self):
        tid = _create_task(status="running")
        # 已被其他 worker 认领（status=running）→ 原子 claim 失败，直接返回
        TaskWorker()._run_sync(tid)
        self.assertEqual(_get_task(tid).status, "running")


class EmitTests(unittest.TestCase):
    def test_emit_sync_fallback_writes_progress(self):
        tid = _create_task()
        worker = TaskWorker()  # loop=None → 同步回退
        worker.emit(tid, "进行中", 50)
        task = _get_task(tid)
        progress = json.loads(task.progress_json)
        self.assertEqual(progress["percent"], 50)
        self.assertEqual(progress["message"], "进行中")
        self.assertEqual(progress["logs"][-1]["m"], "进行中")

    def test_flush_events_merges_per_task(self):
        t1, t2 = _create_task(), _create_task()
        worker = TaskWorker()
        for msg, pct in [("a", 10), ("b", 20), ("c", None)]:
            worker._event_queue.put((t1, msg, pct))
        worker._event_queue.put((t2, "x", 5))
        worker._flush_events()

        p1 = json.loads(_get_task(t1).progress_json)
        self.assertEqual(p1["percent"], 20, "percent 取最后一条非 None")
        self.assertEqual(p1["message"], "c")
        self.assertEqual([l["m"] for l in p1["logs"]], ["a", "b", "c"])

        p2 = json.loads(_get_task(t2).progress_json)
        self.assertEqual(p2["percent"], 5)
        self.assertTrue(worker._event_queue.empty())


class EnqueueTests(unittest.TestCase):
    def test_enqueue_offline_is_noop(self):
        worker = TaskWorker()  # _queue/loop 均未就绪
        worker.enqueue(123)  # 不抛异常即可（由 reconcile/启动恢复兜底）
        self.assertNotIn(123, worker._queued_ids)


class EndToEndTests(unittest.TestCase):
    def test_process_loop_executes_enqueued_task(self):
        worker = TaskWorker()
        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=loop.run_forever, daemon=True)
        thread.start()
        try:
            worker.set_loop(loop)
            proc = asyncio.run_coroutine_threadsafe(worker.process_loop(), loop)
            time.sleep(0.5)  # 等队列/worker 协程就绪

            tid = _create_task()
            worker.enqueue(tid)

            deadline = time.time() + 15
            status = None
            while time.time() < deadline:
                status = _get_task(tid).status
                if status in ("completed", "failed"):
                    break
                time.sleep(0.2)
            self.assertEqual(status, "completed")

            progress = json.loads(_get_task(tid).progress_json)
            self.assertEqual(progress.get("percent"), 100)
            self.assertEqual(progress.get("message"), "完成")

            worker.stop()
            proc.cancel()
            try:
                proc.result(timeout=5)
            except Exception:
                pass
        finally:
            loop.call_soon_threadsafe(loop.stop)
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
