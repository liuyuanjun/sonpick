import json
import unittest
import urllib.error
from unittest.mock import patch

from unittest.mock import MagicMock

from app.services.host_limiter import get_limiter
from app.services.lrclib_provider import LrclibProvider, LrclibRateLimitError
from app.services.lyrics_provider import LyricsCandidate, LyricsQuery, score_lyrics_candidate
from app.services.lyrics_search_service import LyricsSearchService
from app.services.lyrics_source_registry import lyrics_source_configs
from app.models import Song


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
    # 限流/冷却状态已迁移到 per-host HostLimiter
    get_limiter("lrclib.net").reset()


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

    def test_search_service_filters_single_source(self):
        song = Song(id=1, title="Song", artist="Artist", album="Album", duration=200)
        db = MagicMock()
        db.get.return_value = MagicMock(lyrics_sources_json=json.dumps([
            {"id": "lrclib", "enabled": True},
            {"id": "netease", "enabled": True},
            {"id": "migu", "enabled": True},
        ]))
        service = LyricsSearchService(db)
        service.query_for_song = lambda song, keyword="": LyricsQuery(
            track_name=song.title, artist_name=song.artist, album_name=song.album, duration=song.duration, keyword=keyword
        )

        class FakeCand:
            def __init__(self, source, query):
                self.source = source
                self.track_name = query.track_name
                self.score = 100
            def to_dict(self, include_lyrics=True):
                return {"source": self.source, "track_name": self.track_name, "score": self.score}

        called = []
        def fake_provider(config):
            class P:
                @staticmethod
                def search(query, limit=20):
                    called.append(config["id"])
                    return [FakeCand(config["id"], query)]
            return P()
        service.provider = fake_provider

        for src in ["netease", "lrclib", "migu"]:
            called.clear()
            result = service.search(song, source=src, keyword="", limit=20)
            self.assertEqual(called, [src], f"source={src} should only call {src}")
            self.assertEqual([c["source"] for c in result["candidates"]], [src])

        called.clear()
        result = service.search(song, source="auto", keyword="", limit=20)
        self.assertEqual(set(called), {"lrclib", "netease", "migu"})


if __name__ == "__main__":
    unittest.main()
