import unittest
from types import SimpleNamespace

from app.models import MediaSource, SongFile
from app.services.convert_service import ConvertService, order_playable_files
from app.services.song_version_summary import build_version_summary


def _song_file(**kw):
    kw.setdefault("library_source_id", None)
    kw.setdefault("source_priority", 0)
    return SimpleNamespace(**kw)


class FakeQuery:
    def __init__(self, items):
        self.items = items

    def filter(self, *args):
        return self

    def all(self):
        return self.items


class FakeDb:
    """按模型分发桩数据：SongFile 给版本列表，MediaSource 给来源（含 playback_priority）。"""

    def __init__(self, files, sources=None):
        self.files = files
        self.sources = sources or []

    def query(self, model):
        if model is MediaSource:
            return FakeQuery(self.sources)
        if model is SongFile:
            return FakeQuery(self.files)
        return FakeQuery([])


class PlaybackSelectionTests(unittest.TestCase):
    def test_prefers_mp3_when_lossless_preference_is_off(self):
        files = [
            _song_file(id=1, song_id=1, format="flac", local_path="/music/a.flac", webdav_path=None, availability_status="available"),
            _song_file(id=2, song_id=1, format="mp3", local_path="/mp3/a.mp3", webdav_path=None, availability_status="available"),
        ]
        selected = ConvertService(FakeDb(files)).select_playable_file(SimpleNamespace(id=1), False)
        self.assertEqual(selected.format, "mp3")

    def test_falls_back_when_preferred_source_is_unavailable(self):
        files = [
            _song_file(id=1, song_id=1, format="mp3", local_path="/mp3/a.mp3", webdav_path=None, availability_status="unavailable", source_priority=10),
            _song_file(id=2, song_id=1, format="mp3", local_path="/webdav/a.mp3", webdav_path=None, availability_status="available"),
        ]
        selected = ConvertService(FakeDb(files)).select_playable_file(SimpleNamespace(id=1), False)
        self.assertEqual(selected.id, 2)


class VersionSummaryTests(unittest.TestCase):
    """列表上的「格式 / 大小」列取 preferred_version。

    它是**播放选择规则的第一个**（无损优先），所以必须与播放行为一致：
    显示 FLAC 就意味着无损优先模式下真的会播 FLAC。
    """

    def _files(self):
        return [
            _song_file(id=1, song_id=1, format="flac", local_path="/music/a.flac", webdav_path=None,
                       availability_status="available", file_size=3670016, duration=352),
            _song_file(id=2, song_id=1, format="mp3", local_path="/mp3/a.mp3", webdav_path=None,
                       availability_status="available", file_size=901120, duration=352),
        ]

    def _to_dict(self, item):
        return {
            "id": item.id, "format": item.format, "local_path": item.local_path,
            "webdav_path": item.webdav_path, "file_size": item.file_size,
            "availability_status": item.availability_status,
        }

    def test_prefers_lossless_and_reports_version_count(self):
        files = self._files()
        for item in files:
            item.to_dict = lambda item=item: self._to_dict(item)
        summary = build_version_summary(files, {})
        self.assertEqual(summary["preferred_version"]["format"], "flac")
        self.assertEqual(summary["preferred_version"]["file_size"], 3670016)
        self.assertEqual(summary["preferred_version"]["version_count"], 2)
        self.assertEqual(summary["available_formats"], ["flac", "mp3"])
        self.assertTrue(summary["has_playable_file"])
        # 版本明细必须完整回传，信息弹窗依赖它
        self.assertEqual(len(summary["versions"]), 2)

    def test_ignores_unavailable_version_when_picking_preferred(self):
        files = self._files()
        files[0].availability_status = "unavailable"  # FLAC 失效 → 回落 MP3
        for item in files:
            item.to_dict = lambda item=item: self._to_dict(item)
        summary = build_version_summary(files, {})
        self.assertEqual(summary["preferred_version"]["format"], "mp3")
        self.assertFalse(summary["preferred_version"]["availability_status"] == "unavailable")

    def test_no_playable_version_yields_empty_summary(self):
        files = [_song_file(id=9, song_id=1, format="flac", local_path=None, webdav_path=None,
                            availability_status="unavailable", file_size=None, duration=None)]
        files[0].to_dict = lambda: self._to_dict(files[0])
        summary = build_version_summary(files, {})
        self.assertIsNone(summary["preferred_version"])
        self.assertFalse(summary["has_playable_file"])

    def test_preferred_matches_playback_first_choice(self):
        """显示的版本必须等于播放链路的第一个候选（同一套排序规则）。"""
        files = self._files()
        for item in files:
            item.to_dict = lambda item=item: self._to_dict(item)
        summary = build_version_summary(files, {})
        playback_first = order_playable_files(files, {}, lossless_preferred=True)[0]
        self.assertEqual(summary["preferred_version"]["id"], playback_first.id)


if __name__ == "__main__":
    unittest.main()
