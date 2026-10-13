# Brahma: End-to-End Work Log and Handoff

**Prepared:** October 10, 2026 (America/Los_Angeles)
**Repository:** `C:\Users\v\OneDrive - Shri Vile Parle Kelavani Mandal\Documents\New project\brahma`
**Branch:** `codex/brahma-redesign`
**Local preview:** [http://127.0.0.1:8770/](http://127.0.0.1:8770/)

This is the working handoff for the Brahma/Credence project work discussed across the prior day and today; it does not summarize unrelated job applications and resume work elsewhere in the conversation. The order of work is recorded below; exact timestamps for every earlier project conversation were not retained, so this is not a minute-by-minute activity log. Repository paths are relative to the root above unless shown as absolute paths.

## 1. How the project direction changed

The project work began while preparing a technical demonstration for Credence ID's Solution Engineer interview. We discussed ideas that could use Credence's mobile-ID SDKs, then tested the underlying business need instead of choosing an integration merely to include an SDK. Rental pickup exception handling and integration diagnostics were considered, along with ways Credence APIs could fit existing work. The concern was whether those features solved a real operator problem or invented one to satisfy the assignment.

The direction then shifted to developing **Brahma**, Vedant Tiwari's entity-intelligence project, as a technical demonstration for Credence ID. The work focused on preserving its investigation capabilities while making the live application a coherent, usable research and decision workspace.

The product was kept within the existing FastAPI, SQLAlchemy, static HTML/CSS/JavaScript stack. The aim became a coherent, usable research and decision workspace rather than a visual mockup. The repository retains historical technical documentation and Git history alongside the ongoing development of Brahma.

## 2. What Brahma contains

Brahma is an entity-intelligence workspace for researching organizations and people, reviewing source evidence, exploring entity relationships, and organizing strategic decisions. Its major user areas are:

- **Investigate:** submit a company or person, search the curated sample set, or use the decision-board mode.
- **Evidence:** review adverse-media items, risk categories, severity and language-objectivity signals; inspect sanctions, court, ownership and source-coverage details.
- **Network:** explore entity-resolution candidates and relationship connections in an interactive graph, then inspect selected nodes and edges.
- **Developers:** try the REST API, configure the MCP client, access generated integration details, and open the FastAPI/OpenAPI documentation.
- **Export:** download the current investigation as JSON.

The sample cases are illustrative offline fixtures and are labelled accordingly. Live investigation is separate: available adapters can query OFAC, SEC EDGAR, GLEIF, GDELT and CourtListener. Missing or failed source coverage is represented as unavailable, not as a clean screen. Risk values are heuristic decision support; they are not a probability, compliance certification or final onboarding decision.

## 3. Architecture and important locations

### Backend and integrations

- `app/main.py`: FastAPI application, lifespan and root UI serving.
- `app/api/v1.py`: investigation, stored reports, source refresh, graph insights, crew, strategy, demo and health endpoints.
- `app/pipeline.py`: orchestration of source collection, identity resolution, evidence assembly and report creation.
- `app/sources/`: individual external-source adapters (`ofac.py`, `sec.py`, `gleif.py`, `gdelt.py`, `courtlistener.py`).
- `app/resolution/`: entity-match logic and supporting features.
- `app/risk/engine.py`: risk contributions, score and recommendation logic, including required-source coverage handling.
- `app/agent/` and `app/crew/`: report generation and investigation-team workflow.
- `app/strategy/board.py`: decision-board logic and sample/live behavior.
- `mcp_server.py` and `static/mcp_server.py`: MCP integration surfaces and generated/configuration support.
- `Dockerfile`, `docker-compose.yml`, and `render.yaml`: retained deployment starting points; they are not evidence of a production deployment.

The API is rooted at `/api/v1`. Its current routes are documented in the FastAPI UI at `/docs`; core operations include `POST /api/v1/supplier/investigate`, listing and retrieving stored investigations, risk categories, graph insights, crew roster/replay, decision samples/decisions, offline demo subjects, source health and OFAC refresh. The MCP server uses `BRAHMA_URL`; `ARGUS_URL` remains accepted for compatibility.

### Frontend and assets

- `static/index.html`: application shell and all four main workspaces.
- `static/app.js`: navigation, investigation loading, evidence rendering/filtering, graph interactions and report/decision-board behavior.
- `static/brahma.css`: shared typography, color tokens, navigation, forms, graph/report and responsive base styling.
- `static/evidence-workspace.css`: evidence-focused layout and responsive overrides.
- `static/motion.js`: progressive, state-driven motion; loaded after the main application script.
- `static/favicon.svg`: Brahma application icon.
- `static/vendor/`: local Lucide browser bundle and license; local Geist variable font and license. The browser does not need to fetch these assets from a font CDN.
- `package.json` / `package-lock.json`: frontend asset/development metadata. Node is not required to run the app.

### Data, configuration and operations

- `data/brahma.db`: current local SQLite database. At handoff, SQLite WAL and shared-memory sidecars were present (`brahma.db-wal`, `brahma.db-shm`), which is normal while the running server is using SQLite.
- `.env.example`: names and descriptions of optional model/provider settings. It contains example configuration, not a user's live credentials.
- `requirements.txt`: Python dependencies.
- `scripts/start_brahma.ps1`: starts the FastAPI app bound to loopback, chooses local SQLite when `DATABASE_URL` is unset, refuses to take over an occupied port, and writes output to `artifacts/`.
- `.brahma-server.pid`: PID written by that launcher. It contained `27952` when this log was prepared; the local browser was connected to port 8770.
- `artifacts/server.stdout.log` and `artifacts/server.stderr.log`: server output/error logs. The captured stderr file was empty at handoff.

## 4. Product and reliability work completed before the latest screen redesign

The adaptation retained the existing source and API contracts while making Brahma a cohesive application. Work recorded in the repository includes the Brahma name and local visual identity; the responsive shell and navigation; offline/sample state labels; working forms and entity modes; evidence filters; entity-resolution and relationship graphs; decision-board samples and report sections; a REST playground and MCP setup surfaces; JSON export; and readable source-availability reporting.

Several data-integrity risks were reviewed and corrected in code:

1. **Incomplete source coverage:** a missing required source must not quietly produce a low-risk or affirmative onboarding recommendation. Completeness is handled separately from adverse-event severity.
2. **Sanctions coverage:** an empty/unavailable OFAC list must be reported as `unavailable / not screened`; it must not be expressed as a successful no-match.
3. **Model self-assessment:** strategy audit percentages are labelled as a model self-assessment unless evidence has been independently checked. The UI does not imply citations were independently verified when they were not.
4. **Presentation semantics:** sample data remains explicitly illustrative; categories can overlap; risk-term counts represent articles; language flags are not claims of factual inaccuracy.

Details and review history are in [QA findings](QA_FINDINGS.md). The original technical description was retained in [UPSTREAM_README.md](UPSTREAM_README.md) for context; those historical claims and benchmarks were not independently revalidated simply by preserving that document.

## 5. Analysis-report readability work

The prior report screen was dense and difficult to scan. It was reorganized into four keyboard-accessible sections: **Overview**, **Team views**, **Evidence**, and **Challenges**. The report still contains the existing analysis: decision and conditions, specialist/board perspectives, claim-level evidence review, audit caveats and challenges. Sorting, report collapse/reopen, score display, and sample/live distinctions remain available. This work changed the presentation, not the decision-analysis backend.

Related implementation and tests:

- `static/app.js`: `renderAnalysisReport`, report-tab state, specialist rendering and audit rendering.
- `static/brahma.css` and `static/evidence-workspace.css`: report layout and responsive styles.
- `tests/test_strategy_report_ui.py`: report-specific rendering, preservation, accessibility and sample/live caveat checks.
- Screenshots: `artifacts/brahma-report-desktop.jpg`, `artifacts/brahma-report-mobile.jpg`.

## 6. October 10 evidence-workspace redesign

The supplied screenshots showed two problems: risk assessment and language analysis were squeezed into a narrow column, and risk terms used large, irregular type that made comparisons difficult. The evidence workspace was reorganized around the case itself:

- A **full-width risk summary** now shows the overall score, identity, sanctions, adverse-media and litigation status, recommendation, and applicable sample/coverage caveats.
- Evidence work is split into **Media evidence**, **Risk signals**, and **Records & summary** tabs. Arrow keys, Home and End move through the evidence tabs; only the selected tab is in the tab order.
- The risk-word cloud was replaced with consistently sized **ranked term rows**. Counts show how many articles contain each term; alternative terms remain visible when a term filter is applied; the list can expand beyond the initial eight entries.
- Category coverage uses consistent bars and labels. The interface says when categories overlap and clearly distinguishes all evidence from filtered evidence. The month chart gives every bar the same plotting height and keeps month text separate.
- The old nested media-bias table became an **expandable article list**. The flagged-lines-only control filters sentence annotations while preserving disclosure state. The UI describes the results as language signals, not factual verification.
- Article date/source/objectivity metadata remains visible below the headline on smaller screens. The media filter rail becomes a disclosure on narrow layouts. Empty results remain readable when columns are hidden.
- The risk view avoids treating unavailable source checks as clean findings. Media filters do not masquerade as filters on the full investigation record view.

The visual system uses a locally bundled Geist font, restrained green interaction color, neutral working surfaces and a few semantic status colors. Existing Lucide icons are retained. The redesign uses motion to acknowledge state changes: view/panel transitions use a small offset and short duration; article rows have a capped stagger; disclosure content enters briefly; quantitative fills animate with `scaleX` while keeping their actual width stable. There is no initial-load choreography. Reduced-motion preference changes and backgrounding cancel animation; content is available if the Web Animations API is missing.

Motion behavior lives in `static/motion.js`. It watches actual application state and DOM updates; optional hooks are `data-motion-panel`, `data-motion-row` and `data-motion-bar`. `window.BrahmaMotion` provides `enter`, `refresh`, `cancel` and `destroy`; the application can emit `brahma:rendered` to refresh after a render. No focus is moved by an animation.

### Design research

Research and inspiration notes, including direct GitHub and Reddit references and company design-system references, are in [DESIGN.md](DESIGN.md). In brief, the work used Impeccable's critique/simplification approach; Anthropic's frontend-design guidance; community experience from the Reddit discussion; Linear's quieter, more predictable interface choices; and IBM Carbon's short, productive motion guidance. No remote skill installer or project hook was run. Inspiration was translated into Brahma's own operational constraints and design; no outside interface was copied wholesale.

### Collaboration used in the latest pass

Three subagents handled bounded work: Archimedes updated the evidence renderers and added rendering tests; Banach implemented the progressive motion module and its tests; Darwin reviewed layout/data semantics and reported issues. The primary agent integrated the CSS/HTML, addressed reviewer notes, and ran the combined browser and test checks. There was no formal multi-agent voting system or unanimous production-readiness vote in this pass.

## 7. How the app was checked

### Automated checks

On October 10, the focused frontend suite passed **52 tests and 229 subtests**:

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_frontend_contract.py tests/test_strategy_report_ui.py tests/test_evidence_rendering.py tests/test_motion_contract.py -q -p no:cacheprovider
```

The run covered frontend contracts and escaping, report states, evidence and filter behavior, mobile metadata, article-count semantics, unavailable coverage, tab focus and keyboard navigation, open disclosures, no-results rendering, and motion cancellation/reduced-motion handling. `node --check static/app.js`, `node --check static/motion.js`, and `git diff --check` also passed. No browser JavaScript errors were observed during the recorded sessions.

The broader offline test run documented earlier on October 10 was **154 passed plus 16 subtests**; a backend/security subset was **50 passed**. The analysis-report view separately passed 12 existing frontend checks and seven report-specific checks before the later targeted suite. The backend suite was not rerun after the final evidence-only presentation changes. See [verification details](VERIFICATION.md) for exact scope and caveats; test totals from distinct runs should not be added together as if they were one run.

### Browser checks

The local browser was used to inspect the existing app and exercise the redesigned views. Checked widths: **1920, 1440, 1024, 390 and 320 px**. The inspected pages had no document-level horizontal overflow. Checks included:

- opening Elena Marchetti's illustrative sample and reviewing the case summary;
- switching between the three evidence views and using keyboard arrow navigation;
- selecting and clearing a risk-term filter, checking the remaining alternatives and result counts;
- expanding all terms and checking the disclosed full list;
- opening an annotated article, turning on flagged-lines-only, and verifying that the article remains open;
- applying category/objectivity filters to reach and inspect the mobile zero-results state;
- verifying that tablet/mobile filter disclosure works and the empty message stays visible;
- returning to the decision board and checking report tabs and specialist views;
- checking logs for browser errors (none returned).

Screenshots are stored in the ignored local folder `artifacts/`:

- `brahma-desktop.jpg`, `brahma-mobile.jpg`: earlier workspace shell.
- `brahma-report-desktop.jpg`, `brahma-report-mobile.jpg`: analysis-report layout.
- `brahma-workspace-desktop.jpg`, `brahma-workspace-mobile.jpg`: latest evidence/risk layout.

### Live-source smoke test recorded earlier

A real REST investigation for Wells Fargo & Company returned from OFAC, SEC EDGAR, GLEIF and CourtListener; GDELT returned HTTP 429, and that coverage gap appeared in the response/UI. The deterministic report fallback was used; no paid model call or user-supplied credential was used. One smoke test demonstrates graceful handling of that observed failure, not universal source completeness, uptime or correctness. More detail is in `docs/VERIFICATION.md`.

## 8. Current workspace state

- The local preview is at **http://127.0.0.1:8770/**. It binds to loopback.
- The launcher recorded PID **27952** in `.brahma-server.pid` when checked. Do not try to start a second copy on port 8770; the launcher refuses to take over an occupied port. The connection is local and is not a public deployment.
- Git HEAD remains `5559b1f` (`Update README title and fix description formatting`), shared with `origin/main` at the time checked. Current work is **uncommitted** on `codex/brahma-redesign`.
- The working tree contains changes to API/backend modules, README/configuration/deployment references and tests, and new frontend assets, design/verification/provenance documents, launcher and screenshots. The exact current file list is available with `git status --short` from the repo root.
- No commit, push, public repository creation, production deployment, or upload was performed in this work session.
- The local SQLite database and its WAL sidecars are present under `data/`; preserve them unless intentionally cleaning the local development environment.

## 9. Requested next work that is not complete yet

Immediately before asking for this handoff file, the user asked to carry the current design language, motion and richer color through **Investigate, the Analysis report, Network, and Developers**. That cross-application pass is **still pending**. The report has already had its readability/tabs work described above, and shared color/type/layout changes exist, but Investigate, Network, and Developers have not yet received a complete, individually reviewed design pass matching the evidence workspace. Motion is currently state-driven in the frontend, but the next pass should verify motion coverage and color semantics on each of those screens.

This is the next implementation task when work resumes. Keep the current feature contracts, sample/live provenance, coverage warnings, API/MCP behavior, and keyboard accessibility intact while extending the visual system.

## 10. Start and inspect the local app

From PowerShell:

```powershell
Set-Location 'C:\Users\v\OneDrive - Shri Vile Parle Kelavani Mandal\Documents\New project\brahma'
.\.venv\Scripts\python.exe -m pytest tests -q
.\scripts\start_brahma.ps1 -Port 8770
```

Then open [http://127.0.0.1:8770/](http://127.0.0.1:8770/). If port 8770 is already occupied, use the running instance or choose a different port. The launcher writes its PID and logs as described above. API docs are at [http://127.0.0.1:8770/docs](http://127.0.0.1:8770/docs).

Do not expose this loopback research build directly to the public internet. Shared production use still needs authentication, authorization/tenancy, a protected admin API, a persistent database and backup/retention policy, rate limiting, monitoring, and deployment-specific security review. Optional provider keys are described by variable name in `.env.example`; do not paste real keys into this log or commit them.

## 11. Related documents

- [README.md](../README.md): install/run instructions, product areas, configuration and limitations.
- [DESIGN.md](DESIGN.md): design decisions, motion rules and research links.
- [VERIFICATION.md](VERIFICATION.md): test/browser results, smoke-test observation and remaining limitations.
- [QA_FINDINGS.md](QA_FINDINGS.md): independent review findings and their resolution status.
- [UPSTREAM_README.md](UPSTREAM_README.md): retained original technical documentation.
