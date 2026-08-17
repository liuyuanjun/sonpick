"""统一并发内核：全项目唯一的"线程里跑阻塞调用"入口。

设计约束（见 docs/backend-architecture-proposal.md）：

- 共享 executor：所有**可中断/有界**的阻塞调用（自带 timeout 的 HTTP、
  会在边界检查取消的循环）提交到这里，禁止在叶子函数里自建线程池；
- lane 信号量：按资源类型限制并发（search / scrape / download…），
  在 worker 线程内 acquire，不阻塞调用方；
- run_with_hard_timeout：对**无法注入超时**的调用（如 musicdl）施加硬超时
  的唯一实现。超时的线程无法强杀——池随调随弃（shutdown(wait=False)），
  僵尸线程跑完后自行消亡并计入 zombie_threads() 指标；
  这是 CPython 下唯一安全的硬超时手段，全项目禁止再自建 max_workers=1 的临时池。

注意：不要把不可中断的调用直接 submit 到共享 executor 再 result(timeout=...)——
超时后僵尸线程会继续占用共享池槽位，反复超时会把池耗尽。
"""
from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Callable, TypeVar

T = TypeVar("T")

_SHARED_MAX_WORKERS = 10

_executor = ThreadPoolExecutor(
    max_workers=_SHARED_MAX_WORKERS,
    thread_name_prefix="sonpick-io",
)


class HardTimeoutError(FuturesTimeout):
    """run_with_hard_timeout 超时抛出；继承 FuturesTimeout 以兼容既有 except 子句。"""


# ---------------------------------------------------------------- lanes

DEFAULT_LANE_LIMITS: dict[str, int] = {
    "search": 4,   # 搜索：多源并行，用户等待敏感
    "scrape": 2,   # 刮削/歌词：对外部源礼貌
    "download": 2, # 下载/上传：对源与 SQLite 都保守
    "default": 4,
}

_lanes: dict[str, threading.Semaphore] = {}
_lanes_lock = threading.Lock()


def lane_semaphore(lane: str, limit: int | None = None) -> threading.Semaphore:
    """取（或建）某 lane 的信号量。limit 仅首次创建时生效。"""
    with _lanes_lock:
        sem = _lanes.get(lane)
        if sem is None:
            sem = threading.Semaphore(limit or DEFAULT_LANE_LIMITS.get(lane, DEFAULT_LANE_LIMITS["default"]))
            _lanes[lane] = sem
        return sem


def submit(fn: Callable[..., T], *args, lane: str = "default", lane_limit: int | None = None, **kwargs) -> Future:
    """提交到共享 executor；lane 信号量在 worker 线程内 acquire。"""
    sem = lane_semaphore(lane, lane_limit)

    def _guarded() -> T:
        with sem:
            return fn(*args, **kwargs)

    return _executor.submit(_guarded)


def shared_executor() -> ThreadPoolExecutor:
    return _executor


# ------------------------------------------------------- hard timeout

_zombie_count = 0
_zombie_lock = threading.Lock()


def zombie_threads() -> int:
    """因硬超时被弃置、仍在跑的线程数（指标用）。"""
    with _zombie_lock:
        return _zombie_count


def run_with_hard_timeout(fn: Callable[[], T], timeout: float, *, label: str = "") -> T:
    """对不可中断的阻塞调用施加硬超时。

    超时后调用线程无法强杀：池 shutdown(wait=False) 弃置，线程作为僵尸跑完
    后自行消亡（计入 zombie_threads()）。绝不占用共享池槽位。
    """
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sonpick-hto")
    fut = pool.submit(fn)
    try:
        return fut.result(timeout=timeout)
    except FuturesTimeout:
        global _zombie_count
        with _zombie_lock:
            _zombie_count += 1
        raise HardTimeoutError(f"{label or '调用'}超时（>{timeout}s）") from None
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
