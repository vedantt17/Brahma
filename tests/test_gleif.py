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
    assert fetch.await_count == 2
    assert fetch.await_args_list[0].kwargs["params"] == {
        "filter[entity.legalName]": "Anthropic", "page[size]": "50", "page[number]": "1"}
    assert fetch.await_args_list[1].kwargs["params"]["filter[fulltext]"] == "Anthropic"


def test_failed_exact_lookup_is_not_reported_as_success(monkeypatch):
    monkeypatch.setattr(gleif, "fetch_json", AsyncMock(return_value=None))
    with pytest.raises(RuntimeError, match="unavailable"):
        asyncio.run(gleif.search("Anthropic", registration_number=LEI))


def node(identifier, name, aliases=None):
    return {"id": identifier, "attributes": {"lei": identifier, "entity": {
        "legalName": {"name": name}, "otherNames": aliases or []}}}


def test_candidates_are_not_limited_to_first_eight_and_do_not_fetch_parents(monkeypatch):
    rows = [node(f"fund{n}", f"Leveraged Brand ETF {n}") for n in range(10)]
    rows.append(node("brand", "Brand Opco LLC"))
    fetch = AsyncMock(side_effect=[{"data": rows}, {"data": []}])
    relation = AsyncMock(return_value=None)
    monkeypatch.setattr(gleif, "fetch_json", fetch)
    monkeypatch.setattr(gleif, "_relation", relation)
    records = asyncio.run(gleif.search("Brand"))
    assert len(records) == 11
    assert records[-1].name == "Brand Opco LLC"
    relation.assert_not_awaited()


def test_bounded_pagination_and_alias_candidates_are_deduplicated(monkeypatch):
    fetch = AsyncMock(side_effect=[
        {"data": [node("first", "Brand Fund")], "links": {"next": "ignored-untrusted-url"}},
        {"data": [node("second", "Brand LLC")]},
        {"data": [node("second", "Brand LLC"), node("alias", "Different Legal LLC",
                    [{"name": "Brand", "type": "TRADING_OR_OPERATING_NAME"}])]},
    ])
    monkeypatch.setattr(gleif, "fetch_json", fetch)
    records = asyncio.run(gleif.search("Brand"))
    assert [record.source_id for record in records] == ["first", "second", "alias"]
    assert records[-1].aliases == ["Brand"]
    assert fetch.await_args_list[1].kwargs["params"]["page[number]"] == "2"
    assert all(call.args[0] == gleif.SEARCH_URL for call in fetch.await_args_list)


def test_pagination_never_exceeds_two_legal_pages_and_one_alias_page(monkeypatch):
    fetch = AsyncMock(return_value={"data": [node("brand", "Brand LLC")],
                                  "links": {"next": "more"}})
    monkeypatch.setattr(gleif, "fetch_json", fetch)
    records = asyncio.run(gleif.search("Brand", limit=10000))
    assert fetch.await_count == 3
    assert records.search_metadata["truncated"] is True
    assert len(records) == 1


def test_enrichment_only_fetches_selected_registry_record(monkeypatch):
    relation = AsyncMock(side_effect=[{"name": "Parent", "lei": "parent"}, None])
    monkeypatch.setattr(gleif, "_relation", relation)
    record = gleif.EntityRecord(source="GLEIF", source_id=LEI, name="Brand")
    assert asyncio.run(gleif.enrich(record)) is record
    assert record.raw["parents"] == [{"name": "Parent", "lei": "parent"}]
    assert {call.args[0] for call in relation.await_args_list} == {LEI}


def test_failed_alias_pass_preserves_valid_legal_candidates(monkeypatch):
    monkeypatch.setattr(gleif, "fetch_json", AsyncMock(side_effect=[{"data": [RECORD]}, None]))
    records = asyncio.run(gleif.search("Anthropic"))
    assert records[0].source_id == LEI
    assert records.search_metadata["alias_search_available"] is False
