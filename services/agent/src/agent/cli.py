from __future__ import annotations

import sys
import uuid

from .config import Settings
from .trip_agent import TripAgent

DEFAULT_CONSTRAINTS = (
    "Plan Saturday afternoon for six of us in Prague, food + activity, "
    "under EUR 40 per person."
)


def main() -> None:
    constraints = " ".join(sys.argv[1:]) or DEFAULT_CONSTRAINTS
    settings = Settings.from_env()
    agent = TripAgent(settings)
    trip_id = str(uuid.uuid4())
    print(f"trip_id: {trip_id}")
    print(agent.plan(trip_id, constraints))


if __name__ == "__main__":
    main()
