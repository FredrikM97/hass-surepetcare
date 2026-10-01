"""Tests for SurePetCareFeedingTimelineCoordinator's incremental polling.

Calls async_refresh(), not _async_update_data() directly - the latter
bypasses DataUpdateCoordinator's own self.data assignment, so the
cold-vs-incremental branching wouldn't see its own previous result.
"""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time
from pytest_homeassistant_custom_component.common import load_json_value_fixture
from surepcio.timeline import TimelineEvent

from custom_components.surepcha.const import (
    OPTION_TIMELINE,
    SCAN_INTERVAL,
    TIMELINE_POLLING_SPEED,
)
from custom_components.surepcha.coordinator import (
    SurePetCareFeedingTimelineCoordinator,
)


def _load_event(name: str) -> TimelineEvent:
    """Load one named event from feeding_timeline_frames.json."""
    raw = load_json_value_fixture("feeding_timeline_frames.json")
    return TimelineEvent(**raw[name])


@pytest.fixture
def coordinator(hass) -> SurePetCareFeedingTimelineCoordinator:
    """Return a feeding-timeline coordinator with a mocked client/entry."""
    client = MagicMock()
    client.api = AsyncMock()
    entry = MagicMock()
    entry.options = {}
    return SurePetCareFeedingTimelineCoordinator(hass, entry, client, 222527)


@pytest.fixture(autouse=True)
def _no_household_name_lookup():
    """These tests aren't about household-name resolution; keep client.api's
    side_effect list focused on timeline calls only."""
    with patch(
        "custom_components.surepcha.coordinator.fetch_household_name",
        AsyncMock(return_value=None),
    ):
        yield


def test_update_interval_defaults_to_scan_interval(hass) -> None:
    """With no configured option, the coordinator uses SCAN_INTERVAL."""
    entry = MagicMock()
    entry.options = {}
    coordinator = SurePetCareFeedingTimelineCoordinator(
        hass, entry, MagicMock(), 222527
    )
    assert coordinator.update_interval == timedelta(seconds=SCAN_INTERVAL)


def test_update_interval_uses_configured_polling_speed(hass) -> None:
    """A configured OPTION_TIMELINE polling speed overrides the default -
    matching SurePetCareHouseholdTimelineCoordinator's own polling rate,
    since both poll the same underlying timeline."""
    entry = MagicMock()
    entry.options = {OPTION_TIMELINE: {TIMELINE_POLLING_SPEED: 120}}
    coordinator = SurePetCareFeedingTimelineCoordinator(
        hass, entry, MagicMock(), 222527
    )
    assert coordinator.update_interval == timedelta(seconds=120)


async def test_first_poll_does_a_cold_rebuild_and_seeds_the_cursor(
    hass, coordinator
) -> None:
    """With no baseline yet, the first poll does the full backward walk (not
    an ambiguous since_id=None fetch), and seeds the incremental cursor from it."""
    event = _load_event("feeding_wet_and_dry")
    coordinator.client.api = AsyncMock(side_effect=[[event], []])

    await hass.config.async_set_time_zone("UTC")
    with freeze_time("2026-08-27T12:00:00+00:00"):
        await coordinator.async_refresh()

    assert coordinator.last_update_success is True
    # Backward walk: one page of events, then an empty page ends it.
    assert coordinator.client.api.await_count == 2
    assert coordinator.data.feeding_stats[472721].count == 1  # Maui
    assert coordinator._cursor == coordinator.data.cursor
    assert coordinator._pending_cursor == coordinator.data.cursor


async def test_same_day_poll_uses_incremental_since_id(hass, coordinator) -> None:
    """After the cold rebuild has run once today, a later poll fetches only
    new events via since_id, not the full backward walk again."""
    baseline = _load_event("feeding_wet_and_dry")  # Maui
    new = _load_event("bowl_filled").model_copy(
        update={
            "id": baseline.id + 1000,
            "created_at": baseline.created_at + timedelta(minutes=5),
        }
    )
    coordinator.client.api = AsyncMock(side_effect=[[baseline], [], [new]])

    await hass.config.async_set_time_zone("UTC")
    with freeze_time("2026-08-27T12:00:00+00:00"):
        await coordinator.async_refresh()  # cold rebuild
        await coordinator.async_refresh()  # same-day: incremental

    assert coordinator.last_update_success is True
    # 2 calls for the cold rebuild + 1 single forward call for the increment.
    assert coordinator.client.api.await_count == 3
    assert coordinator.data.feeding_stats[472721].count == 1  # unchanged
    assert [event["activity_type"] for event in coordinator.data.activity] == [
        "feeding",
        "bowl_filled",
    ]


async def test_late_arriving_lower_id_event_is_recovered_via_the_cursor_lag(
    hass, coordinator
) -> None:
    """Timeline ids aren't strictly ordered by created_at - an event that only
    appears on the server after the cursor has already advanced past its id
    must still be picked up on the next poll, not silently dropped for the
    rest of the day.
    """
    event_a = _load_event("feeding_wet_and_dry").model_copy(update={"id": 100})
    base_time = event_a.created_at
    event_c = _load_event("bowl_filled").model_copy(
        update={"id": 105, "created_at": base_time + timedelta(minutes=5)}
    )
    # Appears on the server only after poll 2 - a non-lagged cursor (which
    # would have already advanced to 105) could never see this again, since
    # its id (102) is below 105.
    event_b = _load_event("feeding_wet_only").model_copy(
        update={"id": 102, "created_at": base_time + timedelta(minutes=2)}
    )

    coordinator.client.api = AsyncMock(
        side_effect=[
            [event_a],
            [],  # poll 1: cold rebuild, cursor seeded to 100
            [event_c],  # poll 2: since_id=100 -> only event_c exists yet
            [event_b, event_c],  # poll 3: since_id is still 100 (lagged) -> both
        ]
    )

    await hass.config.async_set_time_zone("UTC")
    with freeze_time("2026-08-27T12:00:00+00:00"):
        await coordinator.async_refresh()  # poll 1
        await coordinator.async_refresh()  # poll 2
        await coordinator.async_refresh()  # poll 3

    assert coordinator.last_update_success is True
    assert coordinator.client.api.await_count == 4
    # All three events present - event_b was not permanently skipped despite
    # its id being lower than event_c's, which was already folded in by poll 2.
    assert len(coordinator.data.activity) == 3
    assert coordinator.data.feeding_stats[472721].count == 1  # Maui, event_a
    assert coordinator.data.feeding_stats[532070].count == 1  # Ajax, event_b
    # event_c (bowl_filled) was not double-counted despite being re-fetched
    # in both poll 2 and poll 3.
    bowl_filled_entries = [
        event
        for event in coordinator.data.activity
        if event["activity_type"] == "bowl_filled"
    ]
    assert len(bowl_filled_entries) == 1


async def test_day_rollover_triggers_a_fresh_cold_rebuild(hass, coordinator) -> None:
    """When local midnight passes between polls, the running aggregate must
    reset instead of carrying yesterday's totals into today."""
    event = _load_event("feeding_wet_and_dry")
    coordinator.client.api = AsyncMock(side_effect=[[event], []])

    await hass.config.async_set_time_zone("UTC")
    with freeze_time("2026-08-27T23:59:00+00:00"):
        await coordinator.async_refresh()
    assert coordinator.data.feeding_stats[472721].count == 1

    coordinator.client.api = AsyncMock(side_effect=[[]])
    with freeze_time("2026-08-28T00:05:00+00:00"):
        await coordinator.async_refresh()

    assert coordinator.last_update_success is True
    assert coordinator.data.feeding_stats == {}
    assert coordinator.data.activity == []


async def test_empty_day_keeps_doing_cheap_cold_walks_until_something_happens(
    hass, coordinator
) -> None:
    """With nothing folded in yet today (no cursor), each poll must use the
    cutoff-aware backward walk rather than an ambiguous since_id=None fetch
    that could pull in yesterday's stragglers."""
    coordinator.client.api = AsyncMock(side_effect=[[], []])

    await hass.config.async_set_time_zone("UTC")
    with freeze_time("2026-08-27T01:00:00+00:00"):
        await coordinator.async_refresh()
        assert coordinator.data.cursor is None
        await coordinator.async_refresh()

    assert coordinator.last_update_success is True
    # Each poll did its own single-page cold walk (an empty page ends it
    # immediately), not an incremental fetch.
    assert coordinator.client.api.await_count == 2
    assert coordinator.data.activity == []
