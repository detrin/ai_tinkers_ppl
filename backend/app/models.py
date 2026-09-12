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
    """A traveller. `preferences` and `constraints` are what the Slack agent
    extracts from the conversation; the planner reads them back."""

    id: str
    display_name: str
    joined_at: float
    online: bool = False
    position: MemberPosition | None = None
    # Filled in by the API so the group can see how far apart everyone is.
    distance_to_meeting_m: float | None = None
    distance_to_next_stop_m: float | None = None
    # Identity on the surface the traveller arrived from.
    slack_user_id: str | None = None
    budget: float | None = None
    currency: str = "EUR"
    preferences: list[str] = []
    constraints: list[str] = []


class SlackThread(BaseModel):
    """Where a trip is being discussed.

    Identified by workspace, channel and thread ids, never by channel name:
    names are renamed freely and would silently remap a trip.
    """

    workspace_id: str
    channel_id: str
    thread_id: str

    @property
    def key(self) -> str:
        return f"{self.workspace_id}/{self.channel_id}/{self.thread_id}"


class TripMessage(BaseModel):
    id: str
    source: Literal["slack", "web"]
    source_message_id: str | None = None
    author_id: str | None = None
    author_name: str | None = None
    text: str
    created_at: float


class Proposal(BaseModel):
    """An itinerary put forward for the group to accept or reject.

    A proposal is never the group's plan. Only approving one makes it so, which
    is the approval boundary every consequential write goes through.
    """

    id: str
    status: Literal["proposed", "approved", "declined"] = "proposed"
    created_at: float
    created_by: str | None = None
    decided_at: float | None = None
    decided_by: str | None = None
    plan: "Plan"
    estimated_cost: float | None = None
    currency: str = "EUR"
    assumptions: list[str] = []
    note: str = ""


class MediaItem(BaseModel):
    id: str
    filename: str
    category: Literal["landmark", "food", "group_photo", "ticket", "booking", "receipt", "other"]
    note: str = ""
    location: str | None = None
    day: int | None = None
    created_at: float
    created_by: str | None = None


class Expense(BaseModel):
    id: str
    title: str
    amount: float
    currency: str = "EUR"
    paid_by: str
    participant_ids: list[str]
    shares: dict[str, float]
    status: Literal["proposed", "approved", "declined"] = "proposed"
    created_at: float
    decided_at: float | None = None
    decided_by: str | None = None
    media_id: str | None = None


class PollOption(BaseModel):
    id: str
    label: str
    voter_ids: list[str] = []


class TripPoll(BaseModel):
    id: str
    question: str
    options: list[PollOption]
    status: Literal["open", "closed"] = "open"
    winner_option_id: str | None = None
    created_at: float


class PackingList(BaseModel):
    personal: list[str]
    shared: list[str]
    assumptions: list[str] = []


class LocalSuggestion(BaseModel):
    query: str
    city: str
    search_prompt: str


class MemoryEntry(BaseModel):
    id: str
    title: str
    description: str
    occurred_at: float
    media_ids: list[str] = []


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
    slack_thread: SlackThread | None = None
    messages: list[TripMessage] = []
    proposals: list[Proposal] = []
    media: list[MediaItem] = []
    expenses: list[Expense] = []
    polls: list[TripPoll] = []
    memories: list[MemoryEntry] = []


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


class SlackThreadRequest(BaseModel):
    """Find-or-create a trip for a Slack thread. `city` and `name` are only
    used when the thread has no trip yet."""

    workspace_id: str = Field(min_length=1, max_length=64)
    channel_id: str = Field(min_length=1, max_length=64)
    thread_id: str = Field(min_length=1, max_length=64)
    name: str = Field(default="Trip", min_length=1, max_length=80)
    city: str = Field(min_length=1, max_length=120)
    interests: list[str] = []


class TravelerPreferenceRequest(BaseModel):
    """Upsert. Omitted fields are left alone, so the agent can report one
    detail it heard without erasing everything else it knew."""

    slack_user_id: str | None = None
    budget: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    preferences: list[str] | None = None
    constraints: list[str] | None = None


class AppendMessageRequest(BaseModel):
    source: Literal["slack", "web"] = "slack"
    source_message_id: str | None = Field(default=None, max_length=128)
    author_id: str | None = Field(default=None, max_length=64)
    author_name: str | None = Field(default=None, max_length=80)
    text: str = Field(min_length=1, max_length=8000)


class ProposalRequest(BaseModel):
    interests: list[str] | None = None
    max_stops: int = Field(default=5, ge=1, le=12)
    transport: Transport | None = None
    radius_m: int | None = Field(default=None, ge=250, le=20_000)
    created_by: str | None = None
    estimated_cost: float | None = Field(default=None, ge=0)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    assumptions: list[str] = []
    note: str = Field(default="", max_length=500)
    # Replaying the same Slack interaction must not stack up proposals.
    idempotency_key: str | None = Field(default=None, max_length=128)


class DecisionRequest(BaseModel):
    decided_by: str | None = Field(default=None, max_length=80)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class AskResponse(BaseModel):
    question: str
    answer: str


class MediaRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=240)
    category: Literal["landmark", "food", "group_photo", "ticket", "booking", "receipt", "other"] | None = None
    note: str = Field(default="", max_length=1000)
    location: str | None = Field(default=None, max_length=160)
    day: int | None = Field(default=None, ge=1, le=60)
    created_by: str | None = Field(default=None, max_length=80)


class ExpenseRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    amount: float = Field(gt=0)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    paid_by: str = Field(min_length=1, max_length=80)
    participant_ids: list[str] = Field(min_length=1)
    media_id: str | None = None


class PollRequest(BaseModel):
    question: str = Field(min_length=1, max_length=300)
    options: list[str] = Field(min_length=2, max_length=10)


class VoteRequest(BaseModel):
    option_id: str
    voter_id: str


class MemoryRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    occurred_at: float | None = None
    media_ids: list[str] = []


class PackingRequest(BaseModel):
    days: int = Field(default=2, ge=1, le=60)
    weather: str = Field(default="unknown", max_length=120)


Group.model_rebuild()
