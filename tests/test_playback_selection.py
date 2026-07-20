import unittest
from types import SimpleNamespace

from app.services.convert_service import ConvertService


class FakeQuery:
    def __init__(self, items):
        self.items = items

    def filter(self, *args):
        return self

    def all(self):
        return self.items


class FakeDb:
    def __init__(self, files):
        self.files = files

    def query(self, _):
        return FakeQuery(self.files)


class PlaybackSelectionTests(unittest.TestCase):
    def test_prefers_mp3_when_lossless_preference_is_off(self):
        files = [
            SimpleNamespace(id=1, song_id=1, format="flac", local_path="/music/a.flac", webdav_path=None, availability_status="available", source_priority=0),
            SimpleNamespace(id=2, song_id=1, format="mp3", local_path="/mp3/a.mp3", webdav_path=None, availability_status="available", source_priority=0),
        ]
        selected = ConvertService(FakeDb(files)).select_playable_file(SimpleNamespace(id=1), False)
        self.assertEqual(selected.format, "mp3")

    def test_falls_back_when_preferred_source_is_unavailable(self):
        files = [
            SimpleNamespace(id=1, song_id=1, format="mp3", local_path="/mp3/a.mp3", webdav_path=None, availability_status="unavailable", source_priority=10),
            SimpleNamespace(id=2, song_id=1, format="mp3", local_path="/webdav/a.mp3", webdav_path=None, availability_status="available", source_priority=0),
        ]
        selected = ConvertService(FakeDb(files)).select_playable_file(SimpleNamespace(id=1), False)
        self.assertEqual(selected.id, 2)


if __name__ == "__main__":
    unittest.main()
