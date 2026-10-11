"""Search document hits are not a total count of lawsuits."""
import asyncio

from app.sources import courtlistener


def test_deduplicates_documents_and_reports_capped_search_metadata(monkeypatch):
    async def fetch(*args, **kwargs):
        return {"count": 50, "next": "next-page", "results": [
            {"id": 11, "docket_id": 101, "caseName": "Writers v. Anthropic, PBC"},
            {"id": 12, "docket_id": 101, "caseName": "Writers v. Anthropic, PBC"},
            {"id": 13, "docket_id": 102, "caseName": "Authors v. Anthropic"},
        ]}
    monkeypatch.setattr(courtlistener, "fetch_json", fetch)
    output = asyncio.run(courtlistener.search("Anthropic, PBC"))
    assert len(output["cases"]) == output["returned_count"] == 2
    assert output["source_result_count"] == 50
    assert output["truncated"]
    assert output["cases"][0]["url"].endswith("/101/")


def test_relevance_requires_all_name_tokens_in_title_and_never_uses_document_id(monkeypatch):
    async def fetch(*args, **kwargs):
        return {"results": [
            {"id": 42, "caseName": "Acme v. Other", "suitNature": "Blue River"},
            {"id": 43, "caseName": "Blue v. Other"},
            {"id": 44, "caseName": "Blue River v. Other", "court": "test", "docketNumber": "1"},
        ]}
    monkeypatch.setattr(courtlistener, "fetch_json", fetch)
    output = asyncio.run(courtlistener.search("Blue River Ltd"))
    assert [c["case"] for c in output["cases"]] == ["Blue River v. Other"]
    assert output["cases"][0]["url"] is None


def test_unidentified_hits_are_excluded_from_docket_count(monkeypatch):
    async def fetch(*args, **kwargs):
        return {"count": 9, "results": [{"id": 44, "caseName": "Anthropic v. Other"}]}
    monkeypatch.setattr(courtlistener, "fetch_json", fetch)
    output = asyncio.run(courtlistener.search("Anthropic"))
    assert output["returned_count"] == 0
    assert output["unidentified_rejected_count"] == 1
    assert output["truncated"]
    assert "limited search" in output["note"]
