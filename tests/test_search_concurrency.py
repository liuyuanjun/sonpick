"""light_search_service 多源并发搜索行为测试（P2 并发内核回归保护）。

覆盖：单源失败不影响其他源、结果按来源声明顺序合并、
异常按源隔离、缓存命中后不再发起搜索。
"""
import time
import unittest
from unittest import mock

from app.services.light_search_service import LightSearchService, _TTLCache


def _make_service() -> LightSearchService:
    return LightSearchService(None)


def _song(name):
    class _S:
        identifier = name
        source = "x"
        song_name = name

        def __init__(self):
            self._sonpick_source = None

    return _S()


class SearchSourcesTests(unittest.TestCase):
    def setUp(self):
        # 每个用例独立缓存，避免命中污染
        self._patch = mock.patch("app.services.light_search_service._search_cache", _TTLCache())
        self._patch.start()

    def tearDown(self):
        self._patch.stop()

    def _run(self, behaviors: dict, sources: list[str]):
        """behaviors: src -> ("ok", items) / ("error", exc) / ("slow", seconds, items)"""
        svc = _make_service()

        def fake_search_one(keyword, src, size):
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
            return svc.search("kw", music_sources=sources)

    def test_single_source_failure_does_not_affect_others(self):
        items, errors = self._run(
            {
                "QQMusicClient": ("ok", [_song("song-a")]),
                "NeteaseMusicClient": ("error", "连接失败"),
                "MiguMusicClient": ("ok", [_song("song-c")]),
            },
            ["QQMusicClient", "NeteaseMusicClient", "MiguMusicClient"],
        )
        self.assertEqual([s.identifier for s in items], ["song-a", "song-c"])
        self.assertEqual(len(errors), 1)
        self.assertIn("连接失败", errors[0])

    def test_results_merged_in_declared_source_order(self):
        # 慢的源声明在前，结果仍按声明顺序而非完成顺序
        items, _ = self._run(
            {
                "QQMusicClient": ("slow", 0.3, [_song("song-a")]),
                "NeteaseMusicClient": ("ok", [_song("song-b")]),
            },
            ["QQMusicClient", "NeteaseMusicClient"],
        )
        self.assertEqual([s.identifier for s in items], ["song-a", "song-b"])

    def test_sources_run_concurrently(self):
        started = time.monotonic()
        items, _ = self._run(
            {
                "QQMusicClient": ("slow", 0.4, [_song("a")]),
                "NeteaseMusicClient": ("slow", 0.4, [_song("b")]),
                "MiguMusicClient": ("slow", 0.4, [_song("c")]),
            },
            ["QQMusicClient", "NeteaseMusicClient", "MiguMusicClient"],
        )
        elapsed = time.monotonic() - started
        self.assertEqual(len(items), 3)
        self.assertLess(elapsed, 1.0, "三路慢源应并行（总耗时≈最慢一路而非之和）")

    def test_unexpected_exception_isolated_per_source(self):
        items, errors = self._run(
            {
                "QQMusicClient": ("raise", RuntimeError("bug")),
                "NeteaseMusicClient": ("ok", [_song("song-b")]),
            },
            ["QQMusicClient", "NeteaseMusicClient"],
        )
        self.assertEqual([s.identifier for s in items], ["song-b"])
        self.assertEqual(len(errors), 1)

    def test_unknown_sources_are_ignored(self):
        items, errors = _make_service().search("kw", music_sources=["NoSuchClient"])
        self.assertEqual(items, [])
        self.assertEqual(errors, [])

    def test_sonpick_source_tagged_per_item(self):
        items, _ = self._run(
            {"QQMusicClient": ("ok", [_song("song-a")])},
            ["QQMusicClient"],
        )
        self.assertEqual(items[0]._sonpick_source, "QQMusicClient")


class SearchCacheTests(unittest.TestCase):
    def test_cache_hit_avoids_repeat_search(self):
        svc = _make_service()
        with mock.patch("app.services.light_search_service._search_cache", _TTLCache()) as cache:
            cache.set(("search", "kw", "QQMusicClient", 20), [_song("cached")])
            with mock.patch.object(svc, "_search_one_source", wraps=svc._search_one_source) as spy:
                items, errors = svc.search("kw", music_sources=["QQMusicClient"])
        self.assertEqual([s.identifier for s in items], ["cached"])
        self.assertEqual(errors, [])
        # _search_one_source 仍被调用（缓存判断在其内部），但不应触发 client 构造
        self.assertEqual(spy.call_count, 1)


if __name__ == "__main__":
    unittest.main()
