"""PackPlate API entry point.

Layers (see proj_1b report, Figure 1):
    api/           presentation  - HTTP routes, one file per feature
    schemas/       response models shared by routes
    services/      business logic - hours, filter engine, crowd aggregation
    repositories/  data access   - the only layer that queries Postgres

The tables live in proj_2/db (shared with ingestion), so proj_2/ must be on
the Python path: see the README.
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import crowd, filters, locations, meta
from app.deps import get_engine
from db.migrate import check_current

app = FastAPI(title="PackPlate API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(locations.router)
app.include_router(meta.router)
app.include_router(filters.router)
app.include_router(crowd.router)


@app.get("/health")
def health():
    """Whether the API is up, can reach the database, and has the expected schema.

    schema is "current", "outdated" (run the Alembic migrations), or null
    when the database is unreachable.
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        return {"status": "ok", "db": "unreachable", "schema": None}
    try:
        check_current(engine)
        schema = "current"
    except RuntimeError:
        schema = "outdated"
    return {"status": "ok", "db": "ok", "schema": schema}
