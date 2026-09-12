"""Wire schemas. These are what the mobile/web client sees."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Transport = Literal["foot", "bike", "car"]


# --------------------------------------------------------------------------
# Geography
# --------------------------------------------------------------------------
class City(BaseModel):
    name: str
    display_name: str
    lat: float
    lon: float
    country: str | None = None


class Point(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


# --------------------------------------------------------------------------
# Places
# --------------------------------------------------------------------------
class Place(BaseModel):
    id: str
    name: str
    lat: float
    lon: float
    category: str
    tags: list[str] = []
    base_score: float = 0.0
    address: str | None = None
    website: str | None = None
    wikidata: str | None = None
    opening_hours: str | None = None


class RankedPlace(Place):
    score: float = 0.0
    reason: str = ""
    suggested_minutes: int = 45
    ranked_by: Literal["ai", "heuristic"] = "heuristic"


# --------------------------------------------------------------------------
# Group and members
# --------------------------------------------------------------------------
class MemberPosition(BaseModel):
    lat: float
    lon: float
    accuracy_m: float | None = None
    updated_at: float


class Member(BaseModel):
    id: str
    display_name: str
    joined_at: float
    online: bool = False
    position: MemberPosition | None = None
    # Filled in by the API so the group can see how far apart everyone is.
    distance_to_meeting_m: float | None = None
    distance_to_next_stop_m: float | None = None


class Group(BaseModel):
    id: str
    name: str
    join_code: str
    city: City
    created_at: float
    interests: list[str] = []
    transport: Transport = "foot"
    members: list[Member] = []
    meeting_point: Point | None = None
    plan: "Plan | None" = None


# --------------------------------------------------------------------------
# Itinerary
# --------------------------------------------------------------------------
class Leg(BaseModel):
    from_index: int  # -1 means "from the meeting point"
    to_index: int
    distance_m: float
    duration_s: float


class Stop(BaseModel):
    order: int
    place: RankedPlace
    distance_from_previous_m: float
    travel_seconds_from_previous: float
    distance_from_meeting_m: float


class Plan(BaseModel):
    generated_at: float
    transport: Transport
    meeting_point: Point
    stops: list[Stop]
    legs: list[Leg]
    total_distance_m: float
    total_travel_seconds: float
    total_visit_seconds: float
    routing_provider: Literal["openrouteservice", "osrm", "straight-line"]
    ranked_by: Literal["ai", "heuristic"]
    summary: str = ""


# --------------------------------------------------------------------------
# Requests
# --------------------------------------------------------------------------
class CreateGroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    city: str = Field(min_length=1, max_length=120)
    interests: list[str] = []
    transport: Transport = "foot"


class JoinGroupRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=60)
    join_code: str | None = None


class PositionRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    accuracy_m: float | None = None


class PlanRequest(BaseModel):
    interests: list[str] | None = None
    max_stops: int = Field(default=5, ge=1, le=12)
    transport: Transport | None = None
    radius_m: int | None = Field(default=None, ge=250, le=20_000)
    start_from: Point | None = None  # override the computed meeting point


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class AskResponse(BaseModel):
    question: str
    answer: str


Group.model_rebuild()
