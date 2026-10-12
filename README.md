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
The Windows launcher watches backend Python files and reloads after code updates.
If a server was started before this launcher change, restart that process once;
an already running Python process cannot load updated backend modules on its own.

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
Company identity selection is separate from fuzzy ranking. When several legal
entities share a name or brand, the report keeps the submitted name unresolved
and shows registry candidates instead of selecting a namesake. Choose a legal
entity or supply a supported identifier (LEI, `CIK:<number>`, or a registration
number present in the returned registry data). Candidate choice uses its registry
country, preserves other supplied details, and keeps the original brand as a
declared trading name for news searches. Contradictory details still require review.
Country and official source website fields can help distinguish candidates;
missing fields do not count as corroboration. GLEIF retrieves bounded legal-name
and alias candidates and reports truncation. Ownership/insider enrichment runs
only for the selected entity. An unresolved identity cannot authorize onboarding,
even when the screening sources responded. A unique public Wikidata organization
profile can identify a brand such as OpenAI when legal registry records remain
ambiguous. It is labeled `public_profile`, never legal-entity verified. Sourced
CEO and founder claims appear in the Connections network with their Wikidata
links; an undated claim does not independently establish a current role. The
Identity candidates view shows only plausible identity matches, not subsidiaries
or business relationships. Similarly named funds and rejected registry hits are
not included in that graph.
Individual searches use public Wikidata human profiles instead of SEC/GLEIF
company registries. Add an employer/organization, citizenship or optional public
profile identifier to help distinguish namesakes. Profile candidates include
public descriptions and sourced employer claims. When a published employer
profile names the person as CEO, the network shows that role with its source;
an undated claim does not independently establish current employment. Matching
a public profile is not independent identity verification, and user-entered birth
dates are preserved. People absent from the public source stay unresolved.
Allow `www.wikidata.org` for this path.
API and MCP clients can pass optional `employer` and `profile_id` (`Q...`) fields.

Live results require outbound access to the source adapters. In a restricted
cloud environment, allow `api.gleif.org`, `api.gdeltproject.org`, `www.sec.gov`,
`data.sec.gov`, `efts.sec.gov`, `www.courtlistener.com`,
`sanctionslistservice.ofac.treas.gov`, and `www.treasury.gov`. SEC also requires
a real contact User-Agent. An unavailable source is a coverage gap, not a
verified identity or a clean screening result.
Treasury's SDN and alias exports redirect to
`wc2h-sls-prod-public-published.s3.us-gov-west-1.amazonaws.com`; allow that exact
download host as well. After network access is applied, refresh the list with
`POST /api/v1/admin/ofac/refresh` and check `ofac_names_indexed` in health.
The GDELT DOC API covers a recent window of up to three months. If GDELT fails
or returns no locally matched adverse headlines, the app tries public Google
News RSS (`news.google.com`) within a bounded timeout. Allow that domain for
the fallback. Provider status is recorded separately; a healthy fallback can
supply news screening coverage while GDELT remains unavailable. The Evidence
panel also retrieves a separate recent-news feed for both companies and people.
Those general headlines provide context and do not raise the risk score. Both
feeds retain the publisher, date, link, retrieval provider, search window and
result limits. The media panel distinguishes source failures, searches returning
no adverse headlines, and articles hidden by selected filters. Name-matched
headlines are search leads, not proof that an allegation concerns the selected
person or legal entity, and the bounded feeds are not a complete news archive.
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

Vercel discovers the root `main.py` FastAPI entrypoint. `vercel.json` includes
the static interface and gives live source searches a 60-second function budget.
On Vercel, `PUBLIC_DEMO=true` uses temporary `/tmp` storage for source caching,
returns reports to the browser without saving them, disables stored-report and
admin endpoints, and labels the session-only behavior in the form. A public demo
can be deployed without paid AI keys. External source availability still varies;
an unavailable source remains a coverage gap. The configured SEC User-Agent
points to this repository's public issue page for contact.

`Dockerfile` and `render.yaml` remain alternatives for a persistent service.
Shared production use needs authentication, access control, a protected admin
API, database backups, retention policy, rate limits and monitoring. Configure
a persistent PostgreSQL database and set `ALLOW_SQLITE_FALLBACK=false` in that
setting. The Vercel configuration is a public demo, not a production screening
service.

## Architecture and attribution

FastAPI + SQLAlchemy + async HTTP source adapters, with a lightweight static
HTML/CSS/JavaScript client. The redesign deliberately keeps the original backend
contracts instead of replacing working integrations.

This is an adapted project, not a from-scratch authorship claim. See
`PROVENANCE.md` for the original project and permission context, and
`docs/UPSTREAM_README.md` for the original technical documentation. Lucide's license
is retained under `static/vendor/`.
