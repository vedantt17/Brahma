"""Offline API contracts, with the real lifespan and an isolated SQLite DB."""

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from app import db, main, pipeline
from app.agent import investigator
from app.api import v1
from app.config import settings
from app.resolution import embeddings
from app.schemas import InvestigationResponse
from app.sources import ofac
from app.strategy import board


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    from app.sources import news_rss
    monkeypatch.setattr(news_rss, "fetch", AsyncMock(return_value=None))
    async def forbidden(*args, **kwargs):
        pytest.fail("External HTTP is forbidden in offline API tests")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)
    for key in ("anthropic_api_key", "openai_api_key", "openrouter_api_key",
                "courtlistener_api_token"):
        monkeypatch.setattr(settings, key, None)
    monkeypatch.setattr(settings, "embedding_backend", "hashed")
    monkeypatch.setattr(embeddings, "_backend", "hashed")
    monkeypatch.setattr(investigator, "_client", None)
    monkeypatch.setattr(board, "_get_client", lambda: None)


@pytest.fixture
def api(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "database_url",
                        f"sqlite+aiosqlite:///{(tmp_path / 'api.db').as_posix()}")
    monkeypatch.setattr(settings, "allow_sqlite_fallback", False)
    monkeypatch.setattr(ofac, "_entries", [])
    monkeypatch.setattr(ofac, "_loaded", False)
    monkeypatch.setattr(ofac, "ingest", AsyncMock(return_value=0))
    with asyncio.Runner() as runner:
        lifespan = main.app.router.lifespan_context(main.app)
        runner.run(asyncio.wait_for(lifespan.__aenter__(), timeout=30))
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app), base_url="http://test"
        )
        try:
            yield lambda method, path, **kw: runner.run(
                asyncio.wait_for(client.request(method, path, **kw), timeout=30)
            )
        finally:
            runner.run(client.aclose())
            runner.run(asyncio.wait_for(lifespan.__aexit__(None, None, None), timeout=10))
        assert db.ACTIVE_BACKEND == "uninitialized"
        assert db._sessionmaker is None


def test_startup_root_static_openapi_and_health(api):
    root = api("GET", "/")
    assert root.status_code == 200
    assert "text/html" in root.headers["content-type"]
    assert "no-cache" in root.headers["cache-control"]
    asset = api("GET", "/static/mcp_server.py")
    assert asset.status_code == 200 and 'FastMCP("Brahma")' in asset.text
    assert api("GET", "/static/missing-brahma-file").status_code == 404
    schema = api("GET", "/openapi.json").json()
    assert schema["info"]["title"] == "Brahma API"
    assert "/api/v1/supplier/investigate" in schema["paths"]
    health = api("GET", "/api/v1/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "database": "sqlite",
                             "embedding_backend": "hashed", "ofac_names_indexed": 0,
                             "investigations_stored": 0}


def test_root_without_static_index(api, monkeypatch, tmp_path):
    monkeypatch.setattr(main, "STATIC_DIR", tmp_path)
    assert api("GET", "/").json() == {"service": "Brahma API", "docs": "/docs"}


def test_health_database_failure_is_503_without_sensitive_details(api, monkeypatch):
    def broken():
        raise RuntimeError("secret-database-password")
    monkeypatch.setattr(db, "session_factory", broken)
    response = api("GET", "/api/v1/health")
    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert response.json()["investigations_stored"] is None
    assert "secret-database-password" not in response.text


def test_demo_subjects_are_schema_valid_and_explicitly_synthetic(api):
    subjects = api("GET", "/api/v1/demo/subjects").json()["subjects"]
    assert subjects
    assert len({subject["id"] for subject in subjects}) == len(subjects)
    # Exercise both hand-authored and generated fixtures with the real scorer.
    for subject in (subjects[0], subjects[-1]):
        response = api("GET", f"/api/v1/demo/investigate/{subject['id']}")
        assert response.status_code == 200
        data = response.json()
        InvestigationResponse.model_validate(data)
        assert data["demo"] is True
        assert "demo dataset" in data["agent_summary"]["generated_by"]
        assert data["investigation_id"] is None
        assert 0 <= data["risk"]["score"] <= 100
    assert api("GET", "/api/v1/demo/investigate/not-a-subject").status_code == 404
    assert api("GET", "/api/v1/investigations").json()["count"] == 0


def test_strategy_sample_workflows_and_keyless_notice(api):
    samples = api("GET", "/api/v1/strategy/samples").json()["samples"]
    assert samples
    for sample in samples:
        response = api("GET", f"/api/v1/strategy/sample/{sample['id']}")
        assert response.status_code == 200
        data = response.json()
        assert data["verdict"]["decision"] in board.DECISIONS
        assert len(data["seats"]) == 5
        assert len(data["board_vote"]) == 4
        decision = api("POST", "/api/v1/strategy/decide", json={"question": sample["question"]})
        assert decision.status_code == 200
        assert decision.json()["sample"] is True
        assert decision.json()["question"] == sample["question"]
    assert api("GET", "/api/v1/strategy/sample/missing").status_code == 404
    notice = api("POST", "/api/v1/strategy/decide", json={"question": "Should Acme buy Globex?"}).json()
    assert notice["available"] is False and notice["generated_by"] == "unavailable"


@pytest.mark.parametrize("path,payload", [
    ("supplier/investigate", {"name": "  "}),
    ("supplier/investigate", {"name": "x"}),
    ("supplier/investigate", {"name": "Acme", "entity_type": "invalid"}),
    ("supplier/investigate", {"name": "x" * 401}),
    ("strategy/decide", {"question": "      "}),
    ("strategy/decide", {"question": "x" * 401}),
])
def test_invalid_requests_fail_before_pipeline(api, path, payload):
    assert api("POST", f"/api/v1/{path}", json=payload).status_code == 422


def test_live_pipeline_offline_failures_do_not_become_verified(api, monkeypatch):
    for source in (pipeline.sec, pipeline.gleif, pipeline.gdelt):
        monkeypatch.setattr(source, "fetch_json", AsyncMock(return_value=None))
    monkeypatch.setattr(pipeline.sec, "_ticker_cache", None)
    monkeypatch.setattr(pipeline.courtlistener, "search", AsyncMock(return_value={
        "available": False, "cases": [], "note": "offline fixture"}))
    monkeypatch.setattr(ofac, "screen", AsyncMock(return_value={
        "match": False, "confidence": 0.0, "matched_entity": None,
        "source": "OFAC", "list_size": 0}))
    response = api("POST", "/api/v1/supplier/investigate", json={
        "name": " Unverified Fixture Ltd ", "website": "http://169.254.169.254/latest/meta-data/"})
    assert response.status_code == 200
    result = response.json()
    InvestigationResponse.model_validate(result)
    assert result["query"]["name"] == "Unverified Fixture Ltd"
    assert not any(result["sources_consulted"].values())
    assert result["supplier"]["verified"] is False
    assert result["supplier"]["status"] == "unverified"
    assert result["sanctions"]["list_size"] == 0
    assert "unavailable" in result["agent_summary"]["sanctions_assessment"]
    assert "unavailable" in result["agent_summary"]["adverse_media_assessment"]
    assert "no match" not in result["evidence"][0]["description"]
    assert result["investigation_id"] is not None
    stored = api("GET", f"/api/v1/investigations/{result['investigation_id']}")
    assert stored.json() == result
    assert api("GET", "/api/v1/investigations").json()["count"] == 1
    assert api("GET", f"/api/v1/crew/trace/{result['investigation_id']}").status_code == 200
    monkeypatch.setattr(pipeline, "generate_report", AsyncMock(return_value={
        "recommendation": "Standard onboarding may proceed."}))
    guarded = api("POST", "/api/v1/supplier/investigate", json={"name": "LLM Fixture"}).json()
    assert guarded["risk"]["coverage_assessment"]["complete"] is False
    assert guarded["agent_summary"]["recommendation"] == guarded["agent_summary"]["rule_based_recommendation"]
    assert "Standard onboarding may proceed" not in guarded["agent_summary"]["recommendation"]


@pytest.mark.parametrize("headlines", [[], [{"title": "Anthropic faces copyright lawsuit", "url": "https://example.com/news"}]])
def test_legal_name_search_metadata_survives_api_and_storage(api, monkeypatch, headlines):
    from app.resolution.engine import EntityRecord

    monkeypatch.setattr(pipeline.sec, "search", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline.gleif, "search", AsyncMock(return_value=[
        EntityRecord(source="GLEIF", name="ANTHROPIC, PBC", country="US",
                     raw={"lei": "984500B6DEB8CEBC4Z70"})]))
    fetch = AsyncMock(return_value={"articles": headlines})
    monkeypatch.setattr(pipeline.gdelt, "fetch_json", fetch)
    monkeypatch.setattr(pipeline.courtlistener, "search", AsyncMock(return_value={
        "available": True, "cases": [], "note": None}))
    monkeypatch.setattr(ofac, "screen", AsyncMock(return_value={
        "match": False, "list_size": 100, "source": "OFAC"}))
    response = api("POST", "/api/v1/supplier/investigate", json={
        "name": "Anthropic, PBC", "registration_number": "984500B6DEB8CEBC4Z70"})
    assert response.status_code == 200
    result = response.json()
    assert fetch.call_args.kwargs["params"]["query"].startswith('"Anthropic" (')
    assert result["media_summary"]["available"] is True
    assert result["media_summary"]["search_metadata"]["raw_count"] == len(headlines)
    assert result["media_summary"]["search_metadata"]["search_name"] == "Anthropic"
    assert len(result["adverse_media"]) == len(headlines)
    assert api("GET", f"/api/v1/investigations/{result['investigation_id']}").json() == result


def test_rejected_registry_lookalike_does_not_replace_requested_subject(api, monkeypatch):
    from app.resolution.engine import EntityRecord

    monkeypatch.setattr(pipeline.sec, "search", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline.gleif, "search", AsyncMock(return_value=[
        EntityRecord(source="GLEIF", name="Anthropic AI Lab Ecosystem ETF",
                     raw={"lei": "LOOKALIKE"})]))
    monkeypatch.setattr(pipeline.gdelt, "search", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline.courtlistener, "search", AsyncMock(return_value={
        "available": True, "cases": [], "note": None}))
    monkeypatch.setattr(ofac, "screen", AsyncMock(return_value={"match": False, "list_size": 100}))
    response = api("POST", "/api/v1/supplier/investigate", json={"name": "Anthropic"})
    result = response.json()
    assert response.status_code == 200
    assert result["supplier"]["name"] == "Anthropic"
    assert result["supplier"]["verified"] is False
    assert result["supplier"]["lei"] is None
    assert result["entity_resolution"]["selected"] is None


def test_live_api_uses_rss_fallback_as_news_coverage_with_correct_provenance(api, monkeypatch):
    from app.sources import news_rss
    from datetime import datetime, timezone
    from email.utils import format_datetime

    monkeypatch.setattr(pipeline.sec, "search", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline.gleif, "search", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline.gdelt, "search", AsyncMock(side_effect=RuntimeError("503")))
    feed = ('<rss><channel><item><title>Anthropic faces copyright lawsuit</title>'
            '<link>https://news.google.com/rss/articles/test</link><pubDate>'
            + format_datetime(datetime.now(timezone.utc))
            + '</pubDate><source>Example News</source></item></channel></rss>')
    monkeypatch.setattr(news_rss, "fetch", AsyncMock(return_value=feed))
    monkeypatch.setattr(pipeline.courtlistener, "search", AsyncMock(return_value={
        "available": True, "cases": [], "note": None}))
    monkeypatch.setattr(ofac, "screen", AsyncMock(return_value={"match": False, "list_size": 100}))
    response = api("POST", "/api/v1/supplier/investigate", json={"name": "Anthropic"})
    assert response.status_code == 200
    result = response.json()
    assert result["sources_consulted"]["gdelt"] is False
    assert result["sources_consulted"]["google_news"] is True
    assert result["media_summary"]["available"] is True
    assert result["media_summary"]["total"] == 1
    assert result["risk"]["coverage_assessment"]["complete"] is True
    assert any(e["source"] == "Google News RSS" for e in result["evidence"])
    assert "unavailable" not in result["agent_summary"]["adverse_media_assessment"]
    assert "[E" in result["agent_summary"]["adverse_media_assessment"]
    assert api("GET", f"/api/v1/investigations/{result['investigation_id']}").json() == result


def test_generic_ambiguity_requires_choice_even_with_complete_source_coverage(api, monkeypatch):
    from app.resolution.engine import EntityRecord
    from app.sources.gdelt import MediaResults
    ids = ["A" * 18 + "01", "B" * 18 + "02"]
    records = [EntityRecord(source="GLEIF", source_id=identifier, name="Example Labs LLC",
                            country=country, raw={"lei": identifier})
               for identifier, country in zip(ids, ["US", "GB"])]
    monkeypatch.setattr(pipeline.sec, "search", AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline.gleif, "search", AsyncMock(return_value=records))
    enrichment = AsyncMock()
    monkeypatch.setattr(pipeline.gleif, "enrich", enrichment)
    monkeypatch.setattr(pipeline.news, "search", AsyncMock(return_value=MediaResults([], {
        "providers": {"gdelt": True}, "raw_count": 0})))
    monkeypatch.setattr(pipeline.courtlistener, "search", AsyncMock(return_value={
        "available": True, "cases": []}))
    monkeypatch.setattr(ofac, "screen", AsyncMock(return_value={"match": False, "list_size": 100}))
    monkeypatch.setattr(pipeline, "generate_report", AsyncMock(return_value={
        "recommendation": "Standard onboarding may proceed."}))
    result = api("POST", "/api/v1/supplier/investigate", json={"name": "Example Labs"}).json()
    assert result["supplier"]["name"] == "Example Labs"
    assert result["supplier"]["verified"] is False
    assert result["entity_resolution"]["selection"]["status"] == "ambiguous"
    assert len(result["entity_resolution"]["selection"]["candidates"]) == 2
    assert result["risk"]["coverage_assessment"]["complete"] is True
    assert "Confirm the legal entity" in result["agent_summary"]["recommendation"]
    enrichment.assert_not_called()
    selected = api("POST", "/api/v1/supplier/investigate", json={
        "name": "Example Labs LLC", "registration_number": ids[0]}).json()
    assert selected["entity_resolution"]["selection"]["status"] == "selected"
    assert selected["supplier"]["lei"] == ids[0]
    assert selected["supplier"]["verified"] is True
    enrichment.assert_awaited_once_with(records[0])
    assert api("GET", f"/api/v1/investigations/{selected['investigation_id']}").json() == selected


def test_error_and_not_found_contracts(api, monkeypatch):
    monkeypatch.setattr(v1, "investigate", AsyncMock(side_effect=RuntimeError("private-token")))
    failed = api("POST", "/api/v1/supplier/investigate", json={"name": "Acme"})
    assert failed.status_code == 500
    assert failed.json() == {"detail": "investigation failed"}
    for path in ("investigations/999", "crew/trace/999"):
        assert api("GET", f"/api/v1/{path}").status_code == 404
    assert api("GET", "/api/v1/investigations?limit=0").status_code == 422
    assert api("GET", "/api/v1/risk-categories").json()["categories"]
    assert len(api("GET", "/api/v1/crew/roster").json()["agents"]) == 10


def test_forced_ofac_refresh_failure_is_not_success(api, monkeypatch):
    monkeypatch.setattr(ofac, "ingest", AsyncMock(side_effect=RuntimeError("offline")))
    response = api("POST", "/api/v1/admin/ofac/refresh")
    assert response.status_code == 503
    assert response.json() == {"detail": "OFAC refresh failed"}
    monkeypatch.setattr(ofac, "ingest", AsyncMock(return_value=12))
    assert api("POST", "/api/v1/admin/ofac/refresh").json() == {"indexed_names": 12}


def test_lifespan_waits_for_background_cancellation_on_exception(monkeypatch):
    events = []
    async def warm():
        try:
            await asyncio.Event().wait()
        finally:
            events.append("cancelled")
    async def close_http():
        events.append("http")
    async def close_db():
        events.append("database")
    monkeypatch.setattr(main, "init_db", AsyncMock())
    monkeypatch.setattr(main, "_warm_ofac", warm)
    monkeypatch.setattr(main, "close_client", close_http)
    monkeypatch.setattr(main, "close_db", close_db)
    async def exercise():
        with pytest.raises(RuntimeError, match="exercise"):
            async with main.lifespan(main.app):
                await asyncio.sleep(0)
                raise RuntimeError("exercise")
    asyncio.run(exercise())
    assert events == ["cancelled", "http", "database"]
