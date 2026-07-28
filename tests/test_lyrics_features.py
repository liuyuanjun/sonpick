import json
import unittest
import urllib.error
from unittest.mock import patch

from app.services.lrclib_provider import LrclibProvider, LrclibRateLimitError
from app.services.lyrics_provider import LyricsCandidate, LyricsQuery, score_lyrics_candidate
from app.services.lyrics_source_registry import lyrics_source_configs


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def reset_lrclib():
    LrclibProvider._cache.clear()
    LrclibProvider._last_request_at = 0
    LrclibProvider._blocked_until = 0


class LyricsFeatureTests(unittest.TestCase):
    def test_lyrics_sources_are_independent_and_lrclib_enabled(self):
        configs = lyrics_source_configs(None, scrape_raw=json.dumps([
            {"id": "netease", "enabled": False},
            {"id": "migu", "enabled": True},
        ]))
        by_id = {item["id"]: item for item in configs}
        self.assertTrue(by_id["lrclib"]["enabled"])
        self.assertFalse(by_id["netease"]["enabled"])
        self.assertTrue(by_id["migu"]["enabled"])

    def test_candidate_scoring_penalizes_version_mismatch(self):
        query = LyricsQuery(track_name="Song", artist_name="Artist", album_name="Album", duration=200)
        normal = score_lyrics_candidate(query, LyricsCandidate(source="x", source_id="1", track_name="Song", artist_name="Artist", album_name="Album", duration=200))
        live = score_lyrics_candidate(query, LyricsCandidate(source="x", source_id="2", track_name="Song Live", artist_name="Artist", album_name="Album", duration=200))
        self.assertGreater(normal.score, live.score)
        self.assertTrue(live.match_detail["version_mismatch"])

    def test_lrclib_exact_404_falls_back_to_search(self):
        reset_lrclib()
        calls = []

        def urlopen(request, timeout):
            calls.append(request.full_url)
            if "/api/get?" in request.full_url:
                raise urllib.error.HTTPError(request.full_url, 404, "not found", {}, None)
            return FakeResponse([{"id": 1, "trackName": "Song", "artistName": "Artist", "albumName": "Album", "duration": 200, "syncedLyrics": "[00:01]line"}])

        with patch("urllib.request.urlopen", side_effect=urlopen):
            rows = LrclibProvider(minimum_interval=0.2).search(LyricsQuery(track_name="Song", artist_name="Artist", album_name="Album", duration=200))
        self.assertEqual(len(rows), 1)
        self.assertTrue(any("/api/get?" in url for url in calls))
        self.assertTrue(any("/api/search?" in url for url in calls))

    def test_lrclib_429_exposes_retry_after(self):
        reset_lrclib()
        error = urllib.error.HTTPError("https://lrclib.net/api/search", 429, "limited", {"Retry-After": "7"}, None)
        with patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(LrclibRateLimitError) as caught:
                LrclibProvider().search(LyricsQuery(track_name="Song", artist_name="Artist"))
        self.assertEqual(caught.exception.retry_after, 7)

    def test_lrclib_cache_shared_between_instances(self):
        reset_lrclib()
        with patch("urllib.request.urlopen", return_value=FakeResponse([])) as mocked:
            query = LyricsQuery(track_name="Song", artist_name="Artist")
            LrclibProvider().search(query)
            LrclibProvider().search(query)
        self.assertEqual(mocked.call_count, 1)


if __name__ == "__main__":
    unittest.main()
