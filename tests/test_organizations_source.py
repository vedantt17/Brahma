"""Wikidata organization profiles are public relationship leads, not registry IDs."""

import asyncio
from unittest.mock import AsyncMock

from app.sources import organizations


def claim(value, *, qualifiers=None):
    return {"mainsnak": {"snaktype": "value", "datavalue": {"value": value}},
            "qualifiers": qualifiers or {}}


def test_public_profile_extracts_sourced_ceo_and_ignores_product_hits(monkeypatch):
    profile = {"labels": {"en": {"value": "Example AI"}},
               "descriptions": {"en": {"value": "Artificial intelligence company"}},
               "claims": {"P31": [claim({"id": "Q43229"})],
                          "P856": [claim("https://example.ai/")],
                          "P17": [claim({"id": "Q30"})],
                          "P169": [claim({"id": "Q1"}),
                                   claim({"id": "Q2"}, qualifiers={"P582": [{"datavalue": {
                                       "value": {"time": "+2020-01-01T00:00:00Z"}}}]})],
                          "P112": [claim({"id": "Q1"})]}}
    product = {"labels": {"en": {"value": "Example AI ETF"}},
               "claims": {"P31": [claim({"id": "Q43229"})]}}
    labels = {"Q30": {"labels": {"en": {"value": "United States"}},
                       "claims": {"P297": [claim("US")]}},
              "Q1": {"labels": {"en": {"value": "Example Executive"}}},
              "Q2": {"labels": {"en": {"value": "Former Executive"}}}}
    fetch = AsyncMock(side_effect=[
        {"search": [{"id": "Q100"}, {"id": "Q200"}]},
        {"entities": {"Q100": profile, "Q200": product}},
        {"entities": labels},
    ])
    monkeypatch.setattr(organizations, "fetch_json", fetch)
    records = asyncio.run(organizations.search("Example AI"))
    assert len(records) == 1
    record = records[0]
    assert record.source_id == "Q100" and record.website == "https://example.ai/"
    assert record.country == "US" and record.raw["public_profile"] is True
    assert record.raw["officers"][0]["name"] == "Example Executive"
    assert record.raw["officers"][0]["role"] == "Chief executive officer"
    assert record.raw["officers"][0]["source_url"].endswith("#P169")
    assert record.raw["officers"][1]["role"] == "Former chief executive officer"
    assert fetch.await_count == 3
