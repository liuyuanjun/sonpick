"""musicdl_service 多源并发搜索行为测试（P2 并发内核回归保护）。

覆盖：单源失败不影响其他源、结果按来源声明顺序合并、
SearchCancelled 穿透中断整轮搜索、超时/异常隔离。
"""
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from app.services.musicdl_service import MusicDLService, SearchCancelled


def _make_service() -> MusicDLService:
    return MusicDLService(None)


class SearchSourcesTests(unittest.TestCase):
    def _run(self, behaviors: dict, sources: list[str], cancelled=None):
        """behaviors: src -> ("ok", items) / ("error", exc) / ("slow", seconds, items)"""
        svc = _make_service()

        def fake_search_one(keyword, src, work_dir, size, on_event=None, cancelled=None):
            behavior = behaviors[src]
            kind = behavior[0]
            if kind == "ok":
                return behavior[1], None
            if kind == "error":
                return [], f"{src}: {behavior[1]}"
            if kind == "raise":
                raise behavior[1]
            if kind == "slow":
                time.sleep(behavior[1])
                return behavior[2], None
            raise AssertionError(f"unknown behavior {kind}")

        with mock.patch.object(svc, "_search_one_source", side_effect=fake_search_one):
            return svc._search_sources(
                "kw",
                music_sources=sources,
                work_dir=Path("/tmp/test"),
                cancelled=cancelled,
            )

    def test_single_source_failure_does_not_affect_others(self):
        items, errors = self._run(
            {
                "a": ("ok", ["song-a"]),
                "b": ("error", "连接失败"),
                "c": ("ok", ["song-c"]),
            },
            ["a", "b", "c"],
        )
        self.assertEqual(items, ["song-a", "song-c"])
        self.assertEqual(len(errors), 1)
        self.assertIn("连接失败", errors[0])

    def test_results_merged_in_declared_source_order(self):
        # b 慢但声明在前，结果仍按声明顺序而非完成顺序
        items, _ = self._run(
            {
                "a": ("slow", 0.3, ["song-a"]),
                "b": ("ok", ["song-b"]),
            },
            ["a", "b"],
        )
        self.assertEqual(items, ["song-a", "song-b"])

    def test_sources_run_concurrently(self):
        started = time.monotonic()
        items, _ = self._run(
            {
                "a": ("slow", 0.4, ["a"]),
                "b": ("slow", 0.4, ["b"]),
                "c": ("slow", 0.4, ["c"]),
            },
            ["a", "b", "c"],
        )
        elapsed = time.monotonic() - started
        self.assertEqual(len(items), 3)
        self.assertLess(elapsed, 1.0, "三路慢源应并行（总耗时≈最慢一路而非之和）")

    def test_unexpected_exception_isolated_per_source(self):
        items, errors = self._run(
            {
                "a": ("raise", RuntimeError("bug")),
                "b": ("ok", ["song-b"]),
            },
            ["a", "b"],
        )
        self.assertEqual(items, ["song-b"])
        self.assertEqual(len(errors), 1)

    def test_search_cancelled_propagates(self):
        with self.assertRaises(SearchCancelled):
            self._run(
                {
                    "a": ("raise", SearchCancelled()),
                    "b": ("slow", 1.0, ["b"]),
                },
                ["a", "b"],
            )


if __name__ == "__main__":
    unittest.main()
