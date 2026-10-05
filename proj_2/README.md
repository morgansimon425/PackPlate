# PackPlate — Project 2 (Implementation)

Layered client-server monolith with a separate ingestion job, as designed in
[proj_1b](../proj_1b/Project_1b_Report.pdf) (Figure 1).

## 📁 Structure

```
proj_2/
├── docker-compose.yml      db + backend + frontend
├── .env.example            copy to .env
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
├── ingestion/              scheduled scraper: fetch → parse → normalize → write
│   ├── fetch.py
│   ├── parse.py
│   ├── normalize.py        dietary/allergen labels
│   ├── write.py            only writer of menu + nutrition tables
│   ├── run.py
│   └── tests/
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
- **Single writer per table.** `ingestion/` writes menus and nutrition; the API
  writes crowd reports only.

## 🚀 Running

### Everything in Docker

```bash
cp .env.example .env
docker compose up --build
```

- Frontend: http://localhost:3000
- API: http://localhost:8000 (docs at `/docs`, health at `/health`)

### Locally (for development)

Start just the database:

```bash
docker compose up db
```

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

Ingestion (from `proj_2/`):

```bash
pip install -r ingestion/requirements.txt
python -m ingestion.run
```

## 🧪 Tests

```bash
cd backend && pytest          # API
cd .. && pytest ingestion     # pipeline (run from proj_2/)
cd frontend && npm run lint   # frontend
```
