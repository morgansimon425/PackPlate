"""Ingestion settings. Overridable ones come from environment variables."""

import os
from zoneinfo import ZoneInfo  # on Windows this needs the tzdata package

CAMPUS_TZ = ZoneInfo("America/New_York")

NETNUTRITION_BASE = "https://netmenu2.cbord.com/NetNutrition/ncstate-dining"
DINING_SITE_BASE = "https://dining.ncsu.edu"

# Stay slow, sequential, and identifiable.
USER_AGENT = "PackPlate/0.1 (NC State CSC 510 student project; +https://github.com/morgansimon425/PackPlate)"
REQUEST_DELAY_SECONDS = float(os.getenv("SCRAPE_DELAY", "1.0"))
MIN_DELAY_SECONDS = 0.5  # floor for --delay / SCRAPE_DELAY, so a typo can't hammer the sites
REQUEST_ATTEMPTS = 3
MAX_RETRY_AFTER_SECONDS = 60

# NetNutrition lists 7 days of menus; each run re-scrapes them all to catch edits.
DEFAULT_DAYS = 7
MAX_DAYS = 7

# Labels older than this are fetched again, so recipe and allergen changes reach us.
LABEL_MAX_AGE_DAYS = int(os.getenv("LABEL_MAX_AGE_DAYS", "7"))
