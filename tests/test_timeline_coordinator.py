"""Tests for the household timeline coordinator."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_homeassistant_custom_component.common import (
    async_capture_events,
    load_json_value_fixture,
)
from surepcio.timeline import TimelineEvent
from syrupy.assertion import SnapshotAssertion

from custom_components.surepcha.const import (
    EVENT_TIMELINE,
    OPTION_TIMELINE,
    SCAN_INTERVAL,
    TIMELINE_POLLING_SPEED,
)
from custom_components.surepcha.coordinator import (
    SurePetCareHouseholdTimelineCoordinator,
)


def _load_scenario(name: str) -> list[TimelineEvent]:
    """Load one scenario (movement/feeding/household) from timeline.json as TimelineEvents.

    get_timeline()'s Command always applies its parse step, so it returns
    TimelineEvent objects, matching what's built here from the raw fixture.
    """
    raw = load_json_value_fixture("timeline.json")
    return [TimelineEvent(**item) for item in raw[name]]


@pytest.fixture
def timeline_events() -> list[TimelineEvent]:
    """Load the "movement" scenario events."""
    return _load_scenario("movement")


@pytest.fixture
def timeline_coordinator(hass) -> SurePetCareHouseholdTimelineCoordinator:
    """Return a timeline coordinator with a mocked client/household/entry."""
    client = MagicMock()
    client.api = AsyncMock()
    household = MagicMock()
    household.id = 7777
    entry = MagicMock()
    entry.options = {}
    return SurePetCareHouseholdTimelineCoordinator(hass, entry, client, household)


def test_update_interval_defaults_to_scan_interval(hass) -> None:
    """With no configured option, the timeline coordinator uses SCAN_INTERVAL."""
    entry = MagicMock()
    entry.options = {}
    coordinator = SurePetCareHouseholdTimelineCoordinator(
        hass, entry, MagicMock(), MagicMock(id=7777)
    )
    assert coordinator.update_interval == timedelta(seconds=SCAN_INTERVAL)


def test_update_interval_uses_configured_polling_speed(hass) -> None:
    """A configured OPTION_TIMELINE polling speed overrides the default."""
    entry = MagicMock()
    entry.options = {OPTION_TIMELINE: {TIMELINE_POLLING_SPEED: 120}}
    coordinator = SurePetCareHouseholdTimelineCoordinator(
        hass, entry, MagicMock(), MagicMock(id=7777)
    )
    assert coordinator.update_interval == timedelta(seconds=120)


async def test_first_poll_sets_cursor_without_firing_events(
    hass, timeline_coordinator, timeline_events
) -> None:
    """The first poll after startup must not replay existing history as new events."""
    events = async_capture_events(hass, EVENT_TIMELINE)
    timeline_coordinator.client.api.return_value = timeline_events

    await timeline_coordinator._async_update_data()
    await hass.async_block_till_done()

    assert events == []
    assert timeline_coordinator._cursor == max(e.id for e in timeline_events)


async def test_second_poll_fires_only_new_events_sorted_by_created_at(
    hass, timeline_coordinator, timeline_events, snapshot: SnapshotAssertion
) -> None:
    """New events since the cursor are fired in created_at order, oldest first."""
    events = async_capture_events(hass, EVENT_TIMELINE)
    timeline_coordinator.client.api.return_value = timeline_events[:2]
    await timeline_coordinator._async_update_data()
    await hass.async_block_till_done()
    assert events == []

    timeline_coordinator.client.api.return_value = timeline_events
    await timeline_coordinator._async_update_data()
    await hass.async_block_till_done()

    # Fixture events 2..3 (indices) are the ones not seen on the first poll,
    # and must be fired oldest-created_at-first.
    assert [event.data for event in events] == snapshot


async def test_dedupe_prevents_refiring_a_seen_event(
    hass, timeline_coordinator, timeline_events
) -> None:
    """An event id already fired must not be fired again on a later poll."""
    events = async_capture_events(hass, EVENT_TIMELINE)

    # First poll: baseline event, consumed without firing.
    timeline_coordinator.client.api.return_value = timeline_events[:1]
    await timeline_coordinator._async_update_data()
    await hass.async_block_till_done()
    assert events == []

    # Second poll: a new event arrives and is fired for the first time.
    timeline_coordinator.client.api.return_value = timeline_events[:2]
    await timeline_coordinator._async_update_data()
    await hass.async_block_till_done()
    assert len(events) == 1

    # Third poll: the API returns the same accumulated events again (e.g. the
    # lagging cursor re-requesting an overlapping window) - must not refire.
    await timeline_coordinator._async_update_data()
    await hass.async_block_till_done()
    assert len(events) == 1


async def test_event_payload_includes_movement_details(
    hass, timeline_coordinator, timeline_events, snapshot: SnapshotAssertion
) -> None:
    """Fired events expose movement direction/device_id for automations to key off."""
    events = async_capture_events(hass, EVENT_TIMELINE)

    # First poll: a different event establishes the baseline, consumed without firing.
    timeline_coordinator.client.api.return_value = timeline_events[1:2]
    await timeline_coordinator._async_update_data()
    await hass.async_block_till_done()

    # Second poll: the event under test arrives and is fired.
    timeline_coordinator.client.api.return_value = timeline_events[:2]
    await timeline_coordinator._async_update_data()
    await hass.async_block_till_done()

    assert len(events) == 1
    assert events[0].data == snapshot


async def test_no_events_returned_is_a_no_op(hass, timeline_coordinator) -> None:
    """An empty timeline response must not raise and must not fire anything."""
    events = async_capture_events(hass, EVENT_TIMELINE)
    timeline_coordinator.client.api.return_value = []

    await timeline_coordinator._async_update_data()
    await hass.async_block_till_done()

    assert events == []
    assert timeline_coordinator._cursor is None


async def test_real_feeding_events_with_empty_pets(
    hass, timeline_coordinator, snapshot: SnapshotAssertion
) -> None:
    """Real feeding events have no "movements"; a WEIGHT_CHANGED event has no pets.

    The "feeding" scenario in timeline.json is a redacted sample of real
    production data: two FEEDING events with populated pets/devices, plus a
    WEIGHT_CHANGED event with populated devices but an empty pets list.
    """
    real_events = _load_scenario("feeding")
    events = async_capture_events(hass, EVENT_TIMELINE)

    # First poll: baseline, consumed without firing.
    timeline_coordinator.client.api.return_value = real_events[:1]
    await timeline_coordinator._async_update_data()
    await hass.async_block_till_done()
    assert events == []

    # Second poll: the remaining real events arrive, including the one with
    # an empty pets list - must not raise and must fire both.
    timeline_coordinator.client.api.return_value = real_events
    await timeline_coordinator._async_update_data()
    await hass.async_block_till_done()

    assert len(events) == 2
    assert [event.data for event in events] == snapshot


async def test_real_household_events_with_no_devices_or_pets(
    hass, timeline_coordinator, snapshot: SnapshotAssertion
) -> None:
    """Household-membership events populate households/users but nothing else.

    The "household" scenario in timeline.json is a redacted sample of real
    production data (USER_JOINED_HOUSEHOLD, ACCOUNT_CREATED), including one
    event with an empty "households" list.
    """
    real_events = _load_scenario("household")
    events = async_capture_events(hass, EVENT_TIMELINE)

    # First poll: baseline, consumed without firing.
    timeline_coordinator.client.api.return_value = real_events[:1]
    await timeline_coordinator._async_update_data()
    await hass.async_block_till_done()
    assert events == []

    # Second poll: the remaining real events arrive and must fire correctly.
    timeline_coordinator.client.api.return_value = real_events
    await timeline_coordinator._async_update_data()
    await hass.async_block_till_done()

    assert len(events) == 2
    assert [event.data for event in events] == snapshot
