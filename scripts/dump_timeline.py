"""Diagnostic script: log in to Sure Petcare and dump household timeline + pet
status data so we can inspect the real shape of feeding events.

Credentials are entered interactively (password via getpass) and are never
written to disk. Run with:

    uv run python scripts/dump_timeline.py

Output is written as JSON to the path given by --output.
"""

import argparse
import asyncio
import getpass
import json
from pathlib import Path

from surepcio.client import SurePetcareClient
from surepcio.household import Household


async def main(pages: int, output: Path) -> None:
    email = input("Sure Petcare email: ").strip()
    password = getpass.getpass("Sure Petcare password: ")

    client = SurePetcareClient()
    try:
        await client.login(email=email, password=password)

        households = await client.api(Household.get_households())
        if not households:
            print("No households found for this account.")
            return

        household = households[0]
        print(f"Using household id={household.id}")

        pets = await client.api(household.get_pets())
        print(f"Found {len(pets)} pet(s): {[p.name for p in pets]}")

        timeline_events = []
        before_id = None
        for page in range(pages):
            batch = await client.api(household.get_timeline(before_id=before_id))
            if not batch:
                break
            timeline_events.extend(batch)
            ids = [item["id"] for item in batch if "id" in item]
            if not ids:
                break
            before_id = min(ids)
            print(
                f"Page {page + 1}: {len(batch)} events (oldest id so far: {before_id})"
            )

        dump = {
            "household_id": household.id,
            "pets": [
                {
                    "id": pet.id,
                    "name": pet.name,
                    "status": pet.status.model_dump(mode="json"),
                }
                for pet in pets
            ],
            "timeline_events": timeline_events,
        }

        output.write_text(json.dumps(dump, indent=2, default=str))
        print(
            f"\nWrote {len(timeline_events)} timeline events + pet status to {output}"
        )

        if timeline_events:
            type_counts: dict = {}
            for event in timeline_events:
                key = event.get("type", "?")
                type_counts[key] = type_counts.get(key, 0) + 1
            print(f"Event type counts: {type_counts}")
            print("\nSample event:")
            print(json.dumps(timeline_events[0], indent=2, default=str))
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pages",
        type=int,
        default=3,
        help="Number of timeline pages to fetch, paged backwards via before_id",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("timeline_dump.json"),
        help="Where to write the JSON dump",
    )
    args = parser.parse_args()
    asyncio.run(main(args.pages, args.output))
