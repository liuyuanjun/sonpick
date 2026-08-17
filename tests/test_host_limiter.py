"""HostLimiter（P4 外部调用治理）行为测试。"""
import threading
import time
import unittest

from app.services.host_limiter import HostLimiter, get_limiter


class HostLimiterTests(unittest.TestCase):
    def test_min_interval_spaces_requests(self):
        limiter = HostLimiter("test-interval", max_concurrent=5, min_interval=0.15)
        stamps = []

        def work():
            stamps.append(time.monotonic())
            return True

        for _ in range(3):
            limiter.run(work)
        gaps = [b - a for a, b in zip(stamps, stamps[1:])]
        for gap in gaps:
            self.assertGreaterEqual(gap, 0.14)

    def test_max_concurrent_caps_inflight(self):
        limiter = HostLimiter("test-conc", max_concurrent=2, min_interval=0)
        running = peak = 0
        lock = threading.Lock()

        def work():
            nonlocal running, peak
            with lock:
                running += 1
                peak = max(peak, running)
            time.sleep(0.05)
            with lock:
                running -= 1

        threads = [threading.Thread(target=lambda: limiter.run(work)) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertLessEqual(peak, 2)

    def test_backoff_cooldown_blocks_and_recovers(self):
        limiter = HostLimiter("test-backoff", max_concurrent=1, min_interval=0)
        limiter.backoff(0.3)
        self.assertGreater(limiter.blocked_seconds, 0)

        calls = []
        started = time.monotonic()
        limiter.run(lambda: calls.append(1))  # 默认行为：等待冷却结束
        self.assertGreaterEqual(time.monotonic() - started, 0.25)
        self.assertEqual(calls, [1])

    def test_on_blocked_can_fail_fast(self):
        limiter = HostLimiter("test-failfast", max_concurrent=1, min_interval=0)
        limiter.backoff(5)

        class RateLimited(Exception):
            pass

        with self.assertRaises(RateLimited):
            limiter.run(lambda: None, on_blocked=lambda wait: (_ for _ in ()).throw(RateLimited()))

    def test_registry_returns_same_instance_per_host(self):
        a = get_limiter("registry-test-host")
        b = get_limiter("registry-test-host")
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
