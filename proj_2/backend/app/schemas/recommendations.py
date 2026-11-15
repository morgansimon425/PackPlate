
"""Request and response schemas for PackPlate M5 recommendations."""

from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.filters import Profile
from app.schemas.locations import Nutrition


NutritionGoal = Literal[
    "high_protein",
    "lower_calories",
    "lower_sodium",
]


class RecommendationRequest(BaseModel):
    goal: NutritionGoal
    date: Date | None = None
    meal: str | None = None
    profile: Profile | None = None


class RecommendationItem(BaseModel):
    rank: int
    item_id: int
    name: str
    location_id: int
    location_name: str
    meal: str
    meal_periods: list[str]
    nutrition: Nutrition
    reason: str


class RecommendationResponse(BaseModel):
    recommendations: list[RecommendationItem] = Field(default_factory=list)
