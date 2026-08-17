"""并发内核（app.services.execution）行为测试。"""
import threading
import time
import unittest
from concurrent.futures import TimeoutError as FuturesTimeout

from app.services import execution


class HardTimeoutTests(unittest.TestCase):
    def test_returns_result_before_timeout(self):
        self.assertEqual(execution.run_with_hard_timeout(lambda: 42, 2.0), 42)

    def test_raises_hard_timeout_and_counts_zombie(self):
        before = execution.zombie_threads()
        started = time.monotonic()
        with self.assertRaises(execution.HardTimeoutError):
            execution.run_with_hard_timeout(lambda: time.sleep(5), 0.2, label="慢调用")
        self.assertLess(time.monotonic() - started, 2.0, "硬超时必须及时返回，不能等僵尸线程")
        self.assertEqual(execution.zombie_threads(), before + 1)

    def test_hard_timeout_is_futures_timeout_compatible(self):
        with self.assertRaises(FuturesTimeout):
            execution.run_with_hard_timeout(lambda: time.sleep(5), 0.1)

    def test_exception_propagates(self):
        with self.assertRaises(ValueError):
            execution.run_with_hard_timeout(lambda: (_ for _ in ()).throw(ValueError("boom")), 2.0)


class LaneTests(unittest.TestCase):
    def test_lane_limits_concurrency(self):
        limit = 2
        running = 0
        peak = 0
        lock = threading.Lock()

        def work():
            nonlocal running, peak
            with lock:
                running += 1
                peak = max(peak, running)
            time.sleep(0.05)
            with lock:
                running -= 1

        futs = [execution.submit(work, lane="test-lane", lane_limit=limit) for _ in range(6)]
        for f in futs:
            f.result(timeout=5)
        self.assertLessEqual(peak, limit)

    def test_submit_executes_in_worker_thread(self):
        fut = execution.submit(lambda: threading.current_thread().name, lane="test-name")
        self.assertTrue(fut.result(timeout=5).startswith("sonpick-io"))


if __name__ == "__main__":
    unittest.main()
