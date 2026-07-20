"""Targeted executable checks for scrape source configuration and providers."""
from __future__ import annotations

from app.services.scrape.source_registry import dump_source_configs, select_source_configs, source_configs


def main() -> None:
    defaults = source_configs(None)
    assert {item["id"] for item in defaults} >= {"netease", "itunes", "deezer", "musicbrainz", "acoustid"}
    changed = [dict(item) for item in defaults]
    next(item for item in changed if item["id"] == "itunes")["enabled"] = False
    next(item for item in changed if item["id"] == "deezer")["auto_enabled"] = False
    stored = dump_source_configs(changed)
    manual = {item["id"] for item in select_source_configs(stored, automatic=False)}
    automatic = {item["id"] for item in select_source_configs(stored, automatic=True)}
    assert "itunes" not in manual
    assert "deezer" in manual and "deezer" not in automatic
    print("source registry OK")


if __name__ == "__main__":
    main()
