# 02 — Ingestion pipeline (menu, nutrition, and hours scraper)

| | |
|---|---|
| **Author** | Ethan Goodman |
| **Date** | 2026-10-06 |
| **Tool / model** | Claude Code (VS Code extension), Claude Opus 5.5 |

## 1. Request

Build the ingestion job from our architecture (proj_1b report, Figure 1:
Fetch → Parse → Normalize + Label → Write) inside the Project 2 skeleton.
Scope was the scraper only: no frontend, filter engine, crowd reports, or API
routes.

The AI was given a handoff document from an earlier session. In that session the
team built a throwaway prototype to check that the data could be scraped at all.
The handoff covered how the two source sites work, the prototype's design, and
the team's report. The AI was told to:

- **discuss its plan before writing any code**, and look for licensing issues,
  bugs, rate limits, how often we may scrape, and whether scraping is allowed;
- port the prototype into the skeleton's structure, not copy its SQLite setup;
- keep the single-writer-per-table rule;
- run only small live tests (one location) and ask before any full scrape,
  commit, or push.

Site knowledge (endpoints, form fields, page structure) comes from inspecting
NetNutrition's own JavaScript and HTML, and dining.ncsu.edu's HTML.

## 2. AI proposal

After reading the skeleton, the prototype, and the 1b report, the first plan
was:

- Fill in the existing `ingestion/` stubs. Use **plain psycopg plus versioned
  `.sql` migrations owned by ingestion**, to match the skeleton, which had no ORM.
- Port the prototype's offline parser tests and captured pages, and add
  database tests that skip without a test database.
- Fix 11 bugs it found in the prototype, the important ones being:
  - a rolled-back nutrition label could still be treated as stored, so later
    menus silently lost their nutrition and allergen data;
  - "Contains:" names it didn't recognize were silently dropped, which could
    lose an allergen;
  - cached labels never expired, so recipe changes would never arrive;
  - errors during recovery, or one bad date header, could stop the whole run;
  - an hours page that was blocked or had changed layout was silently stored
    as "unknown";
  - retries were not backed off and didn't respect rate limiting;
  - nothing stopped two runs from overlapping.
- **Scraping etiquette.** Manual, low-volume runs only (1 request/s,
  identifying User-Agent, cached labels) until NC State Dining grants
  permission for scheduled runs.
- **Licensing.** The data is mostly facts. The frontend should show the
  dining site's allergy disclaimer and link to the source. Our repo has no
  LICENSE file; that's a team decision. The new dependencies are permissively
  licensed (httpx2, BeautifulSoup, lxml, tzdata, BSD/MIT/Apache) and psycopg is
  LGPL, which is fine for use as a library.
- It asked three questions: database access style, label cache scope, and
  which Postgres to test against. A local PostgreSQL 18 service already uses
  port 5432, so the Docker database would conflict with it.

## 3. Human review

- **"Isn't database access outlined in our architecture diagram?"** The
  AI checked the report and the poster. Neither names an ORM; they only fix a
  data-access layer, PostgreSQL, and single writer per table.
- **"What are the pros and cons of psycopg and SQL migrations?"** The AI
  listed them. The main risk was column names drifting between ingestion and
  the API.
- **"What is the more stable and desired design? The skeleton was only a base
  setup."** Once told the skeleton wasn't a deliberate choice, the AI changed
  its recommendation to **SQLAlchemy 2.0 + Alembic in a shared `db/` package**.
  That gives one schema definition that both the API and ingestion import.
  Accepted.
- **Label cache scope:** chose **per location**. The prototype shared one label
  across all halls by dish name, but two halls can serve different recipes
  under the same name.
- **"What's the best long-term choice for the test database?"** The AI
  recommended Docker Postgres for everyone, with the host port configurable in
  `.env`. That avoids the clash with the local Postgres. Accepted.
- **"If it records 7 days out, should we ingest every day? I'm worried about
  menu changes."** We interrupted implementation to ask this. The AI
  recommended re-scraping all 7 days every run, since menu requests are cheap
  and labels are cached. It also suggested counting changed menus per run, so we
  learn how often menus really change. Both accepted: `--days 7` is the default,
  and runs report `menus_changed`.
- Docker couldn't start because WSL wasn't installed. We installed WSL and
  rebooted rather than fall back to the local Postgres.

## 4. Final version

```
proj_2/
├── db/                       NEW: shared schema
│   ├── models.py             6 tables, each naming its writer
│   ├── session.py, migrate.py
│   └── migrations/           Alembic; 0001 creates the ingestion tables
├── ingestion/
│   ├── config.py             URLs, politeness, 7-day label cache age
│   ├── fetch.py              polite client: 1 req/s, backoff, Retry-After
│   ├── parse.py              HTML → dataclasses
│   ├── normalize.py          allergen/diet keys, unit → hours-page map
│   ├── write.py              Postgres upserts, change detection, removed-menu cleanup
│   ├── run.py                CLI + ingest_runs records + advisory lock
│   └── tests/                43 tests + captured pages
├── docker-compose.yml        db host port from POSTGRES_PORT
└── README.md, .env.example   setup, migrations, CLI options, scraping etiquette
```

The safety rules are kept from the prototype:
- A label is attached only if its title matches the item.
- Allergens are the icon traits plus the label's "Contains:" list.
- Unrecognized names are stored and flagged.
- Missing nutrients stay NULL and are listed in `missing_fields`.

Not built: a scheduler, a Docker service for ingestion, and any full scrape.

## 5. Verification

Checks the AI ran and reported:

- `pytest ingestion`: **43 passed** against Postgres 16 in Docker. This
  includes a test that the migrations match `models.py`, and an end-to-end run
  on captured pages covering:
  - the label mismatch guard;
  - the rolled-back-label regression;
  - change detection;
  - the one-run-at-a-time lock.
- `alembic upgrade head --sql` rendered offline. This found and fixed a bug
  where a space in the checkout path ("csc 510") broke Alembic's import path.
- Live run 1, `--units 1 --days 1 --no-nutrition`: `ok`, 4 menus, 254 items,
  7 requests, 0 errors.
- Live run 2, `--units 1 --days 1` with labels: `ok`, 160 labels fetched,
  94 reused, **0 label mismatches**, 167 requests in 2 min 46 s. All 4 menus
  were correctly reported unchanged.
- What the stored rows showed:
  - every item had a label;
  - Potassium (93 labels) and Cholesterol (75) were the most often missing;
  - 126 of 254 items have no allergen icons, so the filter engine must treat
    "no label" as incomplete;
  - Fountain's hours today were stored as open 7:00am–9:00pm.

Human checks (tick what was actually done):

- [x] Read through the diff on `feature/ingestion`
- [x] Ran `pytest ingestion` locally
- [x] Spot-checked a few items and labels against the NetNutrition site
