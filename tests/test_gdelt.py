"""Requests and returned media must use the DOC API's recent index window."""
import asyncio
from unittest.mock import AsyncMock

from app.sources import gdelt


def test_gdelt_request_caps_lookback_to_recent_three_months(monkeypatch):
    fetch = AsyncMock(return_value={"articles": []})
    monkeypatch.setattr(gdelt, "fetch_json", fetch)
    monkeypatch.setattr(gdelt.settings, "gdelt_months", 24)
    assert asyncio.run(gdelt.search("Anthropic")) == []
    assert fetch.call_args.kwargs["params"]["timespan"] == "3months"
    assert fetch.call_args.kwargs["params"]["query"].startswith('"Anthropic"')


def test_shorter_configured_media_window_is_preserved(monkeypatch):
    monkeypatch.setattr(gdelt.settings, "gdelt_months", 1)
    assert gdelt.search_months() == 1
