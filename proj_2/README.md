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
│   │   ├── api/            routes, one file per feature
│   │   │   ├── locations.py
│   │   │   ├── filters.py
│   │   │   └── crowd.py
│   │   ├── services/       business logic
│   │   │   ├── filter_engine.py
│   │   │   └── crowd.py
│   │   └── repositories/   data access (only layer that queries Postgres)
│   └── tests/              pytest
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

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export DATABASE_URL=postgresql://packplate:packplate@localhost:5432/packplate
uvicorn app.main:app --reload
```

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

> When the API starts reading these tables, `backend/Dockerfile` must also copy
> `db/` (it currently copies only `app/`).

## 🧪 Tests

```bash
cd backend && pytest          # API
cd .. && pytest ingestion     # pipeline (run from proj_2/); DB tests need TEST_DATABASE_URL
cd frontend && npm run lint   # frontend
```
