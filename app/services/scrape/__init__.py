"""Metadata scrape package: multi-provider pipeline with priority fallback."""
from app.services.scrape.base import ScrapeQuery, ScrapeResult
from app.services.scrape.pipeline import (
    ScrapePipeline,
    default_pipeline,
    enrich_song_via_pipeline,
    lookup_album_via_pipeline,
)

__all__ = [
    "ScrapeQuery",
    "ScrapeResult",
    "ScrapePipeline",
    "default_pipeline",
    "enrich_song_via_pipeline",
    "lookup_album_via_pipeline",
]
