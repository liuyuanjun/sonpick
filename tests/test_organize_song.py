"""Per-song「整理到标准路径」后端测试（刮削弹窗入口）。

覆盖：
- 完整专辑/标题可整理，缺专辑拒绝。
- 重复下载（歌曲名.flac 与 歌曲名(1).flac）解析为同一目标 → 冲突分组，带码率/大小。
- 应用：保留所选版本、删除另一版本，移除后父目录为空则删除空目录。
- 默认选择（未传 choices）按码率（其次体积）保留。
- 跨歌曲占用目标路径：标记 blocked，应用时不触碰他人文件。
"""
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

import app.database as database
from app.database import Base, SessionLocal
from app.models import MediaSource, Song, SongFile
from app.services.library_organize_service import LibraryOrganizeService

_ENGINE = create_engine(
    f"sqlite:///{Path(tempfile.mkdtemp()) / 'organize_song_test.db'}",
    connect_args={"check_same_thread": False},
    poolclass=NullPool,
)
Base.metadata.create_all(_ENGINE)


def setUpModule():
    SessionLocal.configure(bind=_ENGINE)


def tearDownModule():
    SessionLocal.configure(bind=None)


def _write(path: Path, size: int, byte: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(byte * size)


class OrganizeSongTests(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        # 每个用例独立事务，tearDown 回滚，避免相互污染
        self.db.begin()
        self.root = Path(tempfile.mkdtemp(prefix="sonpick_lib_"))
        self.source = MediaSource(
            name="本地曲库",
            type="local",
            enabled=True,
            root_path=str(self.root),
        )
        self.db.add(self.source)
        self.db.flush()

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    def _make_song(self, title="歌曲名", artist="歌手", album="专辑名"):
        song = Song(title=title, artist=artist, album=album)
        self.db.add(song)
        self.db.flush()
        return song

    def _make_file(self, song, source, rel_path, size, fmt="flac"):
        path = self.root / rel_path
        _write(path, size)
        sf = SongFile(
            song_id=song.id,
            format=fmt,
            local_path=str(path),
            library_source_id=source.id,
            file_size=size,
            availability_status="available",
        )
        self.db.add(sf)
        self.db.flush()
        return sf

    def test_preview_marks_complete_with_album_and_title(self):
        song = self._make_song()
        self._make_file(song, self.source, "Inbox/Song.flac", 1024)
        self.db.commit()
        preview = LibraryOrganizeService(self.db).preview_organize_song(song.id)
        self.assertTrue(preview["complete"])
        self.assertEqual(preview["title"], "歌曲名")
        self.assertEqual(preview["album"], "专辑名")
        self.assertEqual(len(preview["moves"]), 1)
        # 唯一文件：非冲突，仅位移
        self.assertEqual(len(preview["conflicts"]), 0)

    def test_incomplete_song_rejected_on_apply(self):
        song = self._make_song(album=None)  # 缺专辑
        self._make_file(song, self.source, "Inbox/Song.flac", 1024)
        self.db.commit()
        svc = LibraryOrganizeService(self.db)
        preview = svc.preview_organize_song(song.id)
        self.assertFalse(preview["complete"])
        with self.assertRaises(ValueError):
            svc.apply_organize_song(song.id)

    def test_duplicate_download_produces_conflict_with_bitrate_and_size(self):
        song = self._make_song()
        # 重复下载：歌曲名.flac 与 歌曲名(1).flac，同一目标路径
        f1 = self._make_file(song, self.source, "Inbox/歌曲名.flac", 2048)
        f2 = self._make_file(song, self.source, "Inbox/歌曲名(1).flac", 1024)
        self.db.commit()
        preview = LibraryOrganizeService(self.db).preview_organize_song(song.id)
        self.assertEqual(len(preview["conflicts"]), 1)
        group = preview["conflicts"][0]
        self.assertEqual(len(group["candidates"]), 2)
        ids = {c["song_file_id"] for c in group["candidates"]}
        self.assertEqual(ids, {f1.id, f2.id})
        # 每个候选都带格式、体积、码率字段（码率对假文件为 None，仍应存在键）
        for c in group["candidates"]:
            self.assertIn("format", c)
            self.assertIn("file_size", c)
            self.assertIn("bitrate", c)
        # 两文件都被标记为需位移（changed=True）
        self.assertTrue(all(m["changed"] for m in preview["moves"]))

    def test_apply_keeps_chosen_deletes_other_and_removes_empty_folder(self):
        song = self._make_song()
        f_keep = self._make_file(song, self.source, "Inbox/歌曲名.flac", 2048)  # 大 → 默认保留
        f_drop = self._make_file(song, self.source, "Inbox/歌曲名(1).flac", 1024)
        inbox = self.root / "Inbox"
        self.assertTrue(inbox.is_dir())
        self.db.commit()

        result = LibraryOrganizeService(self.db).apply_organize_song(
            song.id, choices=[f_keep.id]
        )
        self.assertEqual(result["deleted"], 1)
        self.assertEqual(result["moved"], 1)
        self.assertEqual(result["kept"], 0)

        # 保留文件已移动到标准路径（服务以解析后的 root 存储绝对路径）
        target = (self.root / "歌手" / "专辑名" / "歌曲名.flac").resolve()
        self.assertTrue(target.is_file())
        # 被删除文件不复存在
        self.assertFalse((inbox / "歌曲名(1).flac").exists())
        # 移除后 Inbox 为空 → 被删除
        self.assertFalse(inbox.exists())

        # 数据库：保留的 SongFile 指向新路径，被删的 SongFile 行消失
        kept = self.db.get(SongFile, f_keep.id)
        self.assertIsNotNone(kept)
        self.assertEqual(kept.local_path, str(target))
        self.assertIsNone(self.db.get(SongFile, f_drop.id))

    def test_apply_default_choice_keeps_larger_file(self):
        song = self._make_song()
        f_big = self._make_file(song, self.source, "Inbox/歌曲名.flac", 4096)
        f_small = self._make_file(song, self.source, "Inbox/歌曲名(1).flac", 512)
        self.db.commit()

        # 不传 choices → 默认保留体积更大者
        result = LibraryOrganizeService(self.db).apply_organize_song(song.id)
        self.assertEqual(result["deleted"], 1)
        self.assertEqual(result["moved"], 1)
        self.assertIsNotNone(self.db.get(SongFile, f_big.id))
        self.assertIsNone(self.db.get(SongFile, f_small.id))

    def test_cross_song_occupied_target_is_blocked_not_touched(self):
        # 歌曲2 已占据标准路径
        song2 = self._make_song(title="歌曲名", artist="歌手", album="专辑名")
        target = (self.root / "歌手" / "专辑名" / "歌曲名.flac").resolve()
        _write(target, 2048)
        sf2 = SongFile(
            song_id=song2.id,
            format="flac",
            local_path=str(target),
            library_source_id=self.source.id,
            file_size=2048,
            availability_status="available",
        )
        self.db.add(sf2)
        self.db.flush()

        # 歌曲1 也解析到同一标准路径，但被歌曲2 占用
        song1 = self._make_song(title="歌曲名", artist="歌手", album="专辑名")
        f1 = self._make_file(song1, self.source, "Inbox/歌曲名.flac", 1024)
        self.db.commit()

        preview = LibraryOrganizeService(self.db).preview_organize_song(song1.id)
        self.assertEqual(preview["blocked_count"], 1)
        blocked = [m for m in preview["moves"] if m["blocked"]]
        self.assertEqual(len(blocked), 1)
        self.assertIn("占用", blocked[0]["block_reason"] or "")
        # 无冲突分组（只有一首歌争用该目标）
        self.assertEqual(len(preview["conflicts"]), 0)

        result = LibraryOrganizeService(self.db).apply_organize_song(song1.id)
        # 被占用 → 跳过，不移动也不删除歌曲1的文件
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["moved"], 0)
        self.assertEqual(result["deleted"], 0)
        self.assertTrue((self.root / "Inbox" / "歌曲名.flac").is_file())
        # 歌曲2 的文件完好无损
        self.assertTrue(target.is_file())
        self.assertIsNotNone(self.db.get(SongFile, f1.id))
        self.assertIsNotNone(self.db.get(SongFile, sf2.id))

    def test_missing_file_is_reported_in_preview(self):
        song = self._make_song()
        sf = self._make_file(song, self.source, "Inbox/歌曲名.flac", 1024)
        # 物理文件不存在（如已手动移动）
        (self.root / "Inbox" / "歌曲名.flac").unlink()
        self.db.commit()
        preview = LibraryOrganizeService(self.db).preview_organize_song(song.id)
        move = preview["moves"][0]
        self.assertEqual(move["status"], "missing")


if __name__ == "__main__":
    unittest.main()
