"""歌曲列表的「版本摘要」（列表格式/大小列 与 歌曲信息弹窗的数据来源）。

背景（为什么需要这组测试）：
- ``Song`` 与 ``SongFile`` 是**一对多**，且 ``Song.format`` / ``Song.file_size`` 是只在
  扫描入库与下载替换时写入的遗留列 —— 转码、``keep_both`` 新增版本、整理改路径都不更新它们。
  因此列表的格式/大小必须从 ``SongFile`` 聚合，不能读 ``Song`` 的那两列。
- 一个 Song 对应 N 个版本时必须先定义「取哪个」：这里统一按**音质优先**，且复用播放链路的
  排序规则，保证「列表显示 FLAC」等于「无损优先模式下真的播 FLAC」。
- 列表必须**批量**取版本；逐行查询会把列表接口拖成 N+1。

覆盖：/songs、/favorites、/history、/playlists/{id}/songs、/artists/{name}/songs
      都返回 versions / available_formats / has_playable_file / preferred_version。
"""
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.pool import NullPool

from app.database import Base, SessionLocal
from app.models import Favorite, MediaSource, PlayHistory, Playlist, PlaylistItem, Song, SongFile
from app.routers.library import list_songs
from app.routers.library_extra import list_artist_songs, list_favorites, list_history, library_stats
from app.routers.playlists import list_playlist_songs
from app.services.convert_service import order_playable_files

_ENGINE = create_engine(
    f"sqlite:///{Path(tempfile.mkdtemp()) / 'song_version_summary_test.db'}",
    connect_args={"check_same_thread": False},
    poolclass=NullPool,
)
Base.metadata.create_all(_ENGINE)


def setUpModule():
    SessionLocal.configure(bind=_ENGINE)


def tearDownModule():
    SessionLocal.configure(bind=None)


class SongListVersionSummaryTests(unittest.TestCase):
    def setUp(self):
        # 每次用例从空库开始：模块级共享 engine，若不清理数据会跨用例累加
        Base.metadata.drop_all(_ENGINE)
        Base.metadata.create_all(_ENGINE)
        self.db = SessionLocal()
        self.source = MediaSource(name="本地测试源", type="local", enabled=True, playback_priority=0)
        self.db.add(self.source)
        self.db.flush()

        def add_song(title, files):
            song = Song(title=title, artist="测试艺人", album="测试专辑", duration=210, status="local")
            self.db.add(song)
            self.db.flush()
            for fmt, size, status in files:
                self.db.add(
                    SongFile(
                        song_id=song.id,
                        format=fmt,
                        local_path=f"/tmp/fake/{song.id}-{fmt}.{fmt}",
                        library_source_id=self.source.id,
                        file_size=size,
                        duration=210,
                        availability_status=status,
                    )
                )
            return song

        # 双版本：FLAC + 转码 MP3（列表应取 FLAC）
        self.song_multi = add_song("多版本歌曲", [("flac", 3670016, "available"), ("mp3", 901120, "available")])
        # 单版本
        self.song_single = add_song("单版本歌曲", [("mp3", 524288, "available")])
        # FLAC 失效，仅 MP3 可用
        self.song_degraded = add_song("失效降级歌曲", [("flac", 3670016, "unavailable"), ("mp3", 700000, "available")])
        # 全部失效
        self.song_dead = add_song("全部失效歌曲", [("flac", 3670016, "unavailable")])
        self.db.flush()

        self.db.add(Favorite(song_id=self.song_multi.id))
        self.db.add(PlayHistory(song_id=self.song_multi.id))
        playlist = Playlist(name="测试歌单")
        self.db.add(playlist)
        self.db.flush()
        self.db.add(PlaylistItem(playlist_id=playlist.id, song_id=self.song_multi.id, position=0))
        self.db.commit()
        self.playlist_id = playlist.id

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    # ---------- 各列表接口都要带摘要 ----------

    def test_list_songs_exposes_summary(self):
        page = list_songs(
            q=None, page=1, page_size=100, source_id=None,
            include_unavailable=False, availability="all", user="admin", db=self.db,
        )
        by_id = {item.id: item for item in page.items}
        item = by_id[self.song_multi.id]
        self.assertEqual(item.preferred_version["format"], "flac")
        self.assertEqual(item.preferred_version["file_size"], 3670016)
        self.assertEqual(item.preferred_version["version_count"], 2)
        self.assertEqual(item.available_formats, ["flac", "mp3"])
        self.assertTrue(item.has_playable_file)
        self.assertEqual(len(item.versions), 2)

    def test_favorites_exposes_summary(self):
        items = list_favorites(user="admin", db=self.db)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].preferred_version["format"], "flac")
        self.assertTrue(items[0].is_favorite)

    def test_history_exposes_summary(self):
        items = list_history(limit=50, user="admin", db=self.db)
        self.assertEqual(len(items), 1)
        self.assertIsNotNone(items[0].song)
        self.assertEqual(items[0].song.preferred_version["format"], "flac")

    def test_playlist_songs_exposes_summary(self):
        items = list_playlist_songs(playlist_id=self.playlist_id, user="admin", db=self.db)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].preferred_version["format"], "flac")

    def test_artist_songs_exposes_summary(self):
        items = list_artist_songs(artist_name="测试艺人", user="admin", db=self.db)
        self.assertEqual(len(items), 4)
        by_id = {item.id: item for item in items}
        self.assertEqual(by_id[self.song_single.id].preferred_version["format"], "mp3")
        self.assertEqual(by_id[self.song_single.id].preferred_version["version_count"], 1)

    # ---------- 取值规则 ----------

    def test_preferred_skips_unavailable_and_falls_back(self):
        items = list_artist_songs(artist_name="测试艺人", user="admin", db=self.db)
        by_id = {item.id: item for item in items}
        degraded = by_id[self.song_degraded.id]
        self.assertEqual(degraded.preferred_version["format"], "mp3")
        # 失效版本仍要出现在明细里（供弹窗与 tooltip 展示）
        self.assertEqual(len(degraded.versions), 2)

    def test_no_usable_version_yields_none(self):
        items = list_artist_songs(artist_name="测试艺人", user="admin", db=self.db)
        by_id = {item.id: item for item in items}
        dead = by_id[self.song_dead.id]
        self.assertIsNone(dead.preferred_version)
        self.assertFalse(dead.has_playable_file)

    def test_preferred_matches_playback_order(self):
        """列表显示的首选版本必须等于播放链路（无损优先）的首个候选。"""
        page = list_songs(
            q=None, page=1, page_size=100, source_id=None,
            include_unavailable=False, availability="all", user="admin", db=self.db,
        )
        by_id = {item.id: item for item in page.items}
        song = self.db.get(Song, self.song_multi.id)
        files = self.db.query(SongFile).filter(SongFile.song_id == song.id).all()
        usable = [f for f in files if f.availability_status != "unavailable"]
        expected = order_playable_files(usable, {self.source.id: 0}, lossless_preferred=True)[0]
        self.assertEqual(by_id[song.id].preferred_version["id"], expected.id)

    # ---------- 曲库统计的「本地占用」口径 ----------

    def test_stats_local_size_sums_only_usable_local_versions(self):
        """口径 A：本地可用版本体积之和；失效版本不计（文件已不在）。"""
        stats = library_stats(user="admin", db=self.db)
        expected = 3670016 + 901120 + 524288 + 700000  # 多版本 FLAC+MP3、单版本 MP3、降级后的 MP3
        self.assertEqual(stats.local_size, expected)

    def test_stats_local_size_excludes_webdav_versions(self):
        self.db.add(SongFile(
            song_id=self.song_multi.id, format="flac", webdav_path="/remote/x.flac",
            library_source_id=self.source.id, file_size=9_999_999, availability_status="available",
        ))
        self.db.commit()
        stats = library_stats(user="admin", db=self.db)
        self.assertEqual(stats.local_size, 3670016 + 901120 + 524288 + 700000)

    # ---------- N+1 护栏 ----------
    def test_query_count_does_not_grow_with_song_count(self):
        statements = []

        def count_sql(conn, cursor, statement, params, context, executemany):
            statements.append(statement)

        event.listen(_ENGINE, "before_cursor_execute", count_sql)
        try:
            statements.clear()
            list_songs(
                q=None, page=1, page_size=100, source_id=None,
                include_unavailable=False, availability="all", user="admin", db=self.db,
            )
            baseline = len(statements)

            # 再灌 30 首双版本歌曲，SQL 条数不应随歌曲数增长
            for i in range(30):
                song = Song(title=f"批量歌曲{i}", artist="测试艺人", album="测试专辑", status="local")
                self.db.add(song)
                self.db.flush()
                for fmt in ("flac", "mp3"):
                    self.db.add(SongFile(
                        song_id=song.id, format=fmt,
                        local_path=f"/tmp/fake/bulk-{song.id}-{fmt}.{fmt}",
                        library_source_id=self.source.id, file_size=1000,
                        availability_status="available",
                    ))
            self.db.commit()

            statements.clear()
            list_songs(
                q=None, page=1, page_size=100, source_id=None,
                include_unavailable=False, availability="all", user="admin", db=self.db,
            )
            after = len(statements)
        finally:
            event.remove(_ENGINE, "before_cursor_execute", count_sql)

        self.assertEqual(after, baseline, f"列表 SQL 条数随歌曲数增长（{baseline} → {after}），疑似 N+1")


if __name__ == "__main__":
    unittest.main()
