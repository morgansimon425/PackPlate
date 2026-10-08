# 03 — Backend database connection and read API

| | |
|---|---|
| **Author** | Moe Ko |
| **Date** | 2026-10-07 |
| **Tool / model** | Claude Code (VS Code extension), Claude Opus 5.5 |

## 1. Request

Two requests in one session:

1. "Analyze [Ethan's] work and then come up with a plan for how to go
   forward with implementing the backend." The tech stack on our poster
   was given as a constraint.
2. After the team reviewed that plan: build parts 1 (foundation) and 2
   (read API). Constraints:
   - No GitHub Actions yet.
   - Show all of a day's menus at once; don't map meals to times yet.

## 2. AI proposal

**Review of `feature/ingestion`.** The AI ran Ethan's tests: 43 passed
against Postgres 16 in Docker. It raised five points:

- NetNutrition's `robots.txt` disallows all crawlers, and the branch never
  mentions it.
- Only the 24 NetNutrition units become `locations`. Places listed only on
  dining.ncsu.edu (Chick-fil-A, the markets, and others) are missing.
- The backend Docker image couldn't include the shared `db/` package.
- Hours that run past midnight are stored on the previous day.
- There is no CI.

**Plan.** Six steps:

0. Merge and unblock.
1. Foundation.
2. Read API.
3. Filter engine.
4. Crowd reports.
5. TypeScript types from OpenAPI.
6. M0 eval.

It proposed filter-engine rules but said the team must decide them.

## 3. Human review

- **The team decided to scrape both sites by hand once a day.** This
  settled the robots.txt question for now.
- **"Don't worry about GitHub Actions yet."** CI was dropped from
  part 1.
- **"All the menus should just be displayed at once, don't worry about
  having meal times yet."** The AI had asked whether to map meal names to
  times. Instead, `/locations/{id}/menus` returns every menu for the day.
- _TODO (reviewer): record changes requested in PR review._

## 4. Final version

On branch `feature/backend-api`, built on `feature/ingestion` because it
needs `db/`.

- **Foundation**
  - `app/deps.py` gives one session per request; the engine is created
    lazily, so `/health` works without a database.
  - `/health` also reports whether the schema is up to date (Alembic
    `check_current`).
  - `backend/pytest.ini` puts `proj_2/` on the import path.
  - SQLAlchemy, Alembic and tzdata were added to the backend requirements.
- **Docker.** The backend builds with `proj_2/` as its context and copies
  `db/` into the image. `backend/Dockerfile.dockerignore` replaces
  `backend/.dockerignore`.
- **Read API**, kept to the layering rules:
  - repositories: `locations`, `menus`, `ingest_runs`;
  - schemas: `locations`, `meta`;
  - services: `hours` (open now, including past-midnight windows from the
    previous day), `menus` (meal order), `freshness` (stale after 36 h);
  - routes: `GET /locations`, `/locations/{id}`,
    `/locations/{id}/menus?date=`, and `/freshness`.
  - Time-dependent routes take `?at=`.
  - Unknown hours give `is_open: null`, not closed. An item with no label
    gives `nutrition: null`.
- **Running locally.** From `backend/`, `uvicorn` can't import `db`, so
  the README now says to run from `proj_2/` with `--app-dir backend`.

## 5. Verification

Checks the AI ran and reported:

- `pytest` in `backend/`: **22 passed** against Postgres 16 in Docker
  (11 skip without `TEST_DATABASE_URL`).
- **Mutation checks.** Two deliberate bugs were each caught by 2 tests:
  ignoring the previous day's late hours, and treating unknown hours as
  closed.
- **End to end.**
  - Applied the migrations.
  - Ran Ethan's scraper live:
    `--units 1,3 --days 1 --max-labels 40`, giving `ok`, 331 items,
    52 requests.
  - Started the API and called every route.
  - At 9:35pm both halls showed as closed. Fountain's 7am–9pm and Case's
    split hours matched dining.ncsu.edu.
  - The 404 for an unknown location worked.
  - Two things in the real data:
    - Case lists a Dinner menu although its hours end at 1:30pm.
    - Only 72 of 258 Fountain items had labels, because of the 40-label
      cap on this test run.
- `docker compose build backend` succeeded, and the image imports
  `app.main` and `db.models`.

Human checks (tick what was actually done):

- [ ] Ran the API locally and opened `/docs`
- [ ] Reviewed the code in a PR
