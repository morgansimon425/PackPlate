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
│   │   ├── deps.py         database session per request
│   │   ├── api/            routes, one file per feature
│   │   │   ├── locations.py    /locations, /locations/{id}, /locations/{id}/menus
│   │   │   ├── meta.py         /freshness
│   │   │   ├── filters.py
│   │   │   └── crowd.py
│   │   ├── schemas/        Pydantic response models
│   │   ├── services/       business logic (no database)
│   │   │   ├── hours.py        open now?, past-midnight windows
│   │   │   ├── menus.py        meal ordering
│   │   │   ├── freshness.py    stale-data rule
│   │   │   ├── filter_engine.py
│   │   │   └── crowd.py
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
  items, nutrition, and ingest runs; the API writes crowd reports only. Each
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

Time-dependent routes take `?at=2026-10-06T12:00:00-04:00` (default now, campus
time), so you can check "open at noon" without waiting for noon. Unknown stays
unknown: `is_open: null` means today's hours aren't known, and `nutrition: null`
means the item has no label, so its allergens come from icons only.

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

**Sources and etiquette.** Menus and nutrition come from NC State's NetNutrition
(`netmenu2.cbord.com`), hours from `dining.ncsu.edu`. The job is deliberately
slow (1 request/s, sequential, identifying User-Agent, labels cached). **Do not schedule it until NC State
Dining has given permission**; run it by hand. The intended schedule once
allowed is once a day at 4am Eastern, re-scraping all 7 days (a cached run is
roughly 10 minutes; the first run, which fills the label cache, takes longer).
The `menus_changed` stat shows how often menus really change.

Known source limits: "Contains Nuts" covers peanuts and tree nuts, and
"Contains Seafood" covers fish and shellfish; the source can't tell them apart.

## 🧪 Tests

```bash
cd backend && pytest          # API; DB tests need TEST_DATABASE_URL
cd .. && pytest ingestion     # pipeline (run from proj_2/); DB tests need TEST_DATABASE_URL
cd frontend && npm run lint   # frontend
```
