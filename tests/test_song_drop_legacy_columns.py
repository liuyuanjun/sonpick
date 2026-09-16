"""`songs` 表存量列迁移：删除 format / file_size（rc13）。

为什么要单独测：
- 这两个列只在扫描入库与下载替换时写入，转码 / keep_both / 整理改路径都不更新，
  多版本场景下必然失真，因此统一由 SongFile 承载。删列是不可逆操作，必须验证
  「旧库能迁、数据不丢、重复执行安全」。
- 迁移依赖顺序：``_migrate_song_path_responsibility`` 要从旧 songs 表读 format/file_size
  回填 song_files，必须排在删列之前。
"""
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from app.database import _migrate_song_drop_format_file_size


def _make_old_db(path: Path) -> "create_engine":
    """造一个"迁移前"的最小 songs 表：含 format / file_size / local_path。"""
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE songs ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "title VARCHAR(255) NOT NULL,"
            "artist VARCHAR(255), album VARCHAR(255), year VARCHAR(16), genre VARCHAR(255),"
            "source VARCHAR(64), source_id VARCHAR(128),"
            "format VARCHAR(16), duration INTEGER, file_size INTEGER,"
            "cover_path VARCHAR(1024), lrc_path VARCHAR(1024),"
            "lyrics_provider VARCHAR(64), lyrics_source_id VARCHAR(128),"
            "lyrics_type VARCHAR(16), lyrics_score INTEGER, lyrics_fetched_at DATETIME,"
            "lyrics_instrumental BOOLEAN DEFAULT 0,"
            "status VARCHAR(16), play_count INTEGER, meta_confidence INTEGER,"
            "meta_provider VARCHAR(64), scrape_status VARCHAR(16), meta_locked BOOLEAN,"
            "created_at DATETIME, updated_at DATETIME)"
        ))
        conn.execute(text(
            "INSERT INTO songs (title, artist, album, format, duration, file_size, status, play_count) "
            "VALUES ('旧库歌曲', '旧艺人', '旧专辑', 'flac', 215, 3670016, 'local', 7)"
        ))
    return engine


class SongDropFormatSizeMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()) / "legacy.db"
        self.engine = _make_old_db(self.tmp)

    def _columns(self):
        return {column["name"] for column in inspect(self.engine).get_columns("songs")}

    def test_drops_both_legacy_columns(self):
        self.assertIn("format", self._columns())
        self.assertIn("file_size", self._columns())

        _migrate_song_drop_format_file_size(self.engine)

        columns = self._columns()
        self.assertNotIn("format", columns)
        self.assertNotIn("file_size", columns)

    def test_keeps_other_columns_and_rows_intact(self):
        _migrate_song_drop_format_file_size(self.engine)

        with self.engine.connect() as conn:
            row = conn.execute(text(
                "SELECT id, title, artist, album, duration, status, play_count FROM songs"
            )).mappings().one()

        self.assertEqual(row["title"], "旧库歌曲")
        self.assertEqual(row["artist"], "旧艺人")
        self.assertEqual(row["album"], "旧专辑")
        self.assertEqual(row["duration"], 215)
        self.assertEqual(row["status"], "local")
        self.assertEqual(row["play_count"], 7)
        # id 必须保留（历史引用 Song.id 的地方很多）
        self.assertEqual(row["id"], 1)

    def test_is_idempotent(self):
        _migrate_song_drop_format_file_size(self.engine)
        _migrate_song_drop_format_file_size(self.engine)  # 重跑不得报错

        with self.engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM songs")).scalar()
        self.assertEqual(count, 1)

    def test_noop_when_columns_absent(self):
        """已经删过列的新库：迁移应直接返回，不能重建表。"""
        _migrate_song_drop_format_file_size(self.engine)
        before = self._columns()
        _migrate_song_drop_format_file_size(self.engine)
        self.assertEqual(before, self._columns())

    def test_noop_when_table_absent(self):
        empty = create_engine(f"sqlite:///{Path(tempfile.mkdtemp()) / 'empty.db'}")
        _migrate_song_drop_format_file_size(empty)  # 不得抛异常


if __name__ == "__main__":
    unittest.main()
