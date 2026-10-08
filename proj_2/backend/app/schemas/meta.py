"""Response models about the data itself."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class Freshness(BaseModel):
    last_run_finished_at: datetime | None   # null = no completed ingestion run yet
    last_run_status: Literal["ok", "partial"] | None
    stale: bool
    stale_after_hours: int
