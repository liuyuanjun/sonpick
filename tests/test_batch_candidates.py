"""批量下载候选选择逻辑测试（task_worker._order_candidates / _resolve_first）。

批量是无人值守的「取第一命中」：歌名歌手匹配的候选应排最前，
解析失败的候选应回退下一条而不是直接判失败。
"""
import unittest
from unittest import mock

from app.services.task_worker import _candidate_score, _order_candidates, _resolve_first, _split_keyword


def _song(name, singers):
    return mock.Mock(song_name=name, singers=singers)


class SplitKeywordTests(unittest.TestCase):
    def test_title_artist(self):
        self.assertEqual(_split_keyword("晴天 - 周杰伦"), ("晴天", "周杰伦"))

    def test_title_only(self):
        self.assertEqual(_split_keyword("晴天"), ("晴天", None))

    def test_extra_dash_kept_in_artist(self):
        self.assertEqual(_split_keyword("A - B - C"), ("A", "B - C"))


class OrderCandidatesTests(unittest.TestCase):
    def test_exact_match_beats_cover_and_live(self):
        items = [
            _song("晴天(深情版)", "Lucky小爱"),
            _song("晴天", "周杰伦"),
            _song("晴天(Live)", "周杰伦"),
        ]
        ordered = _order_candidates(items, "晴天 - 周杰伦")
        self.assertIs(ordered[0], items[1])

    def test_title_match_without_artist_overlap_ranks_middle(self):
        items = [
            _song("别的歌", "周杰伦"),
            _song("晴天", "翻唱者"),
            _song("晴天", "周杰伦"),
        ]
        ordered = _order_candidates(items, "晴天 - 周杰伦")
        self.assertIs(ordered[0], items[2])
        self.assertIs(ordered[1], items[1])
        self.assertIs(ordered[2], items[0])

    def test_no_artist_in_keyword_only_title_matters(self):
        items = [_song("晴天(伴奏)", "甲"), _song("晴天", "乙")]
        ordered = _order_candidates(items, "晴天")
        self.assertIs(ordered[0], items[1])

    def test_stable_when_nothing_matches(self):
        items = [_song("A", "甲"), _song("B", "乙")]
        self.assertEqual(_order_candidates(items, "晴天 - 周杰伦"), items)


class CandidateScoreTests(unittest.TestCase):
    def test_exact_match(self):
        self.assertEqual(_candidate_score(_song("晴天", "周杰伦"), "晴天 - 周杰伦"), 0)

    def test_version_difference_is_partial(self):
        self.assertEqual(_candidate_score(_song("晴天(Live)", "周杰伦"), "晴天 - 周杰伦"), 1)
        self.assertEqual(_candidate_score(_song("晴天(伴奏)", "周杰伦"), "晴天"), 1)

    def test_artist_mismatch_is_partial(self):
        self.assertEqual(_candidate_score(_song("晴天", "翻唱者"), "晴天 - 周杰伦"), 1)

    def test_title_mismatch_is_reject(self):
        # 完全不相关的歌（批量误配场景）必须判 2，由 worker 拦截为「未找到」
        self.assertEqual(_candidate_score(_song("XYZ123 (Raul Facio Remix)", "Camilo Díaz"), "不存在的歌名xyz123 - 没人"), 2)

    def test_empty_keyword_title_passes(self):
        self.assertEqual(_candidate_score(_song("任何歌", "任何人"), " - "), 0)


class ResolveFirstTests(unittest.TestCase):
    def test_first_resolvable_wins(self):
        light = mock.Mock()
        resolved = mock.Mock()
        light.resolve_for_download.side_effect = [RuntimeError("无版权"), resolved]
        a, b = _song("A", "甲"), _song("B", "乙")
        item, out = _resolve_first(light, [a, b], "best")
        self.assertIs(item, b)
        self.assertIs(out, resolved)

    def test_all_failed_returns_none_pair(self):
        light = mock.Mock()
        light.resolve_for_download.side_effect = RuntimeError("x")
        item, out = _resolve_first(light, [_song("A", "甲"), _song("B", "乙")], "best")
        self.assertIsNone(item)
        self.assertIsNone(out)

    def test_candidate_limit(self):
        from app.services.task_worker import _BATCH_CANDIDATE_LIMIT

        light = mock.Mock()
        light.resolve_for_download.side_effect = RuntimeError("x")
        items = [_song(f"S{i}", "甲") for i in range(_BATCH_CANDIDATE_LIMIT + 3)]
        _resolve_first(light, items, "best")
        self.assertEqual(light.resolve_for_download.call_count, _BATCH_CANDIDATE_LIMIT)

    def test_on_skip_notified(self):
        light = mock.Mock()
        resolved = mock.Mock()
        light.resolve_for_download.side_effect = [RuntimeError("无版权"), resolved]
        skipped = []
        _resolve_first(light, [_song("A", "甲"), _song("B", "乙")], "best", on_skip=lambda c, e: skipped.append(str(e)))
        self.assertEqual(skipped, ["无版权"])


if __name__ == "__main__":
    unittest.main()
