"""歌单手动排序 + 播放阈值 gate 的回归测试。

覆盖：
- reorder_playlists：按给定顺序落 0..n-1；未列出的歌单保持相对顺序排到末尾；未知 id 报 400。
- create_playlist：新歌单排到末尾（取 max+1），不插队。
- list_playlists：按 sort_order 升序返回，不再吃 updated_at。
- _backfill_playlist_sort_order：升级时按旧的展示顺序（updated_at desc）回填；
  已有真实顺序时**幂等退出**（不重排用户摆好的顺序）。
- record_play 阈值：played_s 未达阈值 → 不写最近播放、播放次数也不加；
  达标 → 两者都记；played_s 为 None → 无条件记录（兼容老前端）。
"""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from app.database import Base, SessionLocal, _backfill_playlist_sort_order
from app.models import AppSettings, PlayHistory, Playlist, PlaylistItem, Song
from app.routers.library_extra import record_play
from app.routers.playlists import create_playlist, list_playlists, reorder_playlists
from app.schemas import PlaylistCreate, PlaylistOrder, PlayRecord

_ENGINE = create_engine(
    f"sqlite:///{Path(tempfile.mkdtemp()) / 'playlist_order_test.db'}",
    connect_args={"check_same_thread": False},
    poolclass=NullPool,
)
Base.metadata.create_all(_ENGINE)


def setUpModule():
    SessionLocal.configure(bind=_ENGINE)


def tearDownModule():
    SessionLocal.configure(bind=None)


class _Base(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        self.db.begin()
        for t in (PlaylistItem, PlayHistory, Playlist, Song, AppSettings):
            self.db.query(t).delete()
        self.db.flush()

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    def _playlist(self, name, order, minutes_ago):
        pl = Playlist(
            name=name,
            sort_order=order,
            updated_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
        )
        self.db.add(pl)
        self.db.flush()
        return pl

    def _song(self, title="曲目"):
        song = Song(title=title, artist="A", status="local")
        self.db.add(song)
        self.db.flush()
        return song


class PlaylistOrderTests(_Base):
    def test_list_orders_by_sort_order_not_updated_at(self):
        # sort_order 与 updated_at 故意互相矛盾：后者更新，但必须按前者排
        self._playlist("先", 0, minutes_ago=10)
        self._playlist("后", 1, minutes_ago=0)
        names = [p.name for p in list_playlists(db=self.db)]
        self.assertEqual(names, ["先", "后"])

    def test_create_appends_to_tail(self):
        self._playlist("A", 0, minutes_ago=1)
        self._playlist("B", 7, minutes_ago=2)
        created = create_playlist(PlaylistCreate(name="新"), db=self.db)
        self.assertEqual(created.sort_order, 8)
        self.assertEqual(
            [p.name for p in list_playlists(db=self.db)], ["A", "B", "新"]
        )

    def test_create_into_empty_db_starts_at_zero(self):
        created = create_playlist(PlaylistCreate(name="唯一"), db=self.db)
        self.assertEqual(created.sort_order, 0)

    def test_reorder_assigns_dense_indexes(self):
        a = self._playlist("A", 0, minutes_ago=3)
        b = self._playlist("B", 1, minutes_ago=2)
        c = self._playlist("C", 2, minutes_ago=1)
        out = reorder_playlists(PlaylistOrder(ids=[c.id, a.id, b.id]), db=self.db)
        self.assertEqual([p.name for p in out], ["C", "A", "B"])
        self.assertEqual([p.sort_order for p in out], [0, 1, 2])

    def test_reorder_puts_unlisted_at_tail(self):
        """别的客户端刚建的歌单没出现在 ids 里：不能被清成 0 插到最前，而应整体排到末尾。"""
        a = self._playlist("A", 0, minutes_ago=3)
        b = self._playlist("B", 1, minutes_ago=2)
        c = self._playlist("C", 2, minutes_ago=1)
        out = reorder_playlists(PlaylistOrder(ids=[c.id]), db=self.db)
        self.assertEqual([p.name for p in out], ["C", "A", "B"])
        self.assertEqual([p.sort_order for p in out], [0, 1, 2])

    def test_reorder_dedupes_and_rejects_unknown(self):
        a = self._playlist("A", 0, minutes_ago=2)
        b = self._playlist("B", 1, minutes_ago=1)
        out = reorder_playlists(PlaylistOrder(ids=[b.id, b.id, a.id]), db=self.db)
        self.assertEqual([p.name for p in out], ["B", "A"])

        with self.assertRaises(HTTPException) as ctx:
            reorder_playlists(PlaylistOrder(ids=[a.id, 999999]), db=self.db)
        self.assertEqual(ctx.exception.status_code, 400)


class PlaylistSortOrderBackfillTests(_Base):
    """
    注意：`_backfill_playlist_sort_order` 走 `engine.begin()` 另开连接，
    所以夹具必须先 commit —— 否则它看不到本会话未提交的行，测试会假绿。
    """

    def _seed_and_backfill(self):
        self.db.commit()
        _backfill_playlist_sort_order(_ENGINE)
        self.db.expire_all()
        return [p.name for p in list_playlists(db=self.db)]

    def test_backfill_follows_old_updated_at_order(self):
        # 迁移刚加完列的状态：所有行 sort_order 都是 0，但 updated_at 有先后
        self._playlist("最早", 0, minutes_ago=30)
        self._playlist("居中", 0, minutes_ago=10)
        self._playlist("最近", 0, minutes_ago=1)
        self.assertEqual(self._seed_and_backfill(), ["最近", "居中", "最早"])

    def test_backfill_is_idempotent_once_order_exists(self):
        """已有真实顺序时不得重排 —— 否则用户摆好的顺序每次启动都被 updated_at 冲掉。"""
        self._playlist("我摆的第一", 0, minutes_ago=30)
        self._playlist("我摆的第二", 1, minutes_ago=1)
        self.assertEqual(self._seed_and_backfill(), ["我摆的第一", "我摆的第二"])


class RecordPlayThresholdTests(_Base):
    def setUp(self):
        super().setUp()
        self.song = self._song()

    def _threshold(self, seconds):
        self.db.add(AppSettings(id=1, storage_path="/tmp/music", recent_play_threshold_s=seconds))
        self.db.flush()

    def _history_count(self):
        return self.db.query(PlayHistory).filter(PlayHistory.song_id == self.song.id).count()

    def test_below_threshold_records_nothing(self):
        self._threshold(3)
        before = self.song.play_count or 0
        record_play(self.song.id, PlayRecord(played_s=1.8), db=self.db)
        self.db.refresh(self.song)
        self.assertEqual(self._history_count(), 0)
        self.assertEqual(self.song.play_count or 0, before)

    def test_at_threshold_records_both(self):
        self._threshold(3)
        before = self.song.play_count or 0
        record_play(self.song.id, PlayRecord(played_s=3), db=self.db)
        self.db.refresh(self.song)
        self.assertEqual(self._history_count(), 1)
        self.assertEqual(self.song.play_count or 0, before + 1)

    def test_threshold_reads_setting(self):
        """阈值是配置项：调到 20 秒后，听 10 秒就不该记。"""
        self._threshold(20)
        record_play(self.song.id, PlayRecord(played_s=10), db=self.db)
        self.assertEqual(self._history_count(), 0)

    def test_threshold_zero_records_everything(self):
        self._threshold(0)
        record_play(self.song.id, PlayRecord(played_s=0), db=self.db)
        self.assertEqual(self._history_count(), 1)

    def test_missing_played_s_is_backward_compatible(self):
        self._threshold(3)
        record_play(self.song.id, None, db=self.db)
        self.assertEqual(self._history_count(), 1)


if __name__ == "__main__":
    unittest.main()
