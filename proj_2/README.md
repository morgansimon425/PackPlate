# PackPlate — Project 2 (Implementation)

Layered client-server monolith with a separate ingestion job, as designed in
[proj_1b](../proj_1b/Project_1b_Report.pdf) (Figure 1).

## 📁 Structure

```
proj_2/
├── docker-compose.yml      db + backend + frontend
├── .env.example            copy to .env
│
├── db/                     shared schema (SQLAlchemy 2.0 + Alembic)
│   ├── models.py           every table, and which component writes it
│   ├── session.py          engine/sessions from DATABASE_URL
│   └── migrations/         Alembic versions
│
├── backend/                FastAPI (Python)
│   ├── app/
│   │   ├── main.py         app setup, router wiring, GET /health
│   │   ├── deps.py         database session per request; current_user / optional_user
│   │   ├── api/            routes, one file per feature
│   │   │   ├── locations.py    /locations, /locations/{id}, /locations/{id}/menus
│   │   │   ├── meta.py         /freshness
│   │   │   ├── filters.py      /filters/locations/{id}/menus, /filters/group
│   │   │   ├── crowd.py        /crowd/{id}
│   │   │   ├── auth.py         /auth/register, /auth/login, /auth/logout, /auth/me
│   │   │   └── chat_room.py    /chat/rooms, /chat/invitations, /chat/open-to-chat (M4)
│   │   ├── schemas/        Pydantic response models
│   │   ├── services/       business logic (no database)
│   │   │   ├── hours.py        open now?, past-midnight windows
│   │   │   ├── menus.py        meal ordering
│   │   │   ├── freshness.py    stale-data rule
│   │   │   ├── filter_engine.py  fits / conflicts / incomplete rules
│   │   │   ├── crowd.py        crowd level from recent reports, report throttle
│   │   │   ├── auth.py         username/password rules, session tokens, login limiter
│   │   │   └── passwords.py    scrypt password hashing
│   │   └── repositories/   data access (only layer that queries Postgres)
│   └── tests/              pytest; API tests need TEST_DATABASE_URL
│
├── ingestion/              scraper job: fetch → parse → normalize → write
│   ├── config.py           source URLs, politeness, cache age
│   ├── fetch.py            the only code that touches the network
│   ├── parse.py            HTML → dataclasses (no I/O)
│   ├── normalize.py        dietary/allergen labels, unit → hours-page map
│   ├── write.py            only writer of the ingestion tables
│   ├── run.py              orchestration + CLI + ingest_runs records
│   └── tests/              offline parser tests on captured pages + DB tests
│
└── frontend/               Next.js + React + TypeScript
    └── src/
        ├── app/            pages: /, /locations, /group
        ├── components/     shared UI
        └── lib/api.ts      backend base URL
```

### Rules of the road

- **One feature, one file per layer.** Filtering and crowd reports have
  separate route and service files so they don't collide.
- **Routes stay thin.** Logic goes in `services/`, SQL goes in `repositories/`.
- **Single writer per table.** `ingestion/` writes locations, hours, menus,
  items, nutrition, and ingest runs; the API writes crowd reports, users, and
  sessions. Each
  model in `db/models.py` names its writer.
- **Schema changes go through Alembic.** Edit `db/models.py`, then
  `alembic -c db/alembic.ini revision --autogenerate -m "what changed"`, review
  the generated file, and commit both. A test fails if they drift apart.

## 🚀 Running

### Everything in Docker

```bash
cp .env.example .env
docker compose up --build
```

- Frontend: http://localhost:3000
- API: http://localhost:8000 (docs at `/docs`, health at `/health`)

### Locally (for development)

Start just the database, then create the tables:

```bash
docker compose up db
alembic -c db/alembic.ini upgrade head      # from proj_2/, with DATABASE_URL set
```

If port 5432 is already taken (e.g. a local Postgres install), set
`POSTGRES_PORT=5433` in `.env` and use 5433 in `DATABASE_URL` /
`TEST_DATABASE_URL`.

Backend (run from `proj_2/`, so both `backend/app` and the shared `db/` import):

```bash
python -m venv backend/.venv
source backend/.venv/bin/activate      # Windows: backend\.venv\Scripts\activate
pip install -r backend/requirements.txt
export DATABASE_URL=postgresql://packplate:packplate@localhost:5432/packplate
python -m uvicorn app.main:app --app-dir backend --reload
```

| Endpoint | Returns |
|---|---|
| `GET /health` | API up; database `ok` / `unreachable`; schema `current` / `outdated` |
| `GET /freshness` | when ingestion last finished (`ok` or `partial`), and `stale` if that was over 36 h ago (`STALE_AFTER_HOURS`) |
| `GET /locations` | every location: today's hours, `is_open`, `closes_at`, `opens_next_at` |
| `GET /locations/{id}` | the same, plus 7 days of hours and the menus listed from today on |
| `GET /locations/{id}/menus?date=YYYY-MM-DD` | every menu that day (default today) with items, allergens, diets, and nutrition |
| `POST /filters/locations/{id}/menus?date=` | the same menus, each item checked against every profile in the body: `fits`, `conflicts`, or `incomplete`, with reasons |
| `POST /filters/group?at=` | every location for a group: per profile how many items fit, and `everyone_fits`; ranked everyone-fits first, then open, then name |
| `POST /crowd/{id}` | body `{"level": "not_busy" \| "moderate" \| "crowded"}`; returns the new crowd level (201), or 429 if this client reported this location in the last minute |
| `POST /auth/register` | body `{"username", "password"}`; creates an account and logs in (201), 400 if not allowed, 409 if taken |
| `POST /auth/login` | same body; logs in (sets the session cookie), 401 if wrong, 429 after 10 failed tries in 15 min |
| `POST /auth/logout` | ends this browser's session (204) |
| `GET /auth/me` | the logged-in account `{id, username, open_to_chat, created_at}`, or 401. `PATCH` with `{"open_to_chat": bool}` changes that setting (off by default); `DELETE` with `{"password"}` deletes the account |
| `/chat/...` | group chat for logged-in users (401 otherwise): rooms, invitations, messages, and the Open to Chat list; see `docs/api.md` |

Time-dependent routes take `?at=2026-10-06T12:00:00-04:00` (default now, campus
time), so you can check "open at noon" without waiting for noon. Unknown stays
unknown: `is_open: null` means today's hours aren't known, and `nutrition: null`
means the item has no label, so its allergens come from icons only.

`/locations` and `/locations/{id}` also carry `crowd`: the level from reports in
the last 30 minutes (`CROWD_WINDOW_MINUTES`), newer reports counting more, or
`level: null` when nobody has reported. Reports are stored without anything about
the reporter.

**Filtering.** The body is `{"profiles": [...]}`, 1–10 profiles, each with any of
`name`, `avoid` (allergen keys: dairy, egg, gluten, nuts, pork, seafood, sesame,
soy), `diets` (halal, vegan, vegetarian), `min_protein_g`, `max_calories`,
`max_sodium_mg`. Unknown keys or fields are a 422, never ignored. Profiles are
not stored. The rules are at the top of `services/filter_engine.py`; in short, an
item only `fits` an allergy when it has a nutrition label and no unrecognized
traits, and only fits a diet when it is tagged with it.

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Ingestion (from `proj_2/`, with `DATABASE_URL` set and migrations applied):

```bash
pip install -r ingestion/requirements.txt
python -m ingestion.run --units 1 --days 1 --no-nutrition   # quick check: Fountain, today
python -m ingestion.run                                     # everything: 24 units, 7 days, labels
```

| Option | Meaning |
|---|---|
| `--units 1,2,3` | only these NetNutrition units (default: all) |
| `--days N` | days starting today, America/New_York (default and max 7) |
| `--no-nutrition` | skip nutrition labels (items are then "data incomplete" for allergy checks) |
| `--max-labels N` | cap label requests this run |
| `--refresh-labels` | re-fetch labels even if stored recently (otherwise after 7 days) |
| `--delay S` | seconds between requests (default 1.0, minimum 0.5) |

Every run writes an `ingest_runs` row (status `ok` / `partial` / `failed`, stats,
errors) and prints a summary. A problem in one location or menu is recorded and
the job moves on. Only one run can happen at a time.

**Reviewing diet tags.** When an item's ingredients contradict its diet tag (for
example, tagged vegetarian but listing chicken), the run queues it for review and
the summary shows `label_reviews_pending`. To decide:

```bash
python -m ingestion.review_labels                                   # list pending reviews
python -m ingestion.review_labels --approve 1 --by NAME --reason "..." # remove the tags
python -m ingestion.review_labels --reject 1 --by NAME --reason "..."  # keep them
```

Approved tags are removed from the API's menus and filters; NC State's data is kept
as published.

**Sources and etiquette.** Menus and nutrition come from NC State's NetNutrition
(`netmenu2.cbord.com`), hours from `dining.ncsu.edu`. The job is deliberately
slow (1 request/s, sequential, identifying User-Agent, labels cached). NC State
Dining has allowed scraping **at most once or twice a day**. The `menus_changed`
stat shows how often menus really change.

**Daily schedule.** `.github/workflows/scrape.yml` runs the job once a day at
4am Eastern Standard Time (5am during daylight saving time; GitHub schedules in
UTC) and opens a GitHub issue if a run fails, data goes stale, or diet tags
are waiting for review. It needs the repo secret `SUPABASE_URL` and only runs
from `main`; until then, run the job by hand.

Known source limits: "Contains Nuts" covers peanuts and tree nuts, and
"Contains Seafood" covers fish and shellfish; the source can't tell them apart.

### Shared database (Supabase)

The scraped data is stored in a shared Supabase Postgres database.

1. Request the connection string from the team.
2. Before starting the backend, set `DATABASE_URL` to that string:

   ```bash
   export DATABASE_URL="<connection string>"   # PowerShell: $env:DATABASE_URL = "<connection string>"
   ```

Notes:

- Tests empty their database, so keep `TEST_DATABASE_URL` pointed at your local
  Docker database, not Supabase.
- The scraper is run by one team member, so there's no need to run
  `ingestion.run` against this database.

## 🧪 Tests

```bash
cd backend && pytest          # API; DB tests need TEST_DATABASE_URL
cd .. && pytest ingestion     # pipeline (run from proj_2/); DB tests need TEST_DATABASE_URL
pytest eval                   # M0 eval (run from proj_2/); no database needed
python -m eval.m0             # rerun M0 and write eval/results.json (--check: compare instead)
cd frontend && npm run lint   # frontend
```
