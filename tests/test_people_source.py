import asyncio
from unittest.mock import AsyncMock

import pytest

from app.sources import people


def claim(value, *, rank="normal", qualifiers=None):
    return {"rank": rank, "mainsnak": {"snaktype": "value", "datavalue": {"value": value}},
            "qualifiers": qualifiers or {}}


def entity(name, *, human=True, employers=None):
    return {"labels": {"en": {"value": name}},
            "aliases": {"en": [{"value": "Public alias"}]},
            "descriptions": {"en": {"value": "Public profile description"}},
            "claims": {"P31": [claim({"id": "Q5" if human else "Q43229"})],
                       "P108": employers or [], "P106": [claim({"id": "Q3"})],
                       "P27": [claim({"id": "Q4"})],
                       "P569": [claim({"time": "+1985-04-22T00:00:00Z", "precision": 11})]}}


def related():
    return {"entities": {"Q2": {"labels": {"en": {"value": "Example Employer"}}},
                         "Q3": {"labels": {"en": {"value": "Entrepreneur"}}},
                         "Q4": {"labels": {"en": {"value": "United States"}},
                                "claims": {"P297": [claim("US")]}}}}


def test_search_returns_humans_and_structured_public_profile_facts(monkeypatch):
    human = entity("Sam Example", employers=[claim({"id": "Q2"})])
    fetch = AsyncMock(side_effect=[{"search": [{"id": "Q1"}, {"id": "Q9"}]},
        {"entities": {"Q1": human, "Q9": entity("Sam Example LLC", human=False)}}, related()])
    monkeypatch.setattr(people, "fetch_json", fetch)
    records = asyncio.run(people.search("Sam Example"))
    assert len(records) == 1
    record = records[0]
    assert record.source == "Wikidata" and record.source_id == "Q1"
    assert record.aliases == ["Public alias"]
    assert record.raw["entity_type"] == "individual"
    assert record.raw["date_of_birth"] == "1985-04-22"
    assert record.raw["employers"][0]["name"] == "Example Employer"
    assert record.raw["employers"][0]["current_status"] == "current_status_unverified"
    assert record.raw["employers"][0]["source_url"].endswith("#P108")
    assert record.raw["occupations"][0]["name"] == "Entrepreneur"
    assert record.country == "US" and record.raw["country_basis"] == "citizenship"
    assert fetch.await_count == 3
    assert all(call.args[0] == people.API for call in fetch.await_args_list)


def test_selected_qid_uses_exact_batch_endpoint_and_still_requires_human(monkeypatch):
    fetch = AsyncMock(return_value={"entities": {"Q9": entity("Company", human=False)}})
    monkeypatch.setattr(people, "fetch_json", fetch)
    records = asyncio.run(people.search("Company", profile_identifier=" q9 "))
    assert records == []
    assert records.search_metadata["profile_identifier"] == "Q9"
    assert fetch.await_count == 1
    assert fetch.await_args.kwargs["params"]["action"] == "wbgetentities"


def test_invalid_profile_identifier_never_becomes_network_target(monkeypatch):
    fetch = AsyncMock()
    monkeypatch.setattr(people, "fetch_json", fetch)
    with pytest.raises(ValueError):
        asyncio.run(people.search("Someone", profile_identifier="https://private.example/"))
    fetch.assert_not_awaited()


def test_namesakes_and_search_limit_remain_explicit(monkeypatch):
    fetch = AsyncMock(side_effect=[{"search": [{"id": "Q1"}, {"id": "Q2"}], "search-continue": 20},
        {"entities": {"Q1": entity("Alex Example"), "Q2": entity("Alex Example")}}, related()])
    monkeypatch.setattr(people, "fetch_json", fetch)
    records = asyncio.run(people.search("Alex Example", limit=999))
    assert len(records) == 2
    assert records.search_metadata["truncated"] is True
    assert fetch.await_args_list[0].kwargs["params"]["limit"] == "20"


def test_former_employers_and_deprecated_claims_are_not_current_employment(monkeypatch):
    qualifiers = {"P582": [{"datavalue": {"value": {"time": "+2019-01-01T00:00:00Z"}}}]}
    human = entity("Public Person", employers=[claim({"id": "Q2"}, qualifiers=qualifiers),
                                             claim({"id": "Q8"}, rank="deprecated")])
    fetch = AsyncMock(side_effect=[{"entities": {"Q1": human}}, related()])
    monkeypatch.setattr(people, "fetch_json", fetch)
    record = asyncio.run(people.search("Public Person", profile_identifier="Q1"))[0]
    assert len(record.raw["employers"]) == 1
    assert record.raw["employers"][0]["end_date"] == "2019-01-01"
    assert record.raw["employers"][0]["current_status"] == "end_date_recorded"


def test_imprecise_birth_dates_are_not_invented_exact_dates(monkeypatch):
    human = entity("Public Person")
    human["claims"]["P569"] = [claim({"time": "+1985-00-00T00:00:00Z", "precision": 9})]
    monkeypatch.setattr(people, "fetch_json", AsyncMock(side_effect=[{"entities": {"Q1": human}}, related()]))
    assert asyncio.run(people.search("Person", profile_identifier="Q1"))[0].raw["date_of_birth"] is None


def test_failed_api_does_not_report_zero_matching_people(monkeypatch):
    monkeypatch.setattr(people, "fetch_json", AsyncMock(return_value=None))
    with pytest.raises(RuntimeError, match="unavailable"):
        asyncio.run(people.search("Person"))
