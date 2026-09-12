"""Deterministic specialist workflows shared by Slack and the dashboard."""
from __future__ import annotations

import time
import uuid
from collections import defaultdict

from fastapi import APIRouter, HTTPException

from ..models import (
    DecisionRequest, Expense, ExpenseRequest, Group, LocalSuggestion, MediaItem,
    MediaRequest, MemoryEntry, MemoryRequest, PackingList, PackingRequest,
    PollOption, PollRequest, TripPoll, VoteRequest,
)
from ..store import store

router = APIRouter(prefix="/api/groups/{group_id}", tags=["specialists"])


def _group(group_id: str) -> Group:
    group = store.get(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="group not found")
    return group


def _media_category(filename: str, note: str) -> str:
    text = f"{filename} {note}".casefold()
    rules = {
        "receipt": ("receipt", "bill", "invoice"),
        "ticket": ("ticket", "boarding", "pass"),
        "booking": ("booking", "reservation", "hotel"),
        "food": ("food", "meal", "restaurant", "cafe"),
        "landmark": ("landmark", "museum", "castle", "monument"),
        "group_photo": ("group", "selfie", "friends"),
    }
    return next((kind for kind, words in rules.items() if any(w in text for w in words)), "other")


@router.post("/media", response_model=MediaItem, status_code=201)
async def organize_media(group_id: str, request: MediaRequest) -> MediaItem:
    _group(group_id)
    item = MediaItem(
        id=uuid.uuid4().hex[:12], filename=request.filename,
        category=request.category or _media_category(request.filename, request.note),
        note=request.note, location=request.location, day=request.day,
        created_at=time.time(), created_by=request.created_by,
    )
    return await store.add_media(group_id, item) or item


@router.post("/expenses", response_model=Expense, status_code=201)
async def propose_expense(group_id: str, request: ExpenseRequest) -> Expense:
    group = _group(group_id)
    member_ids = {m.id for m in group.members}
    if request.paid_by not in member_ids:
        raise HTTPException(status_code=422, detail="payer must be a group member id")
    if any(pid not in member_ids for pid in request.participant_ids):
        raise HTTPException(status_code=422, detail="every participant must be a group member")
    cents = round(request.amount * 100)
    base, remainder = divmod(cents, len(request.participant_ids))
    shares = {
        pid: (base + (1 if index < remainder else 0)) / 100
        for index, pid in enumerate(request.participant_ids)
    }
    expense = Expense(
        id=uuid.uuid4().hex[:12], title=request.title, amount=cents / 100,
        currency=request.currency.upper(), paid_by=request.paid_by,
        participant_ids=request.participant_ids, shares=shares,
        media_id=request.media_id, created_at=time.time(),
    )
    return await store.add_expense(group_id, expense) or expense


@router.post("/expenses/{expense_id}/{decision}", response_model=Expense)
async def decide_expense(group_id: str, expense_id: str, decision: str, request: DecisionRequest) -> Expense:
    _group(group_id)
    if decision not in {"approve", "decline"}:
        raise HTTPException(status_code=404, detail="decision not found")
    result = await store.decide_expense(group_id, expense_id, f"{decision}d", request.decided_by)
    if result is None:
        raise HTTPException(status_code=404, detail="expense not found")
    return result


@router.get("/balances")
async def balances(group_id: str) -> dict:
    group = _group(group_id)
    balances: dict[str, float] = defaultdict(float)
    for expense in group.expenses:
        if expense.status != "approved":
            continue
        balances[expense.paid_by] += expense.amount
        for member_id, share in expense.shares.items():
            balances[member_id] -= share
    return {"currency": next((e.currency for e in group.expenses if e.status == "approved"), "EUR"), "balances": {k: round(v, 2) for k, v in balances.items()}}


@router.post("/polls", response_model=TripPoll, status_code=201)
async def create_poll(group_id: str, request: PollRequest) -> TripPoll:
    _group(group_id)
    labels = [label.strip() for label in request.options if label.strip()]
    if len({label.casefold() for label in labels}) < 2:
        raise HTTPException(status_code=422, detail="poll needs two distinct options")
    poll = TripPoll(id=uuid.uuid4().hex[:12], question=request.question,
                    options=[PollOption(id=uuid.uuid4().hex[:8], label=label) for label in labels],
                    created_at=time.time())
    return await store.add_poll(group_id, poll) or poll


@router.post("/polls/{poll_id}/vote", response_model=TripPoll)
async def vote(group_id: str, poll_id: str, request: VoteRequest) -> TripPoll:
    result = await store.vote(group_id, poll_id, request.option_id, request.voter_id)
    if result is None:
        raise HTTPException(status_code=404, detail="open poll or option not found")
    return result


@router.post("/polls/{poll_id}/close", response_model=TripPoll)
async def close_poll(group_id: str, poll_id: str) -> TripPoll:
    result = await store.close_poll(group_id, poll_id)
    if result is None:
        raise HTTPException(status_code=404, detail="poll not found")
    return result


@router.post("/packing", response_model=PackingList)
async def packing(group_id: str, request: PackingRequest) -> PackingList:
    group = _group(group_id)
    personal = [f"{request.days} days of clothes", "comfortable shoes", "ID and travel documents", "phone charger", "personal medication"]
    shared = ["portable battery", "basic first-aid kit", "shared reservation copies"]
    text = " ".join([request.weather, *group.interests]).casefold()
    if any(word in text for word in ("rain", "wet", "storm")):
        personal += ["waterproof jacket", "compact umbrella"]
    if any(word in text for word in ("walk", "hike", "outdoor")):
        personal.append("refillable water bottle")
    return PackingList(personal=personal, shared=shared, assumptions=[f"Weather: {request.weather}", f"Destination: {group.city.name}"])


@router.get("/local-guide", response_model=LocalSuggestion)
async def local_guide(group_id: str, need: str = "nearby alternatives") -> LocalSuggestion:
    group = _group(group_id)
    constraints = [c for member in group.members for c in member.constraints]
    prompt = f"Current {need} in {group.city.display_name}; interests: {', '.join(group.interests) or 'general sightseeing'}; constraints: {', '.join(constraints) or 'none stated'}. Include current sources."
    return LocalSuggestion(query=need, city=group.city.display_name, search_prompt=prompt)


@router.post("/memories", response_model=MemoryEntry, status_code=201)
async def add_memory(group_id: str, request: MemoryRequest) -> MemoryEntry:
    group = _group(group_id)
    known_media = {m.id for m in group.media}
    if any(mid not in known_media for mid in request.media_ids):
        raise HTTPException(status_code=422, detail="memory references unknown media")
    entry = MemoryEntry(id=uuid.uuid4().hex[:12], title=request.title,
                        description=request.description,
                        occurred_at=request.occurred_at or time.time(), media_ids=request.media_ids)
    return await store.add_memory(group_id, entry) or entry
