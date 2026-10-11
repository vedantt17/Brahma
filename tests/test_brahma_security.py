"""Offline source integrity, cancellation, and MCP compatibility regressions."""

import asyncio
import copy
import runpy
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from app import pipeline
from app.agent import investigator
from app.config import settings
from app.resolution import embeddings
from app.risk.engine import evaluate, recommendation
from app.sources import courtlistener, gdelt, gleif, ofac, sec
from app.strategy import board, samples


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch):
    async def forbidden(*args, **kwargs):
        pytest.fail("External network is forbidden in security regressions")
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)
    for key in ("anthropic_api_key", "openrouter_api_key", "openai_api_key",
                "courtlistener_api_token"):
        monkeypatch.setattr(settings, key, None)
    monkeypatch.setattr(embeddings, "_backend", "hashed")
    monkeypatch.setattr(investigator, "_client", None)
    monkeypatch.setattr(board, "_get_client", lambda: None)


@pytest.mark.parametrize("source", [gleif, gdelt])
@pytest.mark.parametrize("body", [None, {}, {"error": "unavailable"}, []])
def test_source_failure_is_not_a_successful_empty_search(monkeypatch, source, body):
    monkeypatch.setattr(source, "fetch_json", AsyncMock(return_value=body))
    name, result, ok = asyncio.run(pipeline._safe("source", source.search("Acme"), []))
    assert (name, result, ok) == ("source", [], False)


@pytest.mark.parametrize("source,body", [(gleif, {"data": []}), (gdelt, {"articles": []})])
def test_valid_empty_source_response_is_success(monkeypatch, source, body):
    monkeypatch.setattr(source, "fetch_json", AsyncMock(return_value=body))
    assert asyncio.run(pipeline._safe("source", source.search("Acme"), [])) == ("source", [], True)


def test_sec_recovers_after_failed_ticker_download(monkeypatch):
    monkeypatch.setattr(sec, "_ticker_cache", None)
    fetch = AsyncMock(side_effect=[None, {"0": {"title": "Acme Corp", "cik_str": 42, "ticker": "ACME"}}])
    monkeypatch.setattr(sec, "fetch_json", fetch)
    async def exercise():
        with pytest.raises(RuntimeError, match="unavailable"):
            await sec._load_tickers()
        assert sec._ticker_cache is None
        assert (await sec._load_tickers())[0]["cik"] == "0000000042"
    asyncio.run(exercise())
    assert fetch.await_count == 2


def test_sec_failed_submissions_are_not_a_clean_lookup(monkeypatch):
    monkeypatch.setattr(sec, "_find_ciks", AsyncMock(return_value=[{"cik": "42"}]))
    monkeypatch.setattr(sec, "_submission", AsyncMock(return_value=None))
    assert asyncio.run(pipeline._safe("sec", sec.search("Acme"), []))[2] is False


def test_courtlistener_error_object_is_unavailable(monkeypatch):
    monkeypatch.setattr(courtlistener, "fetch_json", AsyncMock(return_value={"detail": "rate limited"}))
    assert asyncio.run(courtlistener.search("Acme"))["available"] is False


@pytest.mark.parametrize("source,body", [(gleif, {"data": []}), (gdelt, {"articles": []}),
                                         (courtlistener, {"results": []})])
def test_user_input_stays_in_query_parameters_not_request_destination(monkeypatch, source, body):
    fetch = AsyncMock(return_value=body)
    monkeypatch.setattr(source, "fetch_json", fetch)
    asyncio.run(source.search("http://127.0.0.1:8000/admin?secret=x"))
    url = fetch.call_args.args[0]
    assert url in {gleif.SEARCH_URL, gdelt.DOC_API, courtlistener.SEARCH_URL}
    assert "127.0.0.1" not in url


def test_invalid_ofac_download_preserves_existing_index(monkeypatch):
    existing = [{"name": "Cached Fixture"}]
    monkeypatch.setattr(ofac, "_entries", existing)
    monkeypatch.setattr(ofac, "_download", AsyncMock(return_value="<html>upstream failure</html>" * 100))
    monkeypatch.setattr(ofac, "_load_index", AsyncMock())
    def unexpected_storage():
        pytest.fail("Invalid download must not replace the sanctions database")
    monkeypatch.setattr(ofac, "session_factory", unexpected_storage)
    with pytest.raises(RuntimeError, match="invalid"):
        asyncio.run(ofac._ingest_locked(force=True))
    assert ofac._entries is existing


def test_forced_ofac_download_bypasses_http_cache(monkeypatch):
    fetch = AsyncMock(return_value="fixture" * 200)
    monkeypatch.setattr(ofac, "fetch", fetch)
    asyncio.run(ofac._download(ofac.SDN_URLS, force=True))
    assert fetch.call_args.kwargs["use_cache"] is False


def test_ofac_parser_accepts_real_csv_shape_not_error_text():
    rows = ofac._parse_sdn('123,"Fixture Name",individual,TEST,-0-,-0-,-0-,-0-,-0-,-0-,-0-,"DOB 1980"')
    assert rows[0]["name"] == "Fixture Name"
    assert ofac._parse_sdn("error,name,type,program") == []


def test_pipeline_timeout_awaits_source_cleanup(monkeypatch):
    finished = []
    async def stalled(*args):
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            finished.append(True)
    for source in (sec, gleif, gdelt, courtlistener):
        monkeypatch.setattr(source, "search", stalled)
    monkeypatch.setattr(ofac, "screen", stalled)
    monkeypatch.setattr(settings, "investigation_timeout_seconds", 0.01)
    monkeypatch.setattr(pipeline, "_persist", AsyncMock(return_value=None))
    result = asyncio.run(pipeline.investigate(name="Timeout Fixture"))
    assert len(finished) == 5
    assert not any(result["sources_consulted"].values())
    assert result["supplier"]["verified"] is False


def test_cancelled_investigation_does_not_leave_source_tasks(monkeypatch):
    started = []
    finished = []
    async def stalled(*args):
        started.append(True)
        try:
            await asyncio.Event().wait()
        finally:
            finished.append(True)
    for source in (sec, gleif, gdelt, courtlistener):
        monkeypatch.setattr(source, "search", stalled)
    monkeypatch.setattr(ofac, "screen", stalled)
    async def exercise():
        task = asyncio.create_task(pipeline.investigate(name="Cancelled Fixture"))
        while len(started) < 5:
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(finished) == 5
    asyncio.run(exercise())


def test_strategy_provider_failure_is_explicit_and_archive_not_relabeled(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "offline-test-only")
    monkeypatch.setattr(board, "_decide_openrouter", AsyncMock(side_effect=RuntimeError("secret-token")))
    result = asyncio.run(board.decide("Should Salesforce sell Notion instead?"))
    assert result["sample"] is True
    assert result["question"] == samples.SAMPLES["salesforce_notion"]["question"]
    assert result["requested_question"] == "Should Salesforce sell Notion instead?"
    assert result["generated_by"] == "mission archive (live generation failed)"
    assert result["error"] == "OpenRouter generation failed"
    assert "secret-token" not in str(result)
    unavailable = asyncio.run(board.decide("Should Acme buy Globex?"))
    assert unavailable["available"] is False
    assert "failed" in unavailable["notice"]


def test_sample_calls_do_not_mutate_archive_or_each_other():
    baseline = copy.deepcopy(samples.SAMPLES["salesforce_notion"])
    result = board.get_sample("salesforce_notion")
    result["seats"][0]["headline"] = "MUTATED"
    result["verdict"]["decision"] = "MUTATED"
    assert samples.SAMPLES["salesforce_notion"] == baseline
    assert board.get_sample("salesforce_notion")["verdict"] == baseline["verdict"]


@pytest.mark.parametrize("missing,expected_score", [("gdelt", 0), ("ofac", 25), ("courtlistener", 10)])
def test_verified_identity_with_one_screening_outage_cannot_authorize_onboarding(missing, expected_score):
    consulted = dict.fromkeys(("sec", "gleif", "gdelt", "ofac", "courtlistener"), True)
    consulted[missing] = False
    risk, _ = evaluate(
        sanctions={"match": False, "list_size": 0 if missing == "ofac" else 100},
        litigation={"available": missing != "courtlistener", "cases": []},
        adverse_media=[], identity_confidence=.95, identity_verdict="verified",
        ownership=[], sources_consulted=consulted,
    )
    assert risk["score"] == expected_score  # Existing point rules are unchanged.
    assert risk["coverage_assessment"]["complete"] is False
    assert risk["coverage_assessment"]["missing_sources"] == [missing]
    assert "Onboarding on hold" in recommendation(risk)
    assert "Standard onboarding may proceed" not in recommendation(risk)


def test_complete_screening_preserves_standard_onboarding():
    risk, _ = evaluate(
        sanctions={"match": False, "list_size": 100},
        litigation={"available": True, "cases": []}, adverse_media=[],
        identity_confidence=.95, identity_verdict="verified", ownership=[],
        sources_consulted=dict.fromkeys(("sec", "gleif", "gdelt", "ofac", "courtlistener"), True),
    )
    assert risk["score"] == 0
    assert risk["coverage_assessment"]["complete"] is True
    assert "Standard onboarding may proceed" in recommendation(risk)


def test_strategy_model_percentages_never_claim_independent_verification():
    result = board._normalize("Should Acme acquire Globex?", {
        "evidence_audit": {"verified_pct": 100, "audited_claims": []}
    })
    audit = result["evidence_audit"]
    assert audit["verification_mode"] == "model_self_assessment"
    assert audit["independently_verified"] is False
    assert audit["audited_claims"] == []


def test_claude_strategy_audit_has_same_provenance_marker():
    import json
    response = types.SimpleNamespace(
        stop_reason="end_turn",
        content=[types.SimpleNamespace(type="text", text=json.dumps({
            "evidence_audit": {"verified_pct": 100, "audited_claims": []}}))],
        usage=types.SimpleNamespace(input_tokens=1, output_tokens=1),
    )
    client = types.SimpleNamespace(messages=types.SimpleNamespace(create=AsyncMock(return_value=response)))
    decision = asyncio.run(board._decide_claude("Should Acme buy Globex?", client))
    assert decision["evidence_audit"]["verification_mode"] == "model_self_assessment"
    assert decision["evidence_audit"]["independently_verified"] is False


@pytest.mark.parametrize("relative", ["mcp_server.py", "static/mcp_server.py"])
@pytest.mark.parametrize("brahma,legacy,expected", [
    ("http://new.test/", "http://legacy.test/", "http://new.test"),
    (None, "http://legacy.test/", "http://legacy.test"),
    (None, None, "http://127.0.0.1:8000"),
])
def test_mcp_name_url_precedence_and_tool_payload(monkeypatch, relative, brahma, legacy, expected):
    # MCP is an optional installation; this checks module wiring, not the protocol.
    class FakeMCP:
        def __init__(self, name):
            self.name = name
        def tool(self):
            return lambda fn: fn
    module = types.ModuleType("mcp.server.fastmcp")
    module.FastMCP = FakeMCP
    monkeypatch.setitem(sys.modules, "mcp.server.fastmcp", module)
    for name, value in (("BRAHMA_URL", brahma), ("ARGUS_URL", legacy)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    namespace = runpy.run_path(str(Path(__file__).resolve().parents[1] / relative))
    assert namespace["mcp"].name == "Brahma"
    assert namespace["BRAHMA_URL"] == namespace["ARGUS_URL"] == expected
    seen = []
    def respond(request):
        seen.append(request)
        return httpx.Response(200, json={"fixture": True})
    original_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda: original_client(transport=httpx.MockTransport(respond)))
    result = asyncio.run(namespace["investigate_supplier"]("Fixture Person", "US", "individual", "1980"))
    assert result == {"fixture": True}
    assert str(seen[0].url) == expected + "/api/v1/supplier/investigate"
    import json
    assert json.loads(seen[0].content) == {"name": "Fixture Person", "country": "US",
                                          "entity_type": "individual", "date_of_birth": "1980"}
