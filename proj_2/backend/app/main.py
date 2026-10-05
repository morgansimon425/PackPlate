"""PackPlate API entry point.

Layers (see proj_1b report, Figure 1):
    api/           presentation  - HTTP routes, one file per feature
    services/      business logic - filter engine, crowd aggregation
    repositories/  data access   - the only layer that talks to Postgres
"""

import os

import psycopg
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import crowd, filters, locations

app = FastAPI(title="PackPlate API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(locations.router)
app.include_router(filters.router)
app.include_router(crowd.router)


@app.get("/health")
def health():
    """Report whether the API is up and whether it can reach the database."""
    try:
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=2):
            db = "ok"
    except Exception:
        db = "unreachable"
    return {"status": "ok", "db": db}
