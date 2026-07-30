import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.services.lyrics_search_service import LyricsSearchService
from app.services.song_metadata_apply_service import apply_metadata_to_song_files


class FakeDb:
    def add(self, _value):
        return None

    def flush(self):
        return None

    def commit(self):
        return None


class FakeResolver:
    def __init__(self, files, writable):
        self.files = files
        self.writable = writable

    def all_files(self, _song):
        return self.files

    def writable_local_files(self, _song):
        return self.writable


def song_file(file_id, *, local_path=None, webdav_path=None, fmt="flac"):
    return SimpleNamespace(
        id=file_id,
        format=fmt,
        local_path=local_path,
        webdav_path=webdav_path,
        cover_path=None,
        lrc_path=None,
        updated_at=None,
    )


def song():
    return SimpleNamespace(
        id=1,
        title="标题",
        artist="艺术家",
        album="专辑",
        year="2025",
        genre="流行",
        cover_path=None,
        lrc_path=None,
        lyrics_provider=None,
        lyrics_source_id=None,
        lyrics_type=None,
        lyrics_score=None,
        lyrics_fetched_at=None,
        lyrics_instrumental=False,
        updated_at=None,
    )


class MultiVersionMetadataTests(unittest.TestCase):
    def test_writes_tags_to_all_local_files_and_skips_webdav(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "a.flac"
            second = Path(directory) / "b.mp3"
            first.write_bytes(b"a")
            second.write_bytes(b"b")
            files = [
                song_file(1, local_path=str(first)),
                song_file(2, local_path=str(second), fmt="mp3"),
                song_file(3, webdav_path="/remote/c.flac"),
            ]
            resolver = FakeResolver(files, files[:2])
            with (
                patch("app.services.song_metadata_apply_service.SongFileResolver", return_value=resolver),
                patch("app.services.song_metadata_apply_service.write_audio_tags", return_value={"title": True}) as write_tags,
            ):
                result = apply_metadata_to_song_files(
                    FakeDb(), song(), selected_fields={"title", "artist"}, cover_url=None
                )

        self.assertEqual(write_tags.call_count, 2)
        self.assertEqual(result["written"], 2)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["unsupported"], 0)
        self.assertEqual(result["versions"][2]["reason"], "远端只读，未写入")
        self.assertTrue(result["ok"])

    def test_cover_sidecar_is_written_once_per_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            album = Path(directory) / "album"
            other = Path(directory) / "other"
            album.mkdir()
            other.mkdir()
            files = [
                song_file(1, local_path=str(album / "a.flac")),
                song_file(2, local_path=str(album / "b.mp3"), fmt="mp3"),
                song_file(3, local_path=str(other / "c.flac")),
            ]
            for item in files:
                Path(item.local_path).write_bytes(b"audio")
            resolver = FakeResolver(files, files)
            target_song = song()

            def fake_l0(*, cover_url=None, cover_source_path=None, cover_bytes=None, cover_mime=None):
                l0 = Path(directory) / "l0-cover.jpg"
                l0.write_bytes(b"cover-l0")
                return {"ok": True, "path": str(l0), "source": "url"}

            with (
                patch("app.services.song_metadata_apply_service.SongFileResolver", return_value=resolver),
                patch("app.services.song_metadata_apply_service._store_l0_cover", side_effect=fake_l0) as l0_store,
                patch("app.services.song_metadata_apply_service.write_audio_tags", return_value={"cover": True}),
            ):
                result = apply_metadata_to_song_files(
                    FakeDb(), target_song, selected_fields={"cover"}, cover_url="https://example.com/cover.jpg"
                )

            self.assertEqual(l0_store.call_count, 1)
            self.assertEqual(result["written"], 3)
            self.assertTrue(result["ok"])
            self.assertTrue(target_song.cover_path)
            self.assertEqual(files[0].cover_path, files[1].cover_path)
            self.assertNotEqual(files[0].cover_path, files[2].cover_path)
            self.assertTrue(Path(files[0].cover_path).is_file())
            self.assertTrue(Path(files[2].cover_path).is_file())

    def test_partial_tag_failure_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            files = [song_file(1, local_path=str(Path(directory) / "a.flac")), song_file(2, local_path=str(Path(directory) / "b.flac"))]
            for item in files:
                Path(item.local_path).write_bytes(b"audio")
            resolver = FakeResolver(files, files)
            with (
                patch("app.services.song_metadata_apply_service.SongFileResolver", return_value=resolver),
                patch("app.services.song_metadata_apply_service.write_audio_tags", side_effect=[{"title": True}, {}]),
            ):
                result = apply_metadata_to_song_files(FakeDb(), song(), selected_fields={"title"}, cover_url=None)

        self.assertTrue(result["partial"])
        self.assertEqual(result["written"], 1)
        self.assertEqual(result["failed"], 1)
        self.assertFalse(result["ok"])

    def test_wma_unsupported_with_sidecar_still_ok(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "data"
            data_dir.mkdir()
            wma = Path(directory) / "track.wma"
            wma.write_bytes(b"wma")
            files = [song_file(1, local_path=str(wma), fmt="wma")]
            resolver = FakeResolver(files, files)
            target_song = song()

            def fake_l0(*, cover_url=None, cover_source_path=None, cover_bytes=None, cover_mime=None):
                l0 = data_dir / "by-hash" / "abc.jpg"
                l0.parent.mkdir(parents=True, exist_ok=True)
                l0.write_bytes(b"cover-bytes")
                return {"ok": True, "path": str(l0), "source": "url"}

            with (
                patch("app.services.song_metadata_apply_service.SongFileResolver", return_value=resolver),
                patch("app.services.song_metadata_apply_service._store_l0_cover", side_effect=fake_l0),
                patch("app.services.song_metadata_apply_service.write_audio_tags") as write_tags,
            ):
                result = apply_metadata_to_song_files(
                    FakeDb(),
                    target_song,
                    selected_fields={"title", "cover"},
                    cover_url="https://example.com/c.jpg",
                )

            write_tags.assert_not_called()
            self.assertTrue(result["ok"])
            self.assertEqual(result["failed"], 0)
            self.assertEqual(result["unsupported"], 1)
            self.assertEqual(result["written"], 0)
            self.assertEqual(result["versions"][0]["status"], "unsupported")
            self.assertTrue(target_song.cover_path)
            self.assertTrue(Path(directory, "cover.jpg").is_file())
            self.assertTrue(files[0].cover_path)

    def test_cover_l0_failure_does_not_block_text_tag_write(self):
        """封面 L0 失败时，文本标签仍应写穿，不再整版本 failed。"""
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "a.flac"
            second = Path(directory) / "b.mp3"
            first.write_bytes(b"a")
            second.write_bytes(b"b")
            files = [
                song_file(1, local_path=str(first)),
                song_file(2, local_path=str(second), fmt="mp3"),
            ]
            resolver = FakeResolver(files, files)
            target_song = song()

            with (
                patch("app.services.song_metadata_apply_service.SongFileResolver", return_value=resolver),
                patch(
                    "app.services.song_metadata_apply_service._store_l0_cover",
                    return_value={"ok": False, "path": None, "error": "封面下载失败: HTTP 403"},
                ),
                patch(
                    "app.services.song_metadata_apply_service.write_audio_tags",
                    return_value={"title": "标题", "artist": "艺术家"},
                ) as write_tags,
            ):
                result = apply_metadata_to_song_files(
                    FakeDb(),
                    target_song,
                    selected_fields={"title", "artist", "cover"},
                    cover_url="https://example.com/blocked.jpg",
                )

            self.assertEqual(write_tags.call_count, 2)
            self.assertEqual(result["written"], 2)
            self.assertEqual(result["failed"], 0)
            # L0 封面失败 → 整体 ok=false，但文本已写入
            self.assertFalse(result["ok"])
            self.assertTrue(result["partial"])
            self.assertIn("封面未写入", result.get("error_summary") or "")
            for version in result["versions"]:
                self.assertEqual(version["status"], "written")
                self.assertIn("侧车封面失败", (version.get("reason") or ""))

    def test_write_audio_tags_error_key_is_surfaced(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "a.flac"
            path.write_bytes(b"audio")
            files = [song_file(1, local_path=str(path))]
            resolver = FakeResolver(files, files)
            with (
                patch("app.services.song_metadata_apply_service.SongFileResolver", return_value=resolver),
                patch(
                    "app.services.song_metadata_apply_service.write_audio_tags",
                    return_value={"_error": "PermissionError: Read-only file system"},
                ),
            ):
                result = apply_metadata_to_song_files(
                    FakeDb(), song(), selected_fields={"title"}, cover_url=None
                )

        self.assertEqual(result["failed"], 1)
        self.assertFalse(result["ok"])
        self.assertIn("PermissionError", result["versions"][0]["error"])
        self.assertIn("PermissionError", result.get("error_summary") or "")


class MultiVersionLyricsTests(unittest.TestCase):
    def test_apply_writes_sidecar_and_tags_for_all_local_files(self):
        with tempfile.TemporaryDirectory() as directory:
            files = [
                song_file(1, local_path=str(Path(directory) / "a.flac")),
                song_file(2, local_path=str(Path(directory) / "b.mp3"), fmt="mp3"),
                song_file(3, webdav_path="/remote/c.flac"),
            ]
            for item in files[:2]:
                Path(item.local_path).write_bytes(b"audio")
            resolver = FakeResolver(files, files[:2])
            with (
                patch("app.services.lyrics_search_service.SongFileResolver", return_value=resolver),
                patch("app.services.lyrics_search_service.write_audio_tags", return_value={"lyrics": True}) as write_tags,
            ):
                result = LyricsSearchService(FakeDb()).apply(
                    song(),
                    {"source": "lrclib", "source_id": "1", "synced_lyrics": "[00:01]歌词", "score": 95},
                )

            self.assertTrue(Path(files[0].lrc_path).is_file())
            self.assertTrue(Path(files[1].lrc_path).is_file())
        self.assertEqual(write_tags.call_count, 2)
        self.assertEqual(result["written_file_tags"], 2)
        self.assertEqual(result["versions"][2]["status"], "skipped")

    def test_clear_removes_all_sidecars_and_embedded_lyrics(self):
        with tempfile.TemporaryDirectory() as directory:
            files = [song_file(1, local_path=str(Path(directory) / "a.flac")), song_file(2, local_path=str(Path(directory) / "b.mp3"), fmt="mp3")]
            for item in files:
                Path(item.local_path).write_bytes(b"audio")
                sidecar = Path(item.local_path).with_suffix(".lrc")
                sidecar.write_text("歌词", encoding="utf-8")
                item.lrc_path = str(sidecar)
            resolver = FakeResolver(files, files)
            target_song = song()
            target_song.lrc_path = files[0].lrc_path
            with (
                patch("app.services.lyrics_search_service.SongFileResolver", return_value=resolver),
                patch("app.services.lyrics_search_service.write_audio_tags", return_value={"lyrics": True}) as write_tags,
            ):
                result = LyricsSearchService(FakeDb()).clear(target_song)

            self.assertFalse(Path(directory, "a.lrc").exists())
            self.assertFalse(Path(directory, "b.lrc").exists())
        self.assertEqual(write_tags.call_count, 2)
        self.assertEqual(result["written_file_tags"], 2)

    def test_apply_rejects_song_without_local_file(self):
        remote = song_file(1, webdav_path="/remote/a.flac")
        resolver = FakeResolver([remote], [])
        with patch("app.services.lyrics_search_service.SongFileResolver", return_value=resolver):
            with self.assertRaisesRegex(RuntimeError, "没有可写入的本地文件"):
                LyricsSearchService(FakeDb()).apply(song(), {"plain_lyrics": "歌词"})

    def test_wma_lyrics_sidecar_ok_embed_unsupported(self):
        with tempfile.TemporaryDirectory() as directory:
            wma = Path(directory) / "a.wma"
            wma.write_bytes(b"x")
            files = [song_file(1, local_path=str(wma), fmt="wma")]
            resolver = FakeResolver(files, files)
            with (
                patch("app.services.lyrics_search_service.SongFileResolver", return_value=resolver),
                patch("app.services.lyrics_search_service.write_audio_tags") as write_tags,
            ):
                result = LyricsSearchService(FakeDb()).apply(
                    song(),
                    {"source": "lrclib", "synced_lyrics": "[00:01]hi", "score": 90},
                )
            self.assertTrue(Path(files[0].lrc_path).is_file())
        write_tags.assert_not_called()
        self.assertTrue(result["ok"])
        self.assertEqual(result["unsupported"], 1)
        self.assertEqual(result["versions"][0]["status"], "unsupported")


class CoverL0HelpersTests(unittest.TestCase):
    def test_store_cover_bytes_dedupes_by_hash(self):
        from app.services import media_meta_service as mms

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(mms, "covers_root", return_value=Path(directory)):
                Path(directory, "by-hash").mkdir(parents=True, exist_ok=True)
                data = b"\xff\xd8\xff" + b"jpeg-payload"
                first = mms.store_cover_bytes(data)
                second = mms.store_cover_bytes(data)
                self.assertEqual(first, second)
                self.assertTrue(first.is_file())
                self.assertIn("by-hash", str(first))

    def test_tag_write_capability_matrix(self):
        from app.services.media_meta_service import tag_write_capability

        self.assertTrue(tag_write_capability(".mp3")["text"])
        self.assertTrue(tag_write_capability("x.flac")["cover"])
        self.assertFalse(tag_write_capability(".wma")["lyrics"])
        self.assertFalse(tag_write_capability("track.wav")["text"])


if __name__ == "__main__":
    unittest.main()
