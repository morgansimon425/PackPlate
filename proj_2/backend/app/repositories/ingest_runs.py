"""Queries for ingestion runs, used to tell how fresh the data is. Read-only."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import IngestRun


def latest_completed(db: Session) -> IngestRun | None:
    """The most recent run that finished with data: status "ok" or "partial"."""
    return db.scalars(
        select(IngestRun)
        .where(IngestRun.status.in_(["ok", "partial"]), IngestRun.finished_at.is_not(None))
        .order_by(IngestRun.finished_at.desc())
        .limit(1)
    ).first()
