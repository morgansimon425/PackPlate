"""Routes about the data itself, e.g. how fresh the last scrape is."""

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_db
from app.repositories import ingest_runs as ingest_runs_repo
from app.schemas.meta import Freshness
from app.services.freshness import STALE_AFTER_HOURS, is_stale
from app.services.hours import campus_time

router = APIRouter(tags=["meta"])


@router.get("/freshness", response_model=Freshness)
def freshness(at: datetime | None = None, db: Session = Depends(get_db)):
    """When ingestion last finished, and whether the data is stale at `at` (default now)."""
    run = ingest_runs_repo.latest_completed(db)
    finished = run.finished_at if run else None
    return {
        "last_run_finished_at": finished,
        "last_run_status": run.status if run else None,
        "stale": is_stale(finished, campus_time(at)),
        "stale_after_hours": STALE_AFTER_HOURS,
    }
