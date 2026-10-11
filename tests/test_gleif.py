"""Identity lookup must use a supplied LEI rather than fuzzy name search."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from app.sources import gleif


LEI = "984500B6DEB8CEBC4Z70"
RECORD = {"id": LEI, "attributes": {"lei": LEI, "entity": {
    "legalName": {"name": "ANTHROPIC, PBC"},
    "legalAddress": {"addressLines": ["548 Market Street"],
                     "city": "San Francisco", "country": "US"},
    "status": "ACTIVE",
}}}


def test_supplied_lei_uses_exact_record_endpoint(monkeypatch):
    fetch = AsyncMock(return_value={"data": RECORD})
    monkeypatch.setattr(gleif, "fetch_json", fetch)
    monkeypatch.setattr(gleif, "_relation", AsyncMock(return_value=None))
    records = asyncio.run(gleif.search("Anthropic", "United States",
                                      registration_number=f" {LEI.lower()} "))
    fetch.assert_awaited_once_with(f"{gleif.SEARCH_URL}/{LEI}", ttl_hours=24)
    assert len(records) == 1
    assert records[0].name == "ANTHROPIC, PBC"
    assert records[0].source_id == LEI
    assert records[0].raw["lei"] == LEI


def test_non_lei_registration_keeps_name_search(monkeypatch):
    fetch = AsyncMock(return_value={"data": []})
    monkeypatch.setattr(gleif, "fetch_json", fetch)
    assert asyncio.run(gleif.search("Anthropic", registration_number="ABC-123")) == []
    fetch.assert_awaited_once_with(gleif.SEARCH_URL,
        params={"filter[fulltext]": "Anthropic", "page[size]": "8"}, ttl_hours=24)


def test_failed_exact_lookup_is_not_reported_as_success(monkeypatch):
    monkeypatch.setattr(gleif, "fetch_json", AsyncMock(return_value=None))
    with pytest.raises(RuntimeError, match="unavailable"):
        asyncio.run(gleif.search("Anthropic", registration_number=LEI))
