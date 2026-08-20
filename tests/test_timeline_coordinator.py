"""Tests for the household timeline coordinator."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_homeassistant_custom_component.common import (
    async_capture_events,
    load_json_value_fixture,
)
from syrupy.assertion import SnapshotAssertion

from custom_components.surepcha.const import EVENT_TIMELINE
from custom_components.surepcha.coordinator import (
    SurePetCareHouseholdTimelineCoordinator,
)


class DummyEnumValue:
    """Minimal stand-in for a surepcio enum member; only .name is used."""

    def __init__(self, name: str) -> None:
        self.name = name


# The real surepcio enum member names aren't relevant here: the coordinator only
# ever forwards whatever `.name` the library gives it, so any distinct labels
# are enough to verify our own dedupe/ordering/payload logic.
_DIRECTION_NAMES = {0: "LOOKED_THROUGH", 1: "ENTERED", 2: "LEFT"}


class DummyEntityRef:
    """Minimal stand-in for a TimelineEntityInfo; only .id is used."""

    def __init__(self, data: dict) -> None:
        self.id = data["id"]


class DummyMovement:
    """Minimal stand-in for a MovementResource."""

    def __init__(self, data: dict) -> None:
        self.device_id = data.get("device_id")
        direction = data.get("direction")
        self.direction = (
            DummyEnumValue(_DIRECTION_NAMES[direction])
            if direction in _DIRECTION_NAMES
            else None
        )
        self.side = None


class DummyTimelineEvent:
    """Minimal stand-in for a TimelineEvent, built from a fixture dict."""

    def __init__(self, data: dict) -> None:
        self.id = data["id"]
        self.event_type = DummyEnumValue(f"TYPE_{data['type']}")
        self.created_at = (
            datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None
        )
        self.pets = [DummyEntityRef(p) for p in data.get("pets", [])]
        self.devices = [DummyEntityRef(d) for d in data.get("devices", [])]
        self.users = [DummyEntityRef(u) for u in data.get("users", [])]
        self.movements = [DummyMovement(m) for m in data.get("movements", [])]


@pytest.fixture
def timeline_events() -> list[DummyTimelineEvent]:
    """Load the timeline fixture as a list of dummy TimelineEvent-like objects."""
    raw = load_json_value_fixture("timeline.json")
    return [DummyTimelineEvent(item) for item in raw]


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
