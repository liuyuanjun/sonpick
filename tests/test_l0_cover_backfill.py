"""L0 封面回填回归测试（metadata-l0-cover-refactor）。

口径：Song.cover_path 必须指向 data/covers/by-hash；版本侧车（SongFile.cover_path）
是 L1 写穿，不得反向覆盖已有 L0 封面。v0.15.2-rc1 前 SongFileResolver.refresh_song_assets
无条件用侧车覆盖 Song.cover_path，导致下载写入的 by-hash 在每次播放解析时被改回侧车。
"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import app.services.media_meta_service as meta
from app.services.media_meta_service import backfill_song_cover_l0, is_l0_cover_path
from app.services.song_file_resolver import SongFileResolver

_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32 + b"\xff\xd9"


def _make_covers(tmp: Path):
    sidecar = tmp / "album" / "cover.jpg"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_bytes(_JPEG)
    return sidecar


class BackfillSongCoverL0Tests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.covers = self.tmp / "covers"
        (self.covers / "by-hash").mkdir(parents=True)
        self._patcher = patch.object(meta, "covers_root", lambda: self.covers)
        self._patcher.start()
        self.sidecar = _make_covers(self.tmp)

    def tearDown(self):
        self._patcher.stop()
        self._tmp.cleanup()

    def test_sidecar_is_materialized_to_by_hash(self):
        song = SimpleNamespace(cover_path=str(self.sidecar))
        self.assertTrue(backfill_song_cover_l0(song, str(self.sidecar)))
        self.assertTrue(is_l0_cover_path(song.cover_path))
        self.assertTrue(Path(song.cover_path).is_file())

    def test_existing_l0_cover_is_never_overwritten(self):
        song = SimpleNamespace(cover_path=None)
        backfill_song_cover_l0(song, str(self.sidecar))
        l0_path = song.cover_path
        self.assertTrue(is_l0_cover_path(l0_path))
        # 另一张内容不同的候选封面也不得覆盖既有 L0
        other = self.tmp / "other.jpg"
        other.write_bytes(_JPEG + b"different")
        self.assertFalse(backfill_song_cover_l0(song, str(other)))
        self.assertEqual(song.cover_path, l0_path)

    def test_missing_candidate_keeps_current(self):
        song = SimpleNamespace(cover_path=str(self.tmp / "gone.jpg"))
        self.assertFalse(backfill_song_cover_l0(song, None))
        self.assertFalse(backfill_song_cover_l0(song, str(self.tmp / "also-gone.jpg")))


class _FakeDb:
    def add(self, obj):
        pass


class RefreshSongAssetsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.covers = self.tmp / "covers"
        (self.covers / "by-hash").mkdir(parents=True)
        self._patcher = patch.object(meta, "covers_root", lambda: self.covers)
        self._patcher.start()
        self.sidecar = _make_covers(self.tmp)

    def tearDown(self):
        self._patcher.stop()
        self._tmp.cleanup()

    def test_resolver_does_not_clobber_l0_cover_but_follows_lrc(self):
        song = SimpleNamespace(cover_path=None, lrc_path=None, updated_at=None)
        selected = SimpleNamespace(cover_path=str(self.sidecar), lrc_path="/music/a.lrc")
        resolver = SongFileResolver(_FakeDb())
        self.assertTrue(resolver.refresh_song_assets(song, selected))
        self.assertTrue(is_l0_cover_path(song.cover_path))
        self.assertEqual(song.lrc_path, "/music/a.lrc")
        # 再次用另一个版本的侧车回填：L0 封面保持不变
        other = self.tmp / "v2cover.jpg"
        other.write_bytes(_JPEG + b"v2")
        changed = resolver.refresh_song_assets(
            song, SimpleNamespace(cover_path=str(other), lrc_path="/music/b.lrc")
        )
        self.assertTrue(changed)  # lrc 跟随选中版本
        self.assertEqual(song.lrc_path, "/music/b.lrc")
        self.assertNotEqual(song.cover_path, str(other))
        self.assertTrue(is_l0_cover_path(song.cover_path))


if __name__ == "__main__":
    unittest.main()
