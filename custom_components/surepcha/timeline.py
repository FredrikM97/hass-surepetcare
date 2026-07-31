"""Aggregate today's household feeding and bowl-maintenance events from the timeline."""

from collections import defaultdict
from dataclasses import dataclass, field
import json
import logging
from typing import Any

from surepcio import Household
from surepcio.client import SurePetcareClient
from surepcio.enums import FoodType, Tare

from homeassistant.util import dt as dt_util

logger = logging.getLogger(__name__)

# Sure Petcare timeline event types seen in a household's feed:
# - a pet's feeder visit ("Pet ate")
# - a feeder bowl being refilled (large weight increase, no pet tag)
# - a feeder bowl being zeroed/tared (weight reset to 0, no pet tag)
# These are inferred from field evidence (a zero event immediately followed by
# a large weight increase on the same device matches a "remove bowl, it reads
# ~0, refill it, put it back" workflow) rather than documented by the API.
FEEDING_EVENT_TYPE = 22
BOWL_FILLED_EVENT_TYPE = 21
BOWL_ZEROED_EVENT_TYPE = 24
TIMELINE_EVENT_TYPES = {
    FEEDING_EVENT_TYPE,
    BOWL_FILLED_EVENT_TYPE,
    BOWL_ZEROED_EVENT_TYPE,
}

MAX_TIMELINE_PAGES = 10


@dataclass
class PetFeedingStats:
    """Today's feeding activity for a single pet."""

    count: int = 0
    total_grams: float = 0.0
    total_wet_grams: float = 0.0
    total_dry_grams: float = 0.0
    events: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class HouseholdTimelineData:
    """Today's household timeline: per-pet feeding stats plus a combined activity feed."""

    feeding_stats: dict[int, PetFeedingStats] = field(default_factory=dict)
    activity: list[dict[str, Any]] = field(default_factory=list)


def _parse_data_blob(event: dict[str, Any]) -> dict[str, Any]:
    """Parse the event's JSON-encoded 'data' blob, tolerating malformed input."""
    raw_data = event.get("data")
    if not raw_data:
        return {}
    try:
        return json.loads(raw_data)
    except (TypeError, ValueError):
        return {}


def _device_name(event: dict[str, Any], device_id: int | None) -> str | None:
    """Look up a device's friendly name from the event's embedded device list."""
    if device_id is None:
        return None
    for device in event.get("devices") or []:
        if device.get("id") == device_id:
            return device.get("name")
    return None


def _tare_label(tare_type: int | None) -> str | None:
    """Return a human-readable label for a tare_type code, if known."""
    if tare_type is None:
        return None
    try:
        return Tare(tare_type).name.lower()
    except ValueError:
        return None


def _bowl_food_types(event: dict[str, Any]) -> list[int]:
    """Return the per-bowl food type codes embedded in the event's data blob."""
    return _parse_data_blob(event).get("weight", {}).get("food_type") or []


def _split_by_food_type(
    event: dict[str, Any], weights: list[dict[str, Any]], *, use_abs: bool
) -> tuple[float, float, float]:
    """Split each bowl's weight change into (wet, dry, other) grams.

    use_abs=True for feeding events (frames can be negative "removed" amounts,
    we want magnitude); use_abs=False for bowl-filled events (raw signed sum
    is the pre-existing convention there, so wet+dry+other stays == grams).
    """
    food_types = _bowl_food_types(event)
    wet = dry = other = 0.0
    for weight in weights:
        for frame in weight.get("frames", []):
            change = frame.get("change") or 0
            if use_abs:
                change = abs(change)
            index = frame.get("index")
            food_type = (
                food_types[index]
                if index is not None and index < len(food_types)
                else None
            )
            if food_type == FoodType.WET.value:
                wet += change
            elif food_type == FoodType.DRY.value:
                dry += change
            else:
                other += change
    return wet, dry, other


async def fetch_household_name(
    client: SurePetcareClient, household_id: int
) -> str | None:
    """Fetch the household's display name (e.g. for use as a device/title name).

    Best-effort: a failure here shouldn't take down feeding/activity polling,
    so any error is swallowed and treated as "name unknown".
    """
    try:
        household = await client.api(Household.get_household(household_id))
    except Exception:
        logger.debug(
            "Failed to fetch household name for household %s",
            household_id,
            exc_info=True,
        )
        return None
    name = household.data.get("name")
    return name.strip() if isinstance(name, str) and name.strip() else None


async def fetch_household_timeline_today(
    client: SurePetcareClient, household_id: int
) -> HouseholdTimelineData:
    """Page back through the household timeline and build today's feeding stats + activity feed."""
    household = Household({"id": household_id})
    cutoff = dt_util.start_of_local_day()
    events_by_pet: dict[int, list[dict[str, Any]]] = defaultdict(list)
    activity: list[dict[str, Any]] = []
    before_id: int | None = None

    for _ in range(MAX_TIMELINE_PAGES):
        batch = await client.api(household.get_timeline(before_id=before_id))
        if not batch:
            break

        oldest_in_batch = None
        for event in batch:
            at = dt_util.parse_datetime(event.get("created_at") or "")
            if at is None:
                continue
            if oldest_in_batch is None or at < oldest_in_batch:
                oldest_in_batch = at

            event_type = event.get("type")
            if event_type not in TIMELINE_EVENT_TYPES or at < cutoff:
                continue

            weights = event.get("weights") or []
            device_id = weights[0].get("device_id") if weights else None
            device_name = _device_name(event, device_id)

            if event_type == FEEDING_EVENT_TYPE:
                pets = event.get("pets") or []
                if not pets or "id" not in pets[0]:
                    continue

                # Each timeline event is already one complete, finalized feeder
                # visit (not an incremental progress update) — the API reports
                # its own duration alongside the weight change.
                wet_grams, dry_grams, other_grams = _split_by_food_type(
                    event, weights, use_abs=True
                )

                duration_seconds = weights[0].get("duration") if weights else None
                pet_id = pets[0]["id"]
                pet_name = pets[0].get("name")
                reading = {
                    "at": at,
                    "device_id": device_id,
                    "grams": round(wet_grams + dry_grams + other_grams, 1),
                    "wet_grams": round(wet_grams, 1),
                    "dry_grams": round(dry_grams, 1),
                    "duration_seconds": duration_seconds,
                }
                events_by_pet[pet_id].append(reading)
                activity.append(
                    {
                        "at": at,
                        "activity_type": "feeding",
                        "pet_id": pet_id,
                        "pet_name": pet_name,
                        "device_id": device_id,
                        "device_name": device_name,
                        **{k: v for k, v in reading.items() if k != "at"},
                    }
                )

            elif event_type == BOWL_FILLED_EVENT_TYPE:
                fill_wet, fill_dry, fill_other = _split_by_food_type(
                    event, weights, use_abs=False
                )
                activity.append(
                    {
                        "at": at,
                        "activity_type": "bowl_filled",
                        "device_id": device_id,
                        "device_name": device_name,
                        "grams": round(fill_wet + fill_dry + fill_other, 1),
                        "wet_grams": round(fill_wet, 1),
                        "dry_grams": round(fill_dry, 1),
                    }
                )

            elif event_type == BOWL_ZEROED_EVENT_TYPE:
                tare_type = _parse_data_blob(event).get("tare_type")
                activity.append(
                    {
                        "at": at,
                        "activity_type": "bowl_zeroed",
                        "device_id": device_id,
                        "device_name": device_name,
                        "tare_type": tare_type,
                        "tare_label": _tare_label(tare_type),
                    }
                )

        ids = [event["id"] for event in batch if "id" in event]
        if not ids:
            break
        before_id = min(ids)

        if oldest_in_batch is not None and oldest_in_batch < cutoff:
            break

    feeding_stats = {
        pet_id: PetFeedingStats(
            count=len(events),
            total_grams=round(sum(event["grams"] for event in events), 1),
            total_wet_grams=round(sum(event["wet_grams"] for event in events), 1),
            total_dry_grams=round(sum(event["dry_grams"] for event in events), 1),
            events=sorted(events, key=lambda event: event["at"]),
        )
        for pet_id, events in events_by_pet.items()
    }
    activity.sort(key=lambda event: event["at"])
    return HouseholdTimelineData(feeding_stats=feeding_stats, activity=activity)
