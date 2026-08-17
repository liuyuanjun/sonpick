"""per-host 外部调用限流器：并发槽 + 最小请求间隔 + 429 冷却退避。

每个外部主机一个实例（get_limiter 注册表），替代各 provider 自带的
全局大锁/自制节流。线程安全，供同步调用方使用。

语义：
- 并发槽：同一 host 最多 max_concurrent 个在途请求；
- 最小间隔：请求发起时刻按 min_interval 排布（预约制，并发线程不扎堆）；
- 冷却期：收到 429 等限流信号后调用 backoff(seconds)，冷却期内
  run() 默认等待，或经 on_blocked 回调交由调用方快速失败。
"""
from __future__ import annotations

import threading
import time
from typing import Callable, TypeVar

T = TypeVar("T")


class HostLimiter:
    def __init__(self, host: str, *, max_concurrent: int = 2, min_interval: float = 0.3):
        self.host = host
        self.min_interval = max(0.0, float(min_interval))
        self._sem = threading.Semaphore(max(1, int(max_concurrent)))
        self._lock = threading.Lock()
        self._next_allowed_at = 0.0
        self._blocked_until = 0.0

    @property
    def blocked_seconds(self) -> float:
        """当前剩余冷却秒数（0 表示未在冷却期）。"""
        with self._lock:
            return max(0.0, self._blocked_until - time.monotonic())

    def reset(self) -> None:
        """清空间隔预约与冷却状态（测试/运维用）。"""
        with self._lock:
            self._next_allowed_at = 0.0
            self._blocked_until = 0.0

    def backoff(self, seconds: float) -> None:
        """收到限流信号时调用：进入冷却期（取已有与新值的较大者）。"""
        with self._lock:
            self._blocked_until = max(self._blocked_until, time.monotonic() + max(0.0, float(seconds)))

    def run(self, fn: Callable[[], T], *, on_blocked: Callable[[float], None] | None = None) -> T:
        """在限流约束下执行 fn。

        最小间隔导致的等待直接睡眠；冷却期导致的等待在睡眠前先回调
        on_blocked(剩余冷却秒数)——回调可抛异常实现快速失败，返回则继续等待。
        """
        with self._sem:
            while True:
                with self._lock:
                    now = time.monotonic()
                    cooldown = self._blocked_until - now
                    wait = max(self._next_allowed_at, self._blocked_until) - now
                    if wait <= 0:
                        # 预约下一个可用时刻
                        self._next_allowed_at = max(now, self._next_allowed_at) + self.min_interval
                        break
                if cooldown > 0 and on_blocked is not None:
                    on_blocked(cooldown)
                time.sleep(wait)
            return fn()


_limiters: dict[str, HostLimiter] = {}
_registry_lock = threading.Lock()


def get_limiter(host: str, *, max_concurrent: int = 2, min_interval: float = 0.3) -> HostLimiter:
    """取（或建）某 host 的限流器；参数仅首次创建时生效。"""
    with _registry_lock:
        limiter = _limiters.get(host)
        if limiter is None:
            limiter = HostLimiter(host, max_concurrent=max_concurrent, min_interval=min_interval)
            _limiters[host] = limiter
        return limiter
