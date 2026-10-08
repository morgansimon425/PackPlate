"""How fresh the scraped data is.

The team scrapes by hand once a day, so data is stale once the last
completed run is older than STALE_AFTER_HOURS (default 36: a day plus slack
for a late run).
"""

import os
from datetime import datetime, timedelta

STALE_AFTER_HOURS = int(os.getenv("STALE_AFTER_HOURS", "36"))


def is_stale(last_finished_at: datetime | None, at: datetime) -> bool:
    return last_finished_at is None or at - last_finished_at > timedelta(hours=STALE_AFTER_HOURS)
