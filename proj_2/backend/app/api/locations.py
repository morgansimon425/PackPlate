"""Routes for dining locations: hours, menus, nutrition."""

from fastapi import APIRouter

router = APIRouter(prefix="/locations", tags=["locations"])
