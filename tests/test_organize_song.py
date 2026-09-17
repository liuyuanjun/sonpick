"""Per-song「整理到标准路径」后端测试（刮削弹窗入口）。

覆盖：
- 完整专辑/标题可整理，缺专辑拒绝。
- 重复下载（歌曲名.flac 与 歌曲名(1).flac）解析为同一目标 → 冲突分组，带码率/大小。
- 应用：保留所选版本、删除另一版本，移除后父目录为空则删除空目录。
- 默认选择（未传 choices）按码率（其次体积）保留。
- 跨歌曲占用目标路径：标记 blocked，应用时不触碰他人文件。
- 内置曲库保留「按格式归档」根目录（无损文件不得被搬出 Lossless/）。
- 排除路径（回收站 / 隐藏目录）的本地版本：不进整理计划，并由扫描清理删除。
"""
import json
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

import app.database as database
from app.database import Base, SessionLocal
from app.models import AppSettings, MediaSource, Song, SongFile
from app.services.library_organize_service import LibraryOrganizeService
from app.services.library_scan_service import EXCLUDED_LAST_ERROR, LibraryScanService

DEFAULT_EXCLUDE = [
    "**/.*",
    "**/.@*",
    "**/@eaDir/**",
    "**/#recycle/**",
    "**/Thumbs.db",
    "**/*.tmp",
]

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
        # .物理文件不存在（如已手动移动）
        (self.root / "Inbox" / "歌曲名.flac").unlink()
        self.db.commit()
        preview = LibraryOrganizeService(self.db).preview_organize_song(song.id)
        move = preview["moves"][0]
        self.assertEqual(move["status"], "missing")

    def test_excluded_trash_path_skipped_in_preview(self):
        song = self._make_song(title="关于郑州的记忆", artist="李志", album="你好，郑州")
        # 真实版本：已处于标准路径
        real = self._make_file(
            song, self.source, "李志/你好，郑州/关于郑州的记忆.mp3", 9128, fmt="mp3"
        )
        # 回收站里的同名文件（.@#local/trash），应被排除、不出现在整理计划
        trash = self._make_file(
            song,
            self.source,
            ".@#local/trash/Standard/李志/05你好，郑州.wav/关于郑州的记忆.mp3",
            9128,
            fmt="mp3",
        )
        self.db.commit()
        preview = LibraryOrganizeService(self.db).preview_organize_song(song.id)
        ids = [e["song_file_id"] for e in preview["moves"]]
        self.assertIn(real.id, ids)
        self.assertNotIn(trash.id, ids)

    def _set_settings(self, *, lossless="Lossless", lossy="Lossy") -> None:
        cfg = self.db.get(AppSettings, 1)
        if cfg is None:
            cfg = AppSettings(id=1, storage_path=str(self.root))
            self.db.add(cfg)
        cfg.storage_path = str(self.root)
        cfg.lossless_output_path = lossless
        cfg.lossy_output_path = lossy
        self.db.flush()

    def test_lossless_version_keeps_format_dir(self):
        """内置曲库：无损版本整理后仍留在 Lossless/ 内，不得被搬出格式目录。"""
        self._set_settings()
        song = self._make_song(title="春末的南方城市", artist="李志", album="梵高先生")
        self._make_file(
            song,
            self.source,
            "Lossless/李志/02梵高先生.wav/春末的南方城市.wav",
            4096,
            fmt="wav",
        )
        self.db.commit()

        preview = LibraryOrganizeService(self.db).preview_organize_song(song.id)
        move = preview["moves"][0]
        # 只修专辑目录名，格式目录 Lossless 保留
        self.assertEqual(move["to_path"], "Lossless/李志/梵高先生/春末的南方城市.wav")
        self.assertTrue(move["changed"])

        LibraryOrganizeService(self.db).apply_organize_song(song.id)
        self.assertTrue(
            (self.root / "Lossless" / "李志" / "梵高先生" / "春末的南方城市.wav").is_file()
        )
        # 旧的「02梵高先生.wav」目录被清掉，且没有把文件挪到 root 下
        self.assertFalse((self.root / "Lossless" / "李志" / "02梵高先生.wav").exists())
        self.assertFalse((self.root / "李志").exists())

    def test_lossy_version_goes_to_lossy_dir(self):
        """有损版本沿用其当前所在的 LOSSY/ 目录（配置名不同也应识别）。"""
        self._set_settings(lossless="Lossless", lossy="LOSSY")
        song = self._make_song(title="春末的南方城市", artist="李志", album="梵高先生")
        self._make_file(
            song, self.source, "LOSSY/李志/02梵高先生.wav/春末的南方城市.mp3", 2048, fmt="mp3"
        )
        self.db.commit()
        preview = LibraryOrganizeService(self.db).preview_organize_song(song.id)
        self.assertEqual(preview["moves"][0]["to_path"], "LOSSY/李志/梵高先生/春末的南方城市.mp3")

    def test_file_outside_format_dirs_falls_back_to_root(self):
        self._set_settings()
        song = self._make_song(title="春末的南方城市", artist="李志", album="梵高先生")
        self._make_file(
            song, self.source, "待整理/春末的南方城市.wav", 4096, fmt="wav"
        )
        self.db.commit()
        preview = LibraryOrganizeService(self.db).preview_organize_song(song.id)
        self.assertEqual(preview["moves"][0]["to_path"], "李志/梵高先生/春末的南方城市.wav")

    def test_excluded_out_of_root_path_skipped_in_preview(self):
        """来源根目录配成子目录时，回收站里的版本（在根之外）仍应被排除。"""
        self._set_settings(lossless="Lossless", lossy="Lossy")
        song = self._make_song(title="春末的南方城市", artist="李志", album="梵高先生")
        real = self._make_file(
            song, self.source, "Lossless/李志/梵高先生/春末的南方城市.wav", 4096, fmt="wav"
        )
        trash = self._make_file(
            song,
            self.source,
            ".@#local/trash/Standard/李志/02梵高先生.wav/春末的南方城市.mp3",
            2048,
            fmt="mp3",
        )
        # 模拟「来源根目录 == Lossless」的历史配置：回收站版本落在根之外
        self.source.root_path = str(self.root / "Lossless")
        self.source.exclude_globs = json.dumps(DEFAULT_EXCLUDE)
        self.db.flush()
        self.db.commit()

        preview = LibraryOrganizeService(self.db).preview_organize_song(song.id)
        ids = [e["song_file_id"] for e in preview["moves"]]
        self.assertIn(real.id, ids)
        self.assertNotIn(trash.id, ids)
        # 根内的文件留在 Lossless（= 根）内，不再多挂一层 Lossless 前缀
        self.assertEqual(preview["moves"][0]["to_path"], "李志/梵高先生/春末的南方城市.wav")


class ExcludedPathCleanupTests(unittest.TestCase):
    """排除路径下的历史本地版本：自愈标记 + 扫描清理删除。"""

    def setUp(self):
        self.db = SessionLocal()
        self.db.begin()
        self.root = Path(tempfile.mkdtemp(prefix="sonpick_excl_"))
        self.source = MediaSource(
            name="本地曲库",
            type="local",
            enabled=True,
            root_path=str(self.root),
            exclude_globs=json.dumps(DEFAULT_EXCLUDE),
        )
        self.db.add(self.source)
        self.db.flush()

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    def _make(self, song_id, rel_path, fmt):
        path = self.root / rel_path
        _write(path, 1024)
        sf = SongFile(
            song_id=song_id,
            format=fmt,
            local_path=str(path),
            library_source_id=self.source.id,
            file_size=1024,
            availability_status="available",
        )
        self.db.add(sf)
        self.db.flush()
        return sf

    def test_heal_marks_and_purge_removes_excluded_version(self):
        song = Song(title="春末的南方城市", artist="李志", album="梵高先生")
        self.db.add(song)
        self.db.flush()
        real = self._make(song.id, "Lossless/李志/梵高先生/春末的南方城市.wav", "wav")
        trash = self._make(
            song.id,
            ".@#local/trash/Standard/李志/02梵高先生.wav/春末的南方城市.mp3",
            "mp3",
        )
        self.db.commit()

        svc = LibraryScanService(self.db)
        heal = svc._heal_stale_paths()
        # 模块级测试库可能残留其它用例的回收站行，因此只断言本用例的行
        self.assertGreaterEqual(heal["excluded_marked"], 1)
        marked = self.db.get(SongFile, trash.id)
        self.assertEqual(marked.availability_status, "unavailable")
        self.assertEqual(marked.last_error, EXCLUDED_LAST_ERROR)

        removed = svc._purge_excluded_local_versions()
        self.assertGreaterEqual(removed, 1)
        self.assertIsNone(self.db.get(SongFile, trash.id))
        # 正常版本完好，物理文件不动
        kept = self.db.get(SongFile, real.id)
        self.assertIsNotNone(kept)
        self.assertEqual(kept.availability_status, "available")
        self.assertTrue(Path(kept.local_path).is_file())
        self.assertTrue(
            (self.root / ".@#local/trash/Standard/李志/02梵高先生.wav/春末的南方城市.mp3").is_file()
        )


class ScanExcludeTests(unittest.TestCase):
    def test_excluded_matches_nested_hidden_dirs(self):
        from app.services.library_scan_service import _is_excluded

        globs = [
            "**/.*",
            "**/.@*",
            "**/@eaDir/**",
            "**/#recycle/**",
            "**/Thumbs.db",
            "**/*.tmp",
        ]
        self.assertTrue(
            _is_excluded(
                ".@#local/trash/Standard/李志/05你好，郑州.wav/3关于郑州的记忆.mp3", globs
            )
        )
        # 普通歌曲路径不应被排除
        self.assertFalse(
            _is_excluded("李志/你好，郑州/关于郑州的记忆.mp3", globs)
        )
        # @eaDir 与 #recycle 嵌套
        self.assertTrue(_is_excluded("@eaDir/sub/foo.mp3", globs))
        self.assertTrue(_is_excluded("#recycle/foo.mp3", globs))
        # 隐藏目录下的任意层级都应被排除
        self.assertTrue(_is_excluded("a/b/.hidden/deep/file.mp3", globs))


if __name__ == "__main__":
    unittest.main()
