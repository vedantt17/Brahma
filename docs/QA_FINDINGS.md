# Independent QA Findings

Review date: 2026-10-10. Scope: frontend contracts and backend/data reliability.
Only `tests/test_frontend_contract.py` and this file were authored by this review.
No browser, live-source requests, commits, or application edits were performed.
Line numbers and original repros identify the reviewed snapshot, not necessarily
the final implementation. Intermediate frontend failures below are not final defects.

## Latest Status

Parent-reported verification update, 2026-10-10:

- All three findings below are resolved by backend/JS changes and parent review.
- The actual risk engine now gates recommendations on coverage completeness.
- OFAC evidence explicitly identifies unavailable screening rather than clearance.
- Strategy metadata and UI label the audit as model self-assessment, not
  independently verified evidence.
- Latest targeted backend run: **50 tests passed**, reported by the parent.
- Parent browser QA completed at desktop 1440px and mobile 390px. A real Wells
  Fargo investigation returned four sources; GDELT HTTP 429 was shown as an
  explicit coverage gap, not a clean result.

These parent-reported checks were not independently rerun by this QA author.
The parent is preparing `docs/VERIFICATION.md` and the final test results;
that handoff remains the source for exact final commands and browser evidence.

## Findings And Status

### Resolved P1: Missing coverage could authorize standard onboarding

- Location: `app/risk/engine.py:82`, `app/risk/engine.py:129`,
  `app/risk/engine.py:216`.
- Original reproduction with actual `evaluate()` and `recommendation()` functions: a
  verified identity, no returned hits, and `sources_consulted.gdelt=False`
  produced score 0, level `low`, no reasons, and
  `Standard onboarding may proceed with periodic monitoring.` A missing OFAC
  index alone produced 25 points, still `low` and the same recommendation.
- This is distinct from identity verification. A verified registry identity
  does not verify sanctions/media clearance. Making source flags accurate is
  necessary but does not fix this downstream recommendation.
- Original repro from the repository root (Python, no network):

```python
from app.risk.engine import evaluate, recommendation
for missing in ("gdelt", "ofac"):
    consulted = dict.fromkeys(("sec", "gleif", "gdelt", "ofac", "courtlistener"), True)
    consulted[missing] = False
    risk, _ = evaluate(
        sanctions={"match": False, "list_size": 0 if missing == "ofac" else 100},
        litigation={"available": True, "cases": []}, adverse_media=[],
        identity_confidence=.95, identity_verdict="verified", ownership=[],
        sources_consulted=consulted,
    )
    print(missing, risk["score"], risk["level"], recommendation(risk))
```

- Handoff: backend/risk owner. Represent assessment completeness separately
  from adverse-event severity; gate affirmative onboarding recommendations on
  required coverage. Add single-source-outage tests, not only all-sources-down
  tests. Do not manufacture an adverse finding merely to increase the score.
- Resolution: the parent confirms a coverage gate in the actual risk engine,
  not only UI wording, and has reviewed the fix. Closed on that verification.

### Resolved P2: Unperformed OFAC screen described as a negative result

- Location: `app/pipeline.py:683` (`_build_evidence`).
- Original repro: `_build_evidence([], [], {"cases": []}, {"match": False, "list_size": 0})`
  returned an OFAC evidence item with description
  `Sanctions screening against the SDN list (0 names): no match` and the official
  OFAC URL. This was executed without a network request.
- The official URL identifies a source, not proof that this subject was
  screened. API consumers and the LLM evidence bundle can interpret the item as
  evidence of clearance. The concurrently updated deterministic narrative now
  says `OFAC screening unavailable - sanctions status unverified.`; that fixes
  the narrative before the evidence fix landed.
- Rechecked after the backend fix: the same direct function call now returns
  `OFAC screening unavailable; sanctions status unverified`. The evidence
  wording defect was independently reverified. Parent also confirms the
  completed backend/JS fix and review; this finding is closed.

### Resolved P2: Strategy self-assessment presented as verified evidence

- Location: `app/strategy/board.py:311`, `app/strategy/board.py:372`,
  `app/strategy/board.py:411`, `app/strategy/board.py:541`.
- At original review, both live strategy paths sent a question to one model
  without retrieval or supporting-document checks. Normalization accepted
  `verified_pct` independently of claims or citations. Repro executed:
  `_normalize("Should Acme acquire Globex?", {"evidence_audit": {"verified_pct": 100,
  "audited_claims": []}})["evidence_audit"]` returned 100% verified with no claims.
- The frontend's evidence audit and timeline could therefore display verified
  percentages without any externally verified evidence. This was a provenance
  limitation even when model JSON is valid, not a claim about a provider outage.
- Handoff: strategy/data and frontend owners. Label this as a model
  self-assessment with no independent verification, or verify retrieved
  citations before using "verified". Derive percentages from validated claim
  statuses and test missing evidence and inconsistent totals.
- Resolution: parent confirms explicit model-self-assessment metadata and
  truthful UI labels after backend/JS changes and review. Closed through
  disclosure of the limitation, not a claim that external verification was added.

## Data Provenance

- `/api/v1/demo/investigate/{id}` assembles fixtures from
  `app/demo/dataset.py` and `app/demo/generator.py`. Article URLs are `None`
  (`app/demo/__init__.py:115`); registry identities, transactions, source counts,
  and `sources_consulted=True` in these objects are simulated. Real company
  names in fixtures do not turn those records into live screening results.
- `demo=True` and `agent_summary.generated_by="demo dataset (deterministic)"`
  identify the fixture mode. Preserve those labels in UI, downloads, and API
  integrations. Fixture "clean record" tests do not establish clean real-world
  records for those companies.
- Strategy archives are authored samples, including their percentages and
  votes. Current fallback retains the archive's question, stores the user's
  question separately, and marks `sample=True`; it is not a new investigation.
- Live supplier adapters target OFAC, SEC, GLEIF, GDELT, and CourtListener.
  This review did not verify their current reachability, freshness, accuracy,
  or completeness. Successful offline tests establish contracts, not live
  accuracy. GDELT returns headlines, not the full bodies supplied in demos.
- Optional OpenCorporates/VirusTotal placeholders and deterministic reports
  are not independent external verification. Crew traces replay an already
  assembled object rather than ten separate live investigations.

## Test Coverage And Handoff

- Existing tests cover resolution/scoring helpers, taxonomy, fixture integrity,
  graph shape, strategy normalization, and crew summaries. Concurrent new
  `test_brahma_api.py` and `test_brahma_security.py` add source-failure handling,
  malformed responses, cancellation, persistence, and API validation.
- The original handoff requested single-source-outage gating, OFAC
  evidence/narrative consistency, and truthful strategy provenance; parent
  reports all three findings fixed and 50 backend tests passing. Parent also
  verified partial live coverage and desktop/mobile browser behavior.
- Residual coverage questions, not confirmed defects: stale-index freshness,
  alias-only sanctions hits, and overlapping frontend requests. Refer to the
  parent's final verification for any additional coverage; no new runs were
  performed for this status-only update.
- Original swallowed source-failure and unsafe source-link paths were changed
  during review. They are not listed as outstanding defects based on stale
  code. The added renderer test exercises actual article rendering with
  HTTP(S), javascript (including mixed case/tab), data, file, and absent URLs.
- Static tests derive literal `$()`/`getElementById()` dependencies, exclude
  JS-declared generated IDs, check duplicate HTML IDs and mounted asset files,
  and inspect link attributes. They do not assert copy, layout, CSS classes,
  or exact implementation strings. Computed selectors/render timing require
  the parent's browser QA. Node is optional only for the rendering test.

## Execution Log

Commands below ran from the repository root using its virtualenv.

- `.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_frontend_contract.py -v`
  Initial 11-test run: 10 passed, 1 failed on five DOM IDs during concurrent
  editing. Subsequent 12-test runs: DOM contracts and malicious-link renderer
  passed; 11 passed, 1 failed because `/static/brahma.css` was temporarily
  absent while the stylesheet was being replaced. **Latest rerun: all 12 tests
  passed in 0.179s**, including the Node renderer test. Neither intermediate
  result is a final markup defect.
- `.\.venv\Scripts\python.exe -B -m pytest tests/test_risk.py -q -p no:cacheprovider`
  **12 passed in 0.05s.** This historical run predated the P1 fix and did not
  establish coverage of that finding. Parent's later backend result is above.
- `.\.venv\Scripts\python.exe -B -m pytest tests -q -p no:cacheprovider`
  Interrupted after several minutes without output; no pass claim.
- `.\.venv\Scripts\python.exe -B -m pytest tests -v -p no:cacheprovider`
  Collected 148 items, then hung at
  `tests/test_brahma_api.py::test_startup_root_static_openapi_and_health`.
  Interrupted; no suite pass claim. Both full-suite sessions owned by this
  review are stopped.
- `.\.venv\Scripts\python.exe -B -c "import faulthandler; faulthandler.dump_traceback_later(15, exit=True); import pytest; raise SystemExit(pytest.main(['tests/test_brahma_api.py::test_startup_root_static_openapi_and_health','-vv','-s','-p','no:cacheprovider']))"`
  Collected one test; watchdog dumped the stack after 15 seconds and exited
  with status 1. The blocking stack is:

```text
tests/test_brahma_api.py:42          with asyncio.Runner() as runner
asyncio/runners.py:137              _lazy_init / new_event_loop
asyncio/proactor_events.py:785      _make_self_pipe
socket.py:646                      socketpair
socket.py:295                      accept
```

  The hang is before entering the application lifespan, database access, or
  an HTTP request. It is not collection and does not show a backend coroutine
  deadlock. It is consistent with this environment's sandbox socket restriction:
  Windows asyncio itself needs a loopback socket pair even for offline tests.
  Handoff to parent: stop its stuck sessions and rerun the offline suite with
  the approved socket-capable execution permissions. Do not weaken the tests'
  external-network guard or modify application logic to bypass this restriction.
- Direct Python probes executed actual risk/recommendation, OFAC evidence and
  fallback-report functions, and strategy normalization. Results are recorded
  in the findings above; no source data was fetched.

Parent browser QA is complete as reported above; the parent's final test report
and `docs/VERIFICATION.md` are pending this status update. No QA-owned command
sessions remain running. This review does not certify production readiness.
