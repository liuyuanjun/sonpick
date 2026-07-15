"""Built-in scrape providers."""
from app.services.scrape.providers.musicbrainz import MusicBrainzProvider
from app.services.scrape.providers.musicdl_provider import MusicDLProvider
from app.services.scrape.providers.smart_cn_provider import SmartCNProvider

__all__ = ["MusicBrainzProvider", "MusicDLProvider", "SmartCNProvider"]
