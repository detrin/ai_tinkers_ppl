"""Cross-surface trip state: the Slack thread mapping, traveller preferences,
the message log, and the itinerary approval boundary.

These are the operations GROUP_TRAVEL_AGENTS.md names under "Cross-surface
synchronization". Slack (apps/channel) and the web app both go through here,
so neither surface holds state the other cannot see.

Two rules hold throughout:

* A proposal is not a plan. Only approving one changes what the group is doing,
  and declining writes no itinerary at all.
* Slack redelivers. Every write here is idempotent on a caller-supplied id, so
  a replayed event returns the original record instead of making a second one.
"""
from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, HTTPException, Query, Response

from ..hub import hub
from ..models import (
    AppendMessageRequest,
    DecisionRequest,
    Group,
    Member,
    PlanRequest,
    Proposal,
    ProposalRequest,
    SlackThread,
    SlackThreadRequest,
    TravelerPreferenceRequest,
    TripMessage,
)
from ..services import geocode, planner
from ..services import places as places_service
from ..store import store

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["trips"])


def _require_group(group_id: str) -> Group:
    group = store.get(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="group not found")
    return group


# ---------------------------------------------------------------------------
# Slack thread <-> trip
# ---------------------------------------------------------------------------
@router.get("/trips/by-slack-thread", response_model=Group)
async def find_trip_by_slack_thread(
    workspace_id: str = Query(min_length=1),
    channel_id: str = Query(min_length=1),
    thread_id: str = Query(min_length=1),
) -> Group:
    group = store.get_by_slack_thread(
        SlackThread(
            workspace_id=workspace_id, channel_id=channel_id, thread_id=thread_id
        )
    )
    if group is None:
        raise HTTPException(status_code=404, detail="no trip for that Slack thread")
    return planner.annotate_members(group)


@router.post("/trips/by-slack-thread", response_model=Group)
async def create_trip_from_slack_thread(
    request: SlackThreadRequest, response: Response
) -> Group:
    """Find or create. Calling this on every mention is safe and expected:
    the second call returns the trip the first one made."""
    thread = SlackThread(
        workspace_id=request.workspace_id,
        channel_id=request.channel_id,
        thread_id=request.thread_id,
    )

    existing = store.get_by_slack_thread(thread)
    if existing is not None:
        response.status_code = 200
        return planner.annotate_members(existing)

    try:
        city = await geocode.resolve_city(request.city)
    except geocode.GeocodeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    group = await store.create_group(
        name=request.name,
        city=city,
        interests=request.interests,
        transport="foot",
        slack_thread=thread,
    )
    response.status_code = 201
    return group


# ---------------------------------------------------------------------------
# Travellers
# ---------------------------------------------------------------------------
@router.patch(
    "/groups/{group_id}/members/{member_id}/preferences", response_model=Member
)
async def upsert_traveler_preference(
    group_id: str, member_id: str, request: TravelerPreferenceRequest
) -> Member:
    """What the agent heard about one traveller. Merges, so reporting a single
    new constraint does not erase what was already known."""
    _require_group(group_id)
    member = await store.upsert_traveler(
        group_id,
        member_id,
        slack_user_id=request.slack_user_id,
        budget=request.budget,
        currency=request.currency,
        preferences=request.preferences,
        constraints=request.constraints,
    )
    if member is None:
        raise HTTPException(status_code=404, detail="member not found in this group")

    await hub.broadcast(
        group_id,
        {"type": "traveler", "member": member.model_dump(mode="json")},
    )
    return member


# ---------------------------------------------------------------------------
# The message log
# ---------------------------------------------------------------------------
@router.post("/groups/{group_id}/messages", response_model=TripMessage)
async def append_message(
    group_id: str, request: AppendMessageRequest, response: Response
) -> TripMessage:
    """Records one message against the trip. A message carrying a
    source_message_id is stored once; a redelivery returns the original and
    answers 200 rather than 201."""
    _require_group(group_id)
    message, created = await store.append_message(
        group_id,
        source=request.source,
        text=request.text,
        source_message_id=request.source_message_id,
        author_id=request.author_id,
        author_name=request.author_name,
    )
    if message is None:
        raise HTTPException(status_code=404, detail="group not found")

    response.status_code = 201 if created else 200
    if created:
        await hub.broadcast(
            group_id,
            {"type": "message", "message": message.model_dump(mode="json")},
        )
    return message


@router.get("/groups/{group_id}/messages", response_model=list[TripMessage])
async def list_messages(
    group_id: str, limit: int = Query(default=100, ge=1, le=1000)
) -> list[TripMessage]:
    return _require_group(group_id).messages[-limit:]


# ---------------------------------------------------------------------------
# Itinerary proposals: the approval boundary
# ---------------------------------------------------------------------------
@router.get("/groups/{group_id}/proposals", response_model=list[Proposal])
async def list_proposals(group_id: str) -> list[Proposal]:
    return _require_group(group_id).proposals


@router.post("/groups/{group_id}/proposals", response_model=Proposal)
async def create_itinerary_proposal(
    group_id: str, request: ProposalRequest, response: Response
) -> Proposal:
    """Builds an itinerary and puts it forward. It does NOT become the group's
    plan; approving it does."""
    group = _require_group(group_id)

    if request.idempotency_key:
        already = store.find_proposal(group_id, request.idempotency_key)
        if already is not None:
            response.status_code = 200
            return already

    try:
        plan = await planner.build_plan(
            group,
            PlanRequest(
                interests=request.interests,
                max_stops=request.max_stops,
                transport=request.transport,
                radius_m=request.radius_m,
            ),
        )
    except places_service.PlacesError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not plan.stops:
        raise HTTPException(
            status_code=404,
            detail="nothing worth visiting was found here; try a larger radius",
        )

    proposal = Proposal(
        id=uuid.uuid4().hex[:12],
        created_at=time.time(),
        created_by=request.created_by,
        plan=plan,
        estimated_cost=request.estimated_cost,
        currency=request.currency.upper(),
        assumptions=request.assumptions,
        note=request.note,
    )
    stored, created = await store.add_proposal(
        group_id, proposal, request.idempotency_key
    )
    if stored is None:
        raise HTTPException(status_code=404, detail="group not found")

    response.status_code = 201 if created else 200
    if created:
        await hub.broadcast(
            group_id,
            {"type": "proposal", "proposal": stored.model_dump(mode="json")},
        )
    return stored


@router.post("/groups/{group_id}/proposals/{proposal_id}/approve", response_model=Proposal)
async def approve_itinerary_proposal(
    group_id: str, proposal_id: str, request: DecisionRequest
) -> Proposal:
    """The one place an itinerary becomes the group's actual plan."""
    return await _decide(group_id, proposal_id, "approved", request.decided_by)


@router.post("/groups/{group_id}/proposals/{proposal_id}/decline", response_model=Proposal)
async def decline_itinerary_proposal(
    group_id: str, proposal_id: str, request: DecisionRequest
) -> Proposal:
    """Declining records the decision and writes no itinerary."""
    return await _decide(group_id, proposal_id, "declined", request.decided_by)


async def _decide(
    group_id: str, proposal_id: str, status: str, decided_by: str | None
) -> Proposal:
    group = _require_group(group_id)
    if store.find_proposal(group_id, proposal_id) is None:
        raise HTTPException(status_code=404, detail="proposal not found")

    proposal, changed = await store.decide_proposal(
        group_id, proposal_id, status, decided_by
    )
    if proposal is None:
        raise HTTPException(status_code=404, detail="proposal not found")

    # A repeated decision is not an error and broadcasts nothing: Slack can
    # deliver the same button press twice.
    if changed:
        payload = {
            "type": "proposal_decision",
            "proposal": proposal.model_dump(mode="json"),
        }
        if status == "approved":
            annotated = planner.annotate_members(group)
            payload["plan"] = proposal.plan.model_dump(mode="json")
            payload["members"] = [
                m.model_dump(mode="json") for m in annotated.members
            ]
        await hub.broadcast(group_id, payload)

    return proposal
