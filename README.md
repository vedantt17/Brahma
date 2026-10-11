# Brahma

An entity-intelligence workspace for researching organizations and individuals,
reviewing evidence, exploring relationships, and evaluating strategic decisions.

## Run locally

Python 3.12+ is recommended. The browser assets are included; Node is not required
to run the application.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt pytest
.\scripts\start_brahma.ps1 -Port 8770
```

Open http://127.0.0.1:8770. The launcher binds to loopback only and uses a local
SQLite database at `data/brahma.db` unless `DATABASE_URL` is explicitly set.
It refuses to take over an occupied port. Logs are under `artifacts/`.

On other platforms:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt pytest
DATABASE_URL=sqlite+aiosqlite:///./data/brahma.db uvicorn app.main:app --host 127.0.0.1 --port 8770
```

## Workspaces

- **Investigate:** organization/person screening, sample case search, and a strategy decision board.
- **Evidence:** adverse media, category/severity/objectivity filters, sanctions, litigation, ownership, source coverage and risk contributions.
- **Relationships:** interactive entity-resolution and connection graphs, node/edge inspection, detailed evidence and raw JSON.
- **Developers:** REST playground, MCP client configuration, downloadable Python connector and OpenAPI reference at `/docs`.
- **Export:** the current investigation is available as a JSON download.

The **Find an entity** search filters curated samples and also offers **Search
company** / **Search person** for any typed name. Those actions start a live
investigation; they do not require a matching sample. They clear previous subject
details so a new name is not searched with another entity's country or aliases.
Use the main investigation form when supplying additional identity details.
Searching the same name/type from the sidebar preserves those completed details.
Put an LEI in **Registration number**; recognizable LEIs accidentally entered as
aliases are moved there before submission. GLEIF looks up that identifier directly.
The report shows the registry's legal name, which may differ from a trading name
(for example, `ANTHROPIC, PBC` for Anthropic).

Live results require outbound access to the source adapters. In a restricted
cloud environment, allow `api.gleif.org`, `api.gdeltproject.org`, `www.sec.gov`,
`data.sec.gov`, `efts.sec.gov`, `www.courtlistener.com`,
`sanctionslistservice.ofac.treas.gov`, and `www.treasury.gov`. SEC also requires
a real contact User-Agent. An unavailable source is a coverage gap, not a
verified identity or a clean screening result.
The GDELT DOC API covers a recent window of up to three months. The media panel
distinguishes source failures, searches returning no adverse headlines, and
articles hidden by selected filters. It is not a complete news archive.
News queries remove trailing incorporation forms (`Anthropic, PBC` searches
`Anthropic`) while preserving distinctive business words. Returned news includes
query and filtering counts. Litigation counts represent deduplicated, bounded
docket-title matches, not a complete lawsuit count or proof of wrongdoing.
An explicit LEI binds registry selection; lookalike identifiers and related-party
records are excluded from the selected company’s evidence.

The existing API routes remain compatible. Primary endpoint:

```http
POST /api/v1/supplier/investigate
Content-Type: application/json

{"name":"Wells Fargo & Company","country":"United States"}
```

The MCP wrapper reads `BRAHMA_URL`. `ARGUS_URL` remains supported for compatibility.

## Data and keys

Curated samples are explicitly labeled and are **not live verification**. The live
workflow queries OFAC, SEC EDGAR, GLEIF, GDELT and CourtListener as available.
Requests and responses may be cached or stored locally. Use public, non-confidential
data in this development environment.

Copy `.env.example` to `.env` only when configuring your own environment. Never
commit credentials. Set a real contact User-Agent for SEC access.

| Optional setting | Behavior without it |
| --- | --- |
| `ANTHROPIC_API_KEY` | Evidence-based deterministic report instead of Claude generation. |
| `OPENAI_API_KEY` | Local or hashed embeddings instead of OpenAI embeddings. |
| `OPENROUTER_API_KEY` | Curated strategy samples or an explicitly unavailable live result; Anthropic may be used if configured. |
| `COURTLISTENER_API_TOKEN` | Litigation coverage gap, not a clean litigation check. |

Source outages and missing coverage must not be interpreted as low real-world
risk. OpenCorporates and VirusTotal placeholders are not live integrations and
are excluded from risk scoring. Scores are heuristic decision support, not
compliance certification or probability estimates.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
node --check static/app.js
```

See `docs/QA_FINDINGS.md` for the independent review and `docs/VERIFICATION.md`
for the actual checks and limitations of this build.

## Hosting

`Dockerfile` and `render.yaml` are retained as deployment starting points. This
edition has not replaced or modified the upstream public demo. A shared deployment
requires authentication, access control, an appropriately protected admin API,
database backups, retention policy, rate limits and monitoring. Configure a
persistent PostgreSQL database and set `ALLOW_SQLITE_FALLBACK=false` in hosted
environments. Do not expose this local research workspace directly to the public
internet. No production-readiness claim is made.

## Architecture and attribution

FastAPI + SQLAlchemy + async HTTP source adapters, with a lightweight static
HTML/CSS/JavaScript client. The redesign deliberately keeps the original backend
contracts instead of replacing working integrations.

This is an adapted project, not a from-scratch authorship claim. See
`PROVENANCE.md` for the original project and permission context, and
`docs/UPSTREAM_README.md` for the original technical documentation. Lucide's license
is retained under `static/vendor/`.
