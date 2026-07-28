import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.routers.library_extra import _candidate_current_values


class ScrapeCoverMetadataTests(unittest.TestCase):
    def test_returns_existing_cover_size(self):
        with tempfile.TemporaryDirectory() as directory:
            cover_path = Path(directory) / "cover.jpg"
            cover_path.write_bytes(b"cover-bytes")
            song = SimpleNamespace(
                title="标题",
                artist="艺术家",
                album="专辑",
                year="2024",
                genre="流行",
                cover_path=str(cover_path),
            )
            with patch("app.routers.library_extra._local_song_file", return_value=None):
                values = _candidate_current_values(song, SimpleNamespace())

        self.assertTrue(values["cover_exists"])
        self.assertEqual(values["cover_size"], 11)
        self.assertEqual(values["cover"], str(cover_path))

    def test_missing_cover_is_reported_as_absent(self):
        song = SimpleNamespace(
            title="标题",
            artist="艺术家",
            album="专辑",
            year=None,
            genre=None,
            cover_path="/missing/cover.jpg",
        )
        with (
            patch("app.routers.library_extra._local_song_file", return_value=None),
            patch("app.routers.library_extra.materialize_song_cover", return_value=None),
        ):
            values = _candidate_current_values(song, SimpleNamespace())

        self.assertFalse(values["cover_exists"])
        self.assertIsNone(values["cover_size"])
        self.assertIsNone(values["cover"])


if __name__ == "__main__":
    unittest.main()
