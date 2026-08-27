"""Aggregate today's household feeding and bowl-maintenance events from the timeline."""

import bisect
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from homeassistant.util import dt as dt_util
from surepcio import Household
from surepcio.client import SurePetcareClient
from surepcio.enums import FoodType, Tare, TimelineEventType
from surepcio.timeline import TimelineEntityInfo, TimelineEvent, WeightResource

logger = logging.getLogger(__name__)

# Event types that make up a household's feeding activity feed: a pet's
# feeder visit ("Pet ate"), a feeder bowl being refilled (weight increase
# with no pet tag), and a bowl being zeroed/tared.
TIMELINE_EVENT_TYPES = {
    TimelineEventType.FEEDING,
    TimelineEventType.WEIGHT_CHANGED,
    TimelineEventType.TARE,
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
    # Highest event id folded in so far; seeds incremental since_id polling.
    cursor: int | None = None

    def _bump_cursor(self, event_id: int) -> None:
        """Record an event as processed, whether or not it produced an entry."""
        self.cursor = event_id if self.cursor is None else max(self.cursor, event_id)

    def add_event(
        self, entry: dict[str, Any], pet_id: int | None, event_id: int
    ) -> None:
        """Fold one classified entry in, keeping activity/events sorted
        (callers may add newest-first or oldest-first)."""
        self._bump_cursor(event_id)
        bisect.insort(self.activity, entry, key=lambda e: e["at"])
        if pet_id is None:
            return
        reading = {key: entry[key] for key in _READING_KEYS}
        stats = self.feeding_stats.setdefault(pet_id, PetFeedingStats())
        stats.count += 1
        stats.total_grams = round(stats.total_grams + reading["grams"], 1)
        stats.total_wet_grams = round(stats.total_wet_grams + reading["wet_grams"], 1)
        stats.total_dry_grams = round(stats.total_dry_grams + reading["dry_grams"], 1)
        bisect.insort(stats.events, reading, key=lambda e: e["at"])


def _parse_data_blob(event: TimelineEvent) -> dict[str, Any]:
    """Parse the event's JSON-encoded 'data' blob, tolerating malformed input."""
    if not event.data:
        return {}
    try:
        return json.loads(event.data)
    except TypeError, ValueError:
        return {}


def _device_name(event: TimelineEvent, device_id: int | None) -> str | None:
    """Look up a device's friendly name from the event's embedded device list."""
    if device_id is None:
        return None
    for device in event.devices:
        if device.id == device_id:
            return device.name
    return None


def _tare_label(tare_type: int | None) -> str | None:
    """Return a human-readable label for a tare_type code, if known."""
    if tare_type is None:
        return None
    try:
        return Tare(tare_type).name.lower()
    except ValueError:
        return None


def _bowl_food_types(event: TimelineEvent) -> list[int]:
    """Return the per-bowl food type codes embedded in the event's data blob."""
    return _parse_data_blob(event).get("weight", {}).get("food_type") or []


def _split_by_food_type(
    event: TimelineEvent, weights: list[WeightResource], *, use_abs: bool
) -> tuple[float, float, float]:
    """Split each bowl's weight change into (wet, dry, other) grams.

    use_abs=True for feeding events (frames go negative); use_abs=False for
    bowl-filled events, to keep wet+dry+other == the signed grams added.
    """
    food_types = _bowl_food_types(event)
    wet = dry = other = 0.0
    for weight in weights:
        for frame in weight.frames:
            change = frame.change or 0
            if use_abs:
                change = abs(change)
            index = frame.index
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
    """Fetch the household's display name. Best-effort: any error is
    swallowed and treated as "name unknown" rather than raised."""
    try:
        household = await client.api(Household.get_household(household_id))
        name = household.data.get("name")
    except Exception:
        logger.debug(
            "Failed to fetch household name for household %s",
            household_id,
            exc_info=True,
        )
        return None
    return name.strip() if isinstance(name, str) and name.strip() else None


def _first_id(entities: list[TimelineEntityInfo]) -> int | None:
    """Return the id of the first embedded entity, if any."""
    return entities[0].id if entities else None


# Keys of a per-pet feeding "reading" - the subset of a feeding activity
# entry that PetFeedingStats aggregates over.
_READING_KEYS = (
    "at",
    "device_id",
    "grams",
    "wet_grams",
    "dry_grams",
    "duration_seconds",
)


async def _iter_today_events(
    client: SurePetcareClient, household_id: int, cutoff: datetime
) -> AsyncIterator[tuple[TimelineEvent, datetime]]:
    """Yield each relevant timeline event since `cutoff`, most recent first.

    Pages backwards until it crosses `cutoff`, runs out of events, or hits
    MAX_TIMELINE_PAGES (warns, since totals are then incomplete). Dedupes
    across pages, since `before_id` paging can repeat the boundary event.
    """
    household = Household({"id": household_id})
    before_id: int | None = None
    seen_event_ids: set[int] = set()

    for _ in range(MAX_TIMELINE_PAGES):
        batch: list[TimelineEvent] = await client.api(
            household.get_timeline(before_id=before_id)
        )
        if not batch:
            return

        newest_in_batch: datetime | None = None
        for event in batch:
            at = event.created_at
            if at is None:
                continue
            if newest_in_batch is None or at > newest_in_batch:
                newest_in_batch = at
            if event.event_type not in TIMELINE_EVENT_TYPES or at < cutoff:
                continue
            if event.id in seen_event_ids:
                continue
            seen_event_ids.add(event.id)
            yield event, at

        before_id = min(event.id for event in batch)
        # Stop only once the whole page is before cutoff (its newest event
        # still is): ids aren't strictly ordered by created_at, so a page can
        # mix pre/post-cutoff events, and stopping on just one old event
        # could skip same-day events that only appear on a later page.
        if newest_in_batch is not None and newest_in_batch < cutoff:
            return

    logger.warning(
        "Household %s timeline still had unpaged events after %d pages; "
        "today's feeding totals may be incomplete",
        household_id,
        MAX_TIMELINE_PAGES,
    )


def _feeding_entry(
    event: TimelineEvent,
    at: datetime,
    weights: list[WeightResource],
    device_id: int | None,
    device_name: str | None,
) -> dict[str, Any] | None:
    """Build the activity-feed entry for a pet's feeder visit, or None if unattributable."""
    pet_id = _first_id(event.pets)
    if pet_id is None:
        return None
    # Each event is one complete, finalized visit - not an incremental update.
    wet_grams, dry_grams, other_grams = _split_by_food_type(
        event, weights, use_abs=True
    )
    return {
        "at": at,
        "activity_type": "feeding",
        "pet_id": pet_id,
        "pet_name": event.pets[0].name,
        "device_id": device_id,
        "device_name": device_name,
        "grams": round(wet_grams + dry_grams + other_grams, 1),
        "wet_grams": round(wet_grams, 1),
        "dry_grams": round(dry_grams, 1),
        "duration_seconds": weights[0].duration if weights else None,
    }


def _bowl_filled_entry(
    event: TimelineEvent,
    at: datetime,
    weights: list[WeightResource],
    device_id: int | None,
    device_name: str | None,
) -> dict[str, Any]:
    """Build the activity-feed entry for a feeder bowl being refilled."""
    fill_wet, fill_dry, fill_other = _split_by_food_type(event, weights, use_abs=False)
    return {
        "at": at,
        "activity_type": "bowl_filled",
        "device_id": device_id,
        "device_name": device_name,
        "grams": round(fill_wet + fill_dry + fill_other, 1),
        "wet_grams": round(fill_wet, 1),
        "dry_grams": round(fill_dry, 1),
    }


def _bowl_zeroed_entry(
    event: TimelineEvent,
    at: datetime,
    device_id: int | None,
    device_name: str | None,
) -> dict[str, Any]:
    """Build the activity-feed entry for a feeder bowl being zeroed/tared."""
    tare_type = _parse_data_blob(event).get("tare_type")
    return {
        "at": at,
        "activity_type": "bowl_zeroed",
        "device_id": device_id,
        "device_name": device_name,
        "tare_type": tare_type,
        "tare_label": _tare_label(tare_type),
    }


def _classify_event(
    event: TimelineEvent, at: datetime
) -> tuple[dict[str, Any], int | None] | None:
    """Classify one timeline event into an activity-feed entry.

    Returns (entry, pet_id) - pet_id set only for feeding events. Returns
    None if unattributable (a feeding event with no pet). Callers must
    already have filtered event_type to TIMELINE_EVENT_TYPES.
    """
    weights = event.weights
    device_id = weights[0].device_id if weights else None
    device_name = _device_name(event, device_id)

    if event.event_type == TimelineEventType.FEEDING:
        entry = _feeding_entry(event, at, weights, device_id, device_name)
        return (entry, entry["pet_id"]) if entry is not None else None
    if event.event_type == TimelineEventType.WEIGHT_CHANGED:
        return _bowl_filled_entry(event, at, weights, device_id, device_name), None
    return _bowl_zeroed_entry(event, at, device_id, device_name), None  # TARE


async def fetch_household_timeline_today(
    client: SurePetcareClient, household_id: int
) -> HouseholdTimelineData:
    """Page back through the household timeline and build today's feeding
    stats + activity feed from scratch. Used for the coordinator's cold
    start; fold_new_events() below handles the rest of the day incrementally.
    """
    cutoff = dt_util.start_of_local_day()
    data = HouseholdTimelineData()

    async for event, at in _iter_today_events(client, household_id, cutoff):
        classified = _classify_event(event, at)
        if classified is not None:
            data.add_event(*classified, event.id)
        else:
            data._bump_cursor(event.id)

    return data


async def fetch_new_events(
    client: SurePetcareClient, household_id: int, since_id: int | None
) -> list[TimelineEvent]:
    """Fetch timeline events newer than since_id - a single forward request,
    not paged, matching SurePetCareHouseholdTimelineCoordinator's own polling.
    """
    household = Household({"id": household_id})
    return await client.api(household.get_timeline(since_id=since_id))


def fold_new_events(data: HouseholdTimelineData, events: list[TimelineEvent]) -> None:
    """Classify and fold a batch of new, already-deduplicated timeline events
    into an existing same-day aggregate, in place.
    """
    for event in sorted(
        events, key=lambda event: event.created_at or datetime.min.replace(tzinfo=UTC)
    ):
        at = event.created_at
        if event.event_type not in TIMELINE_EVENT_TYPES or at is None:
            continue
        classified = _classify_event(event, at)
        if classified is not None:
            data.add_event(*classified, event.id)
        else:
            data._bump_cursor(event.id)
