"""「加入歌单」归属标注（list_playlists?song_id=）测试。

覆盖：
- 不带 song_id 时 contains_song 为 None（不标注，向后兼容）。
- 带 song_id 时，已含该歌的歌单 contains_song=True，未含的为 False。
- 歌曲被多个歌单包含时全部标 True。
- song_count 与 contains_song 互不影响。
"""
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from app.database import Base, SessionLocal
from app.models import Playlist, PlaylistItem, Song
from app.routers.playlists import list_playlists

_ENGINE = create_engine(
    f"sqlite:///{Path(tempfile.mkdtemp()) / 'playlist_membership_test.db'}",
    connect_args={"check_same_thread": False},
    poolclass=NullPool,
)
Base.metadata.create_all(_ENGINE)


def setUpModule():
    SessionLocal.configure(bind=_ENGINE)


def tearDownModule():
    SessionLocal.configure(bind=None)


class PlaylistMembershipTests(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        self.db.begin()
        for t in (PlaylistItem, Playlist, Song):
            self.db.query(t).delete()
        self.db.flush()

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    def _mk_song(self, title="歌"):
        song = Song(title=title, artist="歌手")
        self.db.add(song)
        self.db.flush()
        return song

    def _mk_playlist(self, name):
        pl = Playlist(name=name)
        self.db.add(pl)
        self.db.flush()
        return pl

    def _add(self, playlist, song, position=1):
        self.db.add(PlaylistItem(playlist_id=playlist.id, song_id=song.id, position=position))
        self.db.flush()

    def test_without_song_id_no_annotation(self):
        pl = self._mk_playlist("我的歌单")
        song = self._mk_song()
        self._add(pl, song)
        out = list_playlists(song_id=None, user="u", db=self.db)
        self.assertEqual(len(out), 1)
        self.assertIsNone(out[0].contains_song)
        self.assertEqual(out[0].song_count, 1)

    def test_with_song_id_marks_membership(self):
        in_pl = self._mk_playlist("已加入")
        other = self._mk_playlist("未加入")
        song = self._mk_song()
        self._add(in_pl, song)
        out = list_playlists(song_id=song.id, user="u", db=self.db)
        by_name = {p.name: p for p in out}
        self.assertTrue(by_name["已加入"].contains_song)
        self.assertFalse(by_name["未加入"].contains_song)
        self.assertEqual(by_name["已加入"].song_count, 1)
        self.assertEqual(by_name["未加入"].song_count, 0)

    def test_song_in_multiple_playlists(self):
        a = self._mk_playlist("A")
        b = self._mk_playlist("B")
        song = self._mk_song()
        self._add(a, song)
        self._add(b, song)
        out = list_playlists(song_id=song.id, user="u", db=self.db)
        self.assertTrue(all(p.contains_song for p in out))

    def test_song_in_no_playlist(self):
        self._mk_playlist("空")
        song = self._mk_song()
        out = list_playlists(song_id=song.id, user="u", db=self.db)
        self.assertEqual(len(out), 1)
        self.assertFalse(out[0].contains_song)


if __name__ == "__main__":
    unittest.main()
