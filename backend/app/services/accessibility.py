"""Turning what a traveller said into a limit the planner must obey.

The model is asked to keep a route tight when somebody cannot walk far, but
asking is not enough: a route that quietly ignores a mobility constraint is
worse than no route. So the constraint is also enforced in code, after the
places are chosen, by dropping stops until every leg fits.

The matching is deliberately narrow. These phrases are unambiguous; anything
subtler is left to the model, which reads the whole sentence.
"""
from __future__ import annotations

from typing import Sequence

from ..models import Member

# Phrase -> how far this person can reasonably walk in one go, in metres.
_LIMITED_WALKING: dict[str, int] = {
    "wheelchair": 400,
    "crutch": 400,
    "cannot walk": 600,
    "can't walk": 600,
    "cant walk": 600,
    "not walk far": 600,
    "no long walk": 900,
    "no long walks": 900,
    "short walks": 900,
    "limited walking": 900,
    "bad knee": 900,
    "sore feet": 900,
    "blister": 900,
    "stroller": 1200,
    "pram": 1200,
    "pushchair": 1200,
}


def walking_limit(travelers: Sequence[Member]) -> tuple[int | None, list[str]]:
    """The tightest limit anyone in the group is under.

    Returns (metres per leg, one human-readable note per person it came from).
    A group walks together, so the least mobile person sets the pace.
    """
    limit: int | None = None
    notes: list[str] = []

    for traveler in travelers:
        for constraint in traveler.constraints:
            text = constraint.casefold()
            for phrase, metres in _LIMITED_WALKING.items():
                if phrase in text:
                    if limit is None or metres < limit:
                        limit = metres
                    # State what was said. Whether the route could honour it is
                    # the planner's to report, not this function's to promise.
                    notes.append(f"{traveler.display_name}: “{constraint}”")
                    break  # one note per constraint, not one per phrase

    return limit, notes
