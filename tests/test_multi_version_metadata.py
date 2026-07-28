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
        self.assertEqual(result["versions"][2]["reason"], "远端只读，未写入")

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

            def download(_url, target, timeout=20):
                Path(target).write_bytes(b"cover")
                return {"ok": True, "path": str(target)}

            with (
                patch("app.services.song_metadata_apply_service.SongFileResolver", return_value=resolver),
                patch("app.services.song_metadata_apply_service.download_cover_with_diagnostics", side_effect=download) as downloader,
                patch("app.services.song_metadata_apply_service.write_audio_tags", return_value={"cover": True}),
            ):
                result = apply_metadata_to_song_files(
                    FakeDb(), song(), selected_fields={"cover"}, cover_url="https://example.com/cover.jpg"
                )

        self.assertEqual(downloader.call_count, 2)
        self.assertEqual(result["written"], 3)
        self.assertEqual(files[0].cover_path, files[1].cover_path)
        self.assertNotEqual(files[0].cover_path, files[2].cover_path)

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


if __name__ == "__main__":
    unittest.main()
