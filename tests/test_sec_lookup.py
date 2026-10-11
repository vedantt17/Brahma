import asyncio
from unittest.mock import AsyncMock

from app.sources import sec


def test_cik_lookup_uses_padded_identifier_and_defers_insider_enrichment(monkeypatch):
    fetch = AsyncMock(return_value={"name": "Example Technologies Inc.", "cik": 12})
    insider = AsyncMock(return_value=([], []))
    names = AsyncMock()
    monkeypatch.setattr(sec, "fetch_json", fetch)
    monkeypatch.setattr(sec, "_insiders", insider)
    monkeypatch.setattr(sec, "_find_ciks", names)
    records = asyncio.run(sec.search("Example Technologies", registration_number="CIK:12"))
    assert records[0].name == "Example Technologies Inc."
    fetch.assert_awaited_once_with(sec.SUBMISSIONS_URL.format(cik="0000000012"), ttl_hours=24)
    insider.assert_not_called()
    names.assert_not_called()
    asyncio.run(sec.enrich(records[0]))
    insider.assert_awaited_once()
