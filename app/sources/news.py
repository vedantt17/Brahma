"""Bounded primary news lookup with an independent public-feed fallback."""
import asyncio
import logging

from app.sources import gdelt, news_rss

log = logging.getLogger(__name__)


async def search(name: str) -> gdelt.MediaResults:
    providers = {"gdelt": False}
    try:
        primary = await asyncio.wait_for(gdelt.search(name), timeout=12)
        providers["gdelt"] = True
        metadata = dict(getattr(primary, "search_metadata", {}) or {})
        # A provider can return many unrelated headlines which all fail local
        # entity/risk checks. That is still zero evidence, so try the feed.
        if primary:
            metadata.update(provider="GDELT", providers=providers)
            return gdelt.MediaResults(primary, metadata)
    except Exception as exc:
        log.warning("Primary news lookup failed: %s", type(exc).__name__)
        primary, metadata = None, {}
    providers["google_news"] = False
    try:
        fallback = await asyncio.wait_for(news_rss.search(name), timeout=16)
        providers["google_news"] = True
        metadata = dict(fallback.search_metadata)
        metadata.update(providers=providers, fallback=True)
        return gdelt.MediaResults(fallback, metadata)
    except Exception as exc:
        log.warning("News fallback failed: %s", type(exc).__name__)
        if primary is not None:
            metadata.update(provider="GDELT", providers=providers)
            return gdelt.MediaResults(primary, metadata)
        # Return explicit provider failures; the pipeline must not treat this
        # successful Python call as successful source coverage.
        return gdelt.MediaResults([], {"providers": providers,
                                      "search_name": gdelt.search_name(name),
                                      "lookback_months": gdelt.search_months()})
