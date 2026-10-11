"""Requests and returned media must use the DOC API's recent index window."""
import asyncio
from unittest.mock import AsyncMock

import pytest

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


@pytest.mark.parametrize("name", ["Anthropic, PBC", "Anthropic P.B.C.", "Anthropic, PBC, Inc."])
def test_legal_names_search_the_brand_phrase(name):
    assert gdelt._build_query(name) == gdelt._build_query("Anthropic")


@pytest.mark.parametrize("name, expected", [
    ("Acme Holdings Inc.", "Acme Holdings"),
    ("Apple Hospitality LLC", "Apple Hospitality"),
    ("International Business Machines Corp.", "International Business Machines"),
    ("The PBC", "The"),
])
def test_search_preserves_business_identity_words(name, expected):
    assert gdelt.search_name(name) == expected


def test_query_cannot_be_broken_out_of_quoted_subject():
    query = gdelt._build_query('Acme" OR "unrelated\\\n')
    assert query.startswith('"Acme OR unrelated" (')


def test_empty_subject_rejected_before_fetch(monkeypatch):
    fetch = AsyncMock()
    monkeypatch.setattr(gdelt, "fetch_json", fetch)
    with pytest.raises(ValueError):
        asyncio.run(gdelt.search('"\\'))
    fetch.assert_not_called()


def test_brand_headline_matches_legal_name_without_accepting_other_entity(monkeypatch):
    fetch = AsyncMock(return_value={"articles": [
        {"title": "Anthropic faces copyright lawsuit", "url": "https://example.com/1"},
        {"title": "Anthropic faces copyright lawsuit", "url": "https://example.com/duplicate"},
        {"title": "Other AI company faces lawsuit", "url": "https://example.com/2"},
        {"title": "Anthropic launches new product", "url": "https://example.com/3"},
    ]})
    monkeypatch.setattr(gdelt, "fetch_json", fetch)
    results = asyncio.run(gdelt.search("Anthropic, PBC"))
    assert [article["title"] for article in results] == ["Anthropic faces copyright lawsuit"]
    assert results.search_metadata["search_name"] == "Anthropic"
    assert results.search_metadata["raw_count"] == 4
    assert results.search_metadata["matched_count"] == 1
    assert results.search_metadata["returned_count"] == 1
    assert results.search_metadata["result_limit_reached"] is False


def test_provider_failure_remains_unavailable_not_zero_matches(monkeypatch):
    monkeypatch.setattr(gdelt, "fetch_json", AsyncMock(return_value=None))
    with pytest.raises(RuntimeError, match="unavailable"):
        asyncio.run(gdelt.search("Anthropic, PBC"))


def test_search_caps_are_reported(monkeypatch):
    articles = [{"title": f"Anthropic lawsuit number {n}"} for n in range(45)]
    monkeypatch.setattr(gdelt, "fetch_json", AsyncMock(return_value={"articles": articles}))
    results = asyncio.run(gdelt.search("Anthropic", max_records=45))
    assert len(results) == 40
    assert results.search_metadata["matched_count"] == 45
    assert results.search_metadata["result_limit_reached"] is True
