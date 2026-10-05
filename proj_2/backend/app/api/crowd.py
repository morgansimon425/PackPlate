"""Routes for student crowd reports (not busy / moderate / crowded).

Calls services.crowd; no aggregation logic lives here.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/crowd", tags=["crowd"])
