"""Diagnostic: check whether the real timeline API returns per-frame weight-change
data (weights[].frames), which feedings_today/food_today's gram totals depend on.

Credentials are entered interactively (password via getpass) and are never written
to disk or sent anywhere but the Sure Petcare API itself. Run with:

    uv run python scripts/check_timeline_frames.py

Prints the raw JSON of the most recent FEEDING/WEIGHT_CHANGED events for each of
your households, so you can see directly whether 'frames' has anything in it.
"""

import argparse
import asyncio
import json
from getpass import getpass

from surepcio import Household, SurePetcareClient
from surepcio.enums import TimelineEventType


async def main(page_size: int) -> None:
    email = input("Sure Petcare email: ").strip()
    password = getpass("Sure Petcare password: ")

    client = SurePetcareClient()
    try:
        await client.login(email=email, password=password)

        households: list[Household] = await client.api(Household.get_households())
        for household in households:
            name = (household.data.get("name") or "").strip() or f"#{household.id}"
            print(f"\n=== Household {name} (id={household.id}) ===")

            events = await client.api(household.get_timeline(page_size=page_size))
            feeding_events = [
                e
                for e in events
                if e.event_type
                in (TimelineEventType.FEEDING, TimelineEventType.WEIGHT_CHANGED)
            ]
            if not feeding_events:
                print("  No FEEDING/WEIGHT_CHANGED events in the most recent page.")
                continue

            for event in feeding_events:
                print(f"\n  --- event {event.id} ({event.event_type.name}) ---")
                print(json.dumps(event.model_dump(mode="json"), indent=2, default=str))
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--page-size",
        type=int,
        default=25,
        help="Number of most-recent timeline events to fetch per household (default: 25)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.page_size))
