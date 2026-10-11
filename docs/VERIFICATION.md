# Brahma build verification

## Live identity and media correction — October 11, 2026

- Reproduced a fuzzy `Anthropic` query selecting an Anthropic-related ETF.
  The public GLEIF lookup for `984500B6DEB8CEBC4Z70` returned `ANTHROPIC, PBC`.
  Registration numbers now reach the adapter, and LEIs select the direct record
  endpoint. PBC is treated as a legal suffix during name matching.
- Browser verification submitted the user's company, country, website, city and
  address through the real API, including the LEI initially entered in aliases.
  The request preserved those fields, moved the LEI into registration, and returned
  `ANTHROPIC, PBC` with the matching LEI. Desktop and 390px layouts had no overflow
  or browser page errors. Elapsed-time feedback and cancellation were exercised
  with a held request; no claim is made that browser cancellation stops work
  already running on the server.
- Media rendering now distinguishes source outages, genuinely empty returned
  evidence and filter-empty views. Responses include media availability and the
  search window; GDELT requests are capped to its recent three-month index.
- Direct GDELT requests returned HTTP 503 connection timeouts. SEC, GLEIF and
  CourtListener responded during the live reproduction; OFAC and GDELT coverage
  remained unavailable. No missing articles or sanctions checks are fabricated.
- Added regression coverage for exact LEI requests, failed identifier lookups,
  ordinary registration fallback, identifier field correction, preserved form
  details, PBC normalization, media empty states and the GDELT search window.
- Final full suite: **208 tests and 230 subtests passed** in 48.87 seconds.
  Both JavaScript syntax checks and `git diff --check` passed. The restarted
  server returned HTTP 200 in 21.85 seconds for the complete Anthropic request,
  with the expected legal name/LEI, identity score 0.7842 and explicit missing
  OFAC/GDELT coverage.

## Entity search correction — October 11, 2026

- The former sample-only search now offers explicit company/person live actions.
  Unknown names keep an honest "No sample cases match" message while still
  providing access to the live workflow.
- Focused frontend/rendering checks: **32 passed, 19 subtests passed**, including
  three new tests for unknown-name actions, escaped names, entity type selection,
  stale-detail clearing, empty queries and invalid types. The broader suite run
  before collecting those three new tests passed **195 tests and 230 subtests**.
- Chromium verified company/person payloads and cleared aliases/country at
  1440px and 390px with no page errors or horizontal overflow. API responses
  were intercepted for these UI checks, not claimed as real source coverage.
- A separate real Anthropic investigation returned HTTP 200 with all five source
  coverage flags false and `supplier.verified=false`. A direct GLEIF connection
  was denied by the cloud proxy (CONNECT 403).
- Required source domains were saved to the environment network configuration
  draft, preserving the package-manager preset. This save does not apply or
  publish the configuration; live source access is still blocked in this instance.

## Shared workspace polish — October 11, 2026

Expanded palette follow-up: the focused frontend suite passed **53 tests and
230 subtests**. Chromium checks were repeated across 1440, 1024, 390 and 320px
for colored investigation surfaces, evidence, reports, network and developer
panels. The five accent text/soft-surface pairs measure at least 5:1 contrast.
No backend behavior changed in this palette pass.

- Current cloud instance: Python 3.12.14, Node 24.19.0, local SQLite and
  hashed embeddings. Dependencies installed in `.venv`; `pip check` passed.
- Full suite after the workspace changes: **195 passed, 230 subtests passed**
  in 42.78 seconds (`.venv/bin/python -m pytest tests -q`). The added test
  covers developer tab visibility, selected state, roving focus, keyboard
  wrapping, Home/End and invalid input handling.
- Both `node --check static/app.js` and `node --check static/motion.js` passed.
  `git diff --check` passed.
- Headless system Chromium checked Investigate, Evidence, Network, Analysis
  report and Developer screens at 1440, 1024, 390 and 320 pixels. No page
  errors or document horizontal overflow occurred. Desktop intake widths were
  checked after correcting a conflicting column rule; smaller layouts stack.
- Functional browser checks covered sample loading, graph keyboard selection,
  connection selection and deterministic sample insight generation, all four
  report tabs, developer tab keyboard navigation and MCP client switching.
  These checks validate the displayed client configuration, not an external
  MCP client session.
- Verified an actual panel animation call and cancellation after reduced-motion
  preference changes. Reduced motion stops graph animation and navigation uses
  immediate scrolling. No animation remains after the preference change settles.
- Screenshots are in ignored `artifacts/polish-*.png`, including desktop/mobile
  investigation, developer, graph, report and evidence states.
- Root, bundled scripts, OpenAPI, health, schema-valid Northwind sample response,
  and strategy sample decision requests passed against the running service.
- OFAC warm-up returned HTTP 403 from both configured download destinations;
  health correctly reports zero indexed names. Live investigations, paid APIs,
  production PostgreSQL and external MCP sessions were not validated in this run.
- Reusable installation and startup instructions were saved to the environment
  draft. Draft persistence does not publish an environment or establish restoration
  in a fresh task.

Date: October 10, 2026. Branch: `codex/brahma-redesign`.

## Automated checks

- Full final offline suite: **154 passed, 16 subtests passed**, 106.13 seconds.
  Command: `.venv/Scripts/python.exe -B -m pytest tests -q -p no:cacheprovider`.
- Backend compatibility and security subset: **50 passed**, 17.95 seconds.
- Frontend contracts rerun after the last navigation edit: **12 passed**.
- JavaScript syntax: `node --check static/app.js` passed.
- `git diff --check` passed.
- Windows asyncio needs a local socket pair. The restricted sandbox blocked
  its initialization; final async tests ran with that restriction lifted.
  Offline tests forbid external HTTP and use isolated temporary databases.

## Browser checks performed

- Desktop screening, evidence, graph, strategy and developer workspaces.
- Responsive views at 1440x960, 390x844 and 320x740; no document-level
  horizontal overflow in the phone views inspected. Wide tables scroll locally.
- Required-name validation, individual mode and date-of-birth visibility.
- Northwind sample investigation and explicit sample provenance.
- High-severity filter (20 to 17 articles), reset, and mobile filter disclosure.
- Entity-resolution and connections graphs; node selection, zoom, detailed
  match features and deterministic insight generation.
- Strategy archive scenario and a new question without an AI key. The latter
  produces an unavailable notice, not a fabricated decision.
- REST playground and switching the MCP configuration to Codex.
- JSON download completed and its parsed contents confirmed `application=Brahma`,
  `sample=true` and the correct selected entity. Strategy mode disables an
  unrelated entity export.
- No browser JavaScript errors in the inspected sessions.
- Desktop/mobile screenshots saved in the ignored `artifacts/` directory.

## Live-source smoke test

A real REST investigation for Wells Fargo & Company completed in 60.03 seconds.
OFAC, SEC EDGAR, GLEIF and CourtListener responded; OFAC reported 39,598 indexed
names. GDELT returned HTTP 429 and hit the source budget. The response and UI
reported that coverage as unavailable. Report generation used the deterministic
fallback, not an LLM. No supplied credentials or paid model calls were used.

This one smoke test establishes connectivity and graceful partial failure, not
the completeness or correctness of every source. Subsequent coverage-gating
changes were verified by the offline suite and the server was restarted with
the finished code.

## Analysis report readability update

- Replaced dense report tables with Overview, Team views, Evidence, and
  Challenges tabs. Specialist scores remain sortable; all previously displayed
  report text is retained. No analysis or backend behavior was changed.
- Passed 12 existing frontend contract tests and 7 new report UI tests covering
  sample content preservation, escaping, score bounds, empty states, sorting,
  tab relationships, keyboard navigation, and sample/live audit caveats.
- Browser-verified all three sample decisions, tab switching, keyboard navigation,
  report collapse/reopen, and specialist sorting. Checked desktop at 1440x960
  and mobile at 390x844 and 320x740; no horizontal page overflow or JavaScript
  errors observed. Screenshots: `artifacts/brahma-report-desktop.jpg` and
  `artifacts/brahma-report-mobile.jpg`.
- Node syntax and `git diff --check` passed. The full backend suite was not
  rerun for this presentation-only update.

## Evidence workspace and motion redesign

- Redesigned risk assessment as a full-width summary, separated evidence into
  three working views, replaced the word cloud with ranked article-count facets,
  and replaced the nested media-bias table with native disclosures.
- Local Geist font, coordinated spacing/type/color tokens, and state-driven
  panel, row, bar, and disclosure motion. Research references: `DESIGN.md`.
- Final targeted suite: **52 passed, 229 subtests passed**. Command:
  `.venv/Scripts/python.exe -B -m pytest tests/test_frontend_contract.py tests/test_strategy_report_ui.py tests/test_evidence_rendering.py tests/test_motion_contract.py -q -p no:cacheprovider`.
- Browser-checked 1920, 1440, 1024, 390, and 320px widths. No horizontal
  document overflow in the inspected cases. Verified tab keyboard navigation,
  term expansion/filtering, category scope, tablet/mobile filter disclosure,
  zero-result state, retained open annotations, and the analysis report.
- Monthly bars now use a common plot-height wrapper, separate from labels.
  Missing source coverage remains distinct from clean screening.
- Motion unit tests exercise reduced-motion changes, cancellation, background
  tabs, row-stagger limits, optional browser APIs, and observer cleanup.
- No JavaScript errors observed. App/motion Node syntax and diff whitespace
  checks passed. The backend suite was not rerun for this frontend-only update.
- Screenshots: `artifacts/brahma-workspace-desktop.jpg` and
  `artifacts/brahma-workspace-mobile.jpg`.

## Remaining limits

- Public hosting was not changed or created. The preview binds to loopback.
- Paid LLM/embedding paths and an actual external MCP client session were not
  exercised. MCP URL, name and payload contracts have automated coverage.
- No Docker/production PostgreSQL deployment or load test was performed.
- Source rate limits, freshness, upstream availability and provider-specific
  model compatibility remain deployment considerations.
- Authentication, tenancy, access-control policy, audit retention, production
  monitoring and secured administrative endpoints remain prerequisites for
  shared public use. This is a working research/demo build, not a production
  security certification.
- Historical source documentation is retained separately and is not a claim
  that its original benchmarks or architecture assertions were independently
  revalidated. See `PROVENANCE.md` and `QA_FINDINGS.md`.
