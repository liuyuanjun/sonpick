import unittest
from types import SimpleNamespace

from app.models import MediaSource, SongFile
from app.services.convert_service import ConvertService


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


if __name__ == "__main__":
    unittest.main()
