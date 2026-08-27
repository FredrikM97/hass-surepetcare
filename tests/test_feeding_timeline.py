"""Regression tests for feeding_timeline.py's event parsing.

Exercises timeline events whose weights[].frames are populated (see
fixtures/feeding_timeline_frames.json) - the shipped timeline.json fixture
strips frames out, so the gram-split logic would otherwise be untested.
"""

import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from freezegun import freeze_time
from pytest_homeassistant_custom_component.common import load_json_value_fixture
from surepcio.enums import TimelineEventType
from surepcio.timeline import TimelineEvent

from custom_components.surepcha.feeding_timeline import (
    MAX_TIMELINE_PAGES,
    HouseholdTimelineData,
    _device_name,
    _split_by_food_type,
    fetch_household_name,
    fetch_household_timeline_today,
    fold_new_events,
)


def _load_event(name: str) -> TimelineEvent:
    """Load one named event from feeding_timeline_frames.json."""
    raw = load_json_value_fixture("feeding_timeline_frames.json")
    return TimelineEvent(**raw[name])


def test_split_by_food_type_feeding_wet_and_dry() -> None:
    """A feeding event with food_type [WET, DRY] splits per-frame changes correctly."""
    event = _load_event("feeding_wet_and_dry")

    wet, dry, other = _split_by_food_type(event, event.weights, use_abs=True)

    # frames: index 0 change=-12 (food_type WET), index 1 change=-1 (food_type DRY)
    assert wet == 12
    assert dry == 1
    assert other == 0


def test_split_by_food_type_feeding_wet_only() -> None:
    """A feeding event where the pet only touched the wet bowl."""
    event = _load_event("feeding_wet_only")

    wet, dry, other = _split_by_food_type(event, event.weights, use_abs=True)

    # frames: index 0 change=-3 (WET), index 1 change=-2 (DRY)
    assert wet == 3
    assert dry == 2
    assert other == 0


def test_split_by_food_type_bowl_filled_keeps_sign() -> None:
    """A bowl-filled (WEIGHT_CHANGED) event keeps the raw signed change (use_abs=False)."""
    event = _load_event("bowl_filled")

    wet, dry, other = _split_by_food_type(event, event.weights, use_abs=False)

    # frames: index 0 change=+83 (WET), index 1 change=+45 (DRY)
    assert wet == 83
    assert dry == 45
    assert other == 0


def test_device_name_looks_up_from_embedded_devices() -> None:
    """The feeder's name is resolved from the event's embedded device list."""
    event = _load_event("feeding_wet_and_dry")

    assert _device_name(event, 1376800) == "Feeder"
    assert _device_name(event, 1225898) == "Hub"
    assert _device_name(event, None) is None
    assert _device_name(event, 999999) is None


async def test_fetch_household_timeline_today_aggregates_real_events(hass) -> None:
    """Pages the fixture's three events into per-pet stats and a combined activity feed.

    Exercises the full aggregation path (not just _split_by_food_type in
    isolation): per-pet totals, the chronological activity feed, and the
    pagination stop once the API runs out of pages.
    """
    await hass.config.async_set_time_zone("UTC")
    events = [
        _load_event(name)
        for name in ("feeding_wet_and_dry", "feeding_wet_only", "bowl_filled")
    ]
    client = MagicMock()
    client.api = AsyncMock(side_effect=[events, []])

    with freeze_time("2026-08-27T12:00:00+00:00"):
        data = await fetch_household_timeline_today(client, 222527)

    # One page of events, then an empty page ends the backward paging.
    assert client.api.await_count == 2

    assert set(data.feeding_stats) == {472721, 532070}  # Maui, Ajax

    maui = data.feeding_stats[472721]
    assert maui.count == 1
    assert maui.total_grams == 13.0
    assert maui.total_wet_grams == 12.0
    assert maui.total_dry_grams == 1.0

    ajax = data.feeding_stats[532070]
    assert ajax.count == 1
    assert ajax.total_grams == 5.0
    assert ajax.total_wet_grams == 3.0
    assert ajax.total_dry_grams == 2.0

    # Sorted oldest-first: Ajax's feeding (05:07), the bowl fill (06:35),
    # then Maui's feeding (11:07).
    assert [entry["activity_type"] for entry in data.activity] == [
        "feeding",
        "bowl_filled",
        "feeding",
    ]


async def test_fetch_household_timeline_today_dedupes_events_seen_on_multiple_pages(
    hass,
) -> None:
    """before_id paging can hand back the boundary event again on the next page.

    An event id already yielded on an earlier page must not be counted twice.
    """
    await hass.config.async_set_time_zone("UTC")
    event = _load_event("feeding_wet_and_dry")
    client = MagicMock()
    # Page 2 repeats the same boundary event before page 3 finally empties out.
    client.api = AsyncMock(side_effect=[[event], [event], []])

    with freeze_time("2026-08-27T12:00:00+00:00"):
        data = await fetch_household_timeline_today(client, 222527)

    assert client.api.await_count == 3
    assert data.feeding_stats[472721].count == 1


async def test_fetch_household_timeline_today_keeps_paging_past_a_mixed_page(
    hass,
) -> None:
    """A page's oldest event being before cutoff doesn't mean the whole page
    is - timeline ids aren't strictly ordered by created_at, so a page can mix
    pre/post-cutoff events. Stopping must wait until the newest (not oldest)
    event in a page is before cutoff, or a same-day event on a later page
    would be silently skipped.
    """
    await hass.config.async_set_time_zone("UTC")
    today_event = _load_event("feeding_wet_and_dry")  # Maui, today
    old_outlier = today_event.model_copy(
        update={
            "id": today_event.id - 1,
            "created_at": datetime(2026, 8, 20, 9, 0, 0, tzinfo=UTC),
        }
    )
    later_page_event = _load_event("feeding_wet_only")  # Ajax, today
    client = MagicMock()
    client.api = AsyncMock(
        side_effect=[[today_event, old_outlier], [later_page_event], []]
    )

    with freeze_time("2026-08-27T12:00:00+00:00"):
        data = await fetch_household_timeline_today(client, 222527)

    assert client.api.await_count == 3
    assert set(data.feeding_stats) == {472721, 532070}  # Maui and Ajax


async def test_fetch_household_timeline_today_warns_when_page_limit_reached(
    hass, caplog
) -> None:
    """If MAX_TIMELINE_PAGES is exhausted with same-day events still pending, warn.

    Silent truncation would otherwise let a very active household's totals
    quietly drop earlier-today feedings as the day goes on.
    """
    await hass.config.async_set_time_zone("UTC")
    event = _load_event("feeding_wet_and_dry")
    client = MagicMock()
    # Every page returns the same non-empty, same-day batch - paging never
    # naturally terminates, so the page cap must kick in.
    client.api = AsyncMock(return_value=[event])

    with freeze_time("2026-08-27T12:00:00+00:00"), caplog.at_level(logging.WARNING):
        await fetch_household_timeline_today(client, 222527)

    assert client.api.await_count == MAX_TIMELINE_PAGES
    assert "still had unpaged events" in caplog.text


async def test_fetch_household_name_returns_stripped_name() -> None:
    """A successful lookup returns the household's display name, whitespace trimmed."""
    client = MagicMock()
    household = MagicMock()
    household.data = {"name": " Household "}
    client.api = AsyncMock(return_value=household)

    assert await fetch_household_name(client, 222527) == "Household"


async def test_fetch_household_name_swallows_unexpected_response_shape() -> None:
    """An API response with no usable .data is treated as name-unknown, not raised.

    Regression for the historical shape returned by the shared test mock (a
    bare list) - the .data access must stay inside the try, not raise past it.
    """
    client = MagicMock()
    client.api = AsyncMock(return_value=[])

    assert await fetch_household_name(client, 222527) is None


async def test_fetch_household_timeline_today_sets_cursor_to_the_newest_event(
    hass,
) -> None:
    """The returned aggregate's cursor is the highest event id folded in -
    SurePetCareFeedingTimelineCoordinator seeds its incremental polling from it."""
    await hass.config.async_set_time_zone("UTC")
    events = [
        _load_event(name)
        for name in ("feeding_wet_and_dry", "feeding_wet_only", "bowl_filled")
    ]
    client = MagicMock()
    client.api = AsyncMock(side_effect=[events, []])

    with freeze_time("2026-08-27T12:00:00+00:00"):
        data = await fetch_household_timeline_today(client, 222527)

    assert data.cursor == max(event.id for event in events)


def test_fold_new_events_folds_into_an_existing_aggregate_in_sorted_order() -> None:
    """fold_new_events adds to an existing HouseholdTimelineData in place,
    keeping activity/per-pet events sorted regardless of fold order."""
    earlier = _load_event("feeding_wet_only")  # 05:07:58Z, Ajax
    later = _load_event("feeding_wet_and_dry")  # 11:07:15Z, Maui

    data = HouseholdTimelineData()
    fold_new_events(data, [later])
    fold_new_events(data, [earlier])

    assert [event["pet_name"] for event in data.activity] == ["Ajax", "Maui"]
    assert data.cursor == max(earlier.id, later.id)
    assert data.feeding_stats[532070].count == 1  # Ajax
    assert data.feeding_stats[472721].count == 1  # Maui


def test_fold_new_events_skips_event_types_outside_the_feeding_activity_set() -> None:
    """An event type not in TIMELINE_EVENT_TYPES (e.g. a movement event) is
    ignored rather than mis-parsed as one of the three known shapes."""
    event = _load_event("feeding_wet_and_dry").model_copy(
        update={"event_type": TimelineEventType.MOVEMENT}
    )

    data = HouseholdTimelineData()
    fold_new_events(data, [event])

    assert data.activity == []
    assert data.feeding_stats == {}
