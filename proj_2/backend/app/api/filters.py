"""Routes for dietary filtering, single person and group.

Calls services.filter_engine; no filtering logic lives here.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/filters", tags=["filters"])
