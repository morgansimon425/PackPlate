# 01 — Project 2 scaffolding

| | |
|---|---|
| **Author** | Ethan Goodman, Moe Ko, Morgan Simon, Savanah Hendzel |
| **Date** | 2026-10-05 |
| **Tool / model** | Claude Code (VS Code extension), Claude Opus 5.5 |

## 1. Request

Create a skeleton for Project 2 so all four team members know where to
start: a Next.js + TypeScript frontend and a minimal FastAPI backend,
following the architecture in the
[Project 1b report](../../../proj_1b/Project_1b_Report.pdf) (Figure 1)
and the tech stack on our poster. The AI was told to **explain its plan
before creating anything**. Everything goes under `proj_2/`.

Context given to the AI: the 1b report, the poster, and
`proj_1b/prompts/architecture_critique.txt`.

## 2. AI proposal

The first plan included:

- `backend/` with a full layered structure: `config.py`, `db.py` with a
  connection pool, SQLAlchemy models (`location`, `menu_item`,
  `nutrition`, `crowd_report`), Pydantic schemas, Alembic migrations,
  `pyproject.toml`, a Dockerfile
- One router and one service per feature (locations, filters, crowd),
  so filtering and crowd reports don't share a file. This was the main
  finding of our 1b architecture critique.
- `ingestion/` as a separate pipeline (fetch → parse → normalize → write)
- `frontend/` from `create-next-app`, plus an `npm run gen:api` script
  generating TypeScript types from FastAPI's OpenAPI schema
- `docker-compose.yml` running db, api, web, and ingestion

## 3. Human review

- **"We don't need any real code, just basic scaffolding. Is this too
  intrusive?"** The AI agreed: models, migrations, type generation, and
  the connection pool would lock in decisions the team should make while
  building. All were removed. Folders and files were kept, with
  docstrings saying what belongs in each.
- **"Shouldn't the frontend have the initial Next.js + TypeScript
  setup?"** The trimmed plan had shortened this to "stock
  create-next-app". The AI listed what that produces (`tsconfig.json`,
  `package.json`, App Router pages) and added placeholder `/locations`
  and `/group` routes.
- **"Will this set everything up for our tech stack?"** Checking against
  the poster found two gaps: PostgreSQL ran but nothing connected to it,
  and Docker ran only the database. Fixed by adding `psycopg`, making
  `/health` report database status, and adding Dockerfiles for the
  backend and frontend.
- Tailwind was left out, since we hadn't chosen a styling approach.

## 4. Final version

```
proj_2/
├── docker-compose.yml   db + backend + frontend
├── .env.example
├── backend/             FastAPI: main.py (/health), api/, services/, repositories/, tests/
├── ingestion/           fetch.py, parse.py, normalize.py, write.py, run.py, tests/
└── frontend/            create-next-app (TS, ESLint, App Router, src/) + /locations, /group
```

No feature logic, models, or migrations. See [proj_2/README.md](../../README.md).

## 5. Verification

Checks the AI ran and reported:

- Backend: `pytest` 1 passed. The test client warned that `httpx` is
  deprecated, so `requirements.txt` was switched to `httpx2`; the rerun
  passed with no warning.
- Ingestion: `pytest ingestion` 1 passed; `python -m ingestion.run`
  runs end to end.
- Frontend: `npm run lint` clean; `npm run build` produced `/`,
  `/locations`, `/group`.
- API run directly: `/health` returned `{"status":"ok","db":"unreachable"}`,
  as expected with no Postgres running.
- `docker compose config` is valid.

Human checks (tick what was actually done):

- [x] Whole team reviewed the `backend/`, `frontend/`, and `ingestion/`
  folders and their structure against our 1b architecture and tech stack
