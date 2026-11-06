"""Tests for the household timeline coordinator."""

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from surepcio import Household, SurePetcareClient
from surepcio.devices.pet import Pet
from surepcio.timeline import TimelineEvent
from syrupy.assertion import SnapshotAssertion

from custom_components.surepcha.const import (
    EVENT_TIMELINE,
)
from custom_components.surepcha.coordinator import (
    SurePetCareCoordinator,
)

from .support import MockConfigEntry, async_capture_events, load_json_value_fixture


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
async def timeline_coordinator(hass) -> SurePetCareCoordinator:
    """Return a timeline coordinator with a mocked client/household/entry."""
    client = MagicMock()
    client.api = AsyncMock()
    household = MagicMock()
    household.id = 7777
    entry = MagicMock()
    entry.options = {}
    coordinator = SurePetCareCoordinator(hass, entry, client, household, [])
    await coordinator._async_setup()
    return coordinator


def test_coordinator_starts_with_polling_disabled(hass) -> None:
    """Entity restoration must complete before setup enables interval polling."""
    entry = MagicMock()
    entry.options = {}
    coordinator = SurePetCareCoordinator(
        hass, entry, MagicMock(), MagicMock(id=7777), []
    )
    assert coordinator.update_interval is None


async def test_first_poll_sets_cursor_without_firing_events(
    hass, timeline_coordinator, timeline_events
) -> None:
    """The first poll after startup must not replay existing history as new events."""
    events = async_capture_events(hass, EVENT_TIMELINE)
    timeline_coordinator.client.api.return_value = timeline_events

    await timeline_coordinator._async_update_data()
    await hass.async_block_till_done()

    assert events == []
    assert timeline_coordinator.state._cursor == max(e.id for e in timeline_events)
    assert not timeline_coordinator.state._seen_ids


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
    # an API response repeating previously acknowledged IDs) - must not refire.
    await timeline_coordinator._async_update_data()
    await hass.async_block_till_done()
    assert len(events) == 1


def test_timeline_subscriptions_broadcast_raw_events_at_least_once(
    hass, mock_config_entry
):
    coordinator = SurePetCareCoordinator(
        hass,
        mock_config_entry,
        MagicMock(),
        MagicMock(id=7777),
        [],
    )
    event = TimelineEvent(
        id=1,
        type=0,
        created_at=None,
    )
    first, second = MagicMock(), MagicMock()
    unsubscribe_first = coordinator.async_subscribe_timeline(first)
    unsubscribe_second = coordinator.async_subscribe_timeline(second)
    report_listener = MagicMock()
    unsubscribe_reports = coordinator.async_add_listener(report_listener)

    coordinator._publish_timeline(event)
    coordinator._publish_timeline(event)

    first.assert_has_calls([call(event), call(event)])
    second.assert_has_calls([call(event), call(event)])
    unsubscribe_first()
    coordinator._publish_timeline(event)
    first.assert_has_calls([call(event), call(event)])
    second.assert_has_calls([call(event), call(event), call(event)])
    unsubscribe_second()
    assert coordinator._timeline_listeners == []
    report_listener.assert_not_called()
    unsubscribe_reports()


async def test_command_target_refresh_notifies_once_after_device_phase(
    timeline_coordinator,
):
    device = MagicMock()
    listener = MagicMock()
    unsubscribe = timeline_coordinator.async_add_listener(listener)

    async def refresh(target, *, publish):
        assert target is device
        publish(target)
        listener.assert_not_called()

    timeline_coordinator.state.refresh_device = AsyncMock(side_effect=refresh)
    await timeline_coordinator.async_refresh_device(device)
    listener.assert_called_once_with()
    unsubscribe()


async def test_event_payload_includes_movement_details(
    hass, timeline_coordinator, timeline_events, snapshot: SnapshotAssertion
) -> None:
    """Fired events expose movement direction/device_id for automations to key off."""
    events = async_capture_events(hass, EVENT_TIMELINE)

    # First poll establishes an empty baseline.
    timeline_coordinator.client.api.return_value = []
    await timeline_coordinator._async_update_data()
    await hass.async_block_till_done()

    # Second poll: the event under test arrives and is fired.
    timeline_coordinator.client.api.return_value = timeline_events[:1]
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
    assert timeline_coordinator.state._cursor == 0


async def test_empty_initial_history_does_not_suppress_first_new_event(
    hass,
    timeline_coordinator,
    timeline_events,
) -> None:
    events = async_capture_events(hass, EVENT_TIMELINE)
    timeline_coordinator.client.api.return_value = []
    await timeline_coordinator._async_update_data()
    timeline_coordinator.client.api.return_value = timeline_events[:1]
    await timeline_coordinator._async_update_data()
    await hass.async_block_till_done()
    assert len(events) == 1


async def test_restart_restores_only_cursor_without_history(hass):
    entry = MockConfigEntry(domain="surepcha", data={}, options={})
    client = SurePetcareClient()
    pet = Pet({"id": 10, "household_id": 7, "name": "Cat"})
    history = TimelineEvent(
        id=100,
        type=0,
        created_at="2026-01-01T12:00:00+00:00",
        pets=[{"id": 10}],
        movements=[{"id": 1, "device_id": 20, "direction": 1}],
    )
    requests = []

    async def respond(command):
        if "timeline" in command.endpoint:
            requests.append(command.params)
            return [history] if "since_id" not in command.params else []
        return pet

    client.api = AsyncMock(side_effect=respond)
    first = SurePetCareCoordinator(hass, entry, client, Household({"id": 7}), [pet])
    await first._async_setup()
    await first._async_update_data()
    assert first.state.seen_id == 100
    assert requests == [{"page_size": 25}]
    requests.clear()

    restarted = SurePetCareCoordinator(hass, entry, client, Household({"id": 7}), [pet])
    await restarted._async_setup()
    await restarted._async_update_data()
    assert requests == [{"since_id": 100, "page_size": 25}]
    assert restarted.state.seen_id == 100
    assert await first._store.async_load() == {"seen_id": 100}


async def test_empty_checkpoint_survives_restart(hass):
    entry = MockConfigEntry(domain="surepcha", data={}, options={})
    client = SurePetcareClient()
    client.api = AsyncMock(return_value=[])
    first = SurePetCareCoordinator(hass, entry, client, Household({"id": 7}), [])
    await first._async_setup()
    await first._async_update_data()
    restarted = SurePetCareCoordinator(hass, entry, client, Household({"id": 7}), [])
    await restarted._async_setup()
    client.api.reset_mock()
    await restarted._async_update_data()
    assert client.api.call_args.args[0].params == {"since_id": 0, "page_size": 25}


async def test_failed_timeline_poll_keeps_durable_cursor(hass):
    entry = MockConfigEntry(domain="surepcha", data={}, options={})
    client = SurePetcareClient()
    client.api = AsyncMock(return_value=[])
    coordinator = SurePetCareCoordinator(hass, entry, client, Household({"id": 7}), [])
    await coordinator._async_setup()
    await coordinator._async_update_data()
    client.api.side_effect = TimeoutError("Timeline unavailable")
    await coordinator._async_update_data()
    checkpoint = await coordinator._store.async_load()
    assert checkpoint["seen_id"] == 0
    assert coordinator.state.seen_id == 0


async def test_checkpoint_write_error_is_not_silently_ignored(hass):
    entry = MockConfigEntry(domain="surepcha", data={}, options={})
    client = SurePetcareClient()
    client.api = AsyncMock(return_value=[])
    coordinator = SurePetCareCoordinator(hass, entry, client, Household({"id": 7}), [])
    await coordinator._async_setup()
    coordinator._store.async_save = AsyncMock(side_effect=OSError("Disk full"))
    with pytest.raises(OSError, match="Disk full"):
        await coordinator._async_update_data()


async def test_legacy_checkpoint_extras_are_stripped_after_cursor_restore(hass):
    entry = MockConfigEntry(domain="surepcha", data={}, options={})
    client = SurePetcareClient()
    client.api = AsyncMock(return_value=[])
    coordinator = SurePetCareCoordinator(hass, entry, client, Household({"id": 7}), [])
    coordinator._store.async_save = AsyncMock()
    coordinator._store.async_load = AsyncMock(
        return_value={
            "household_id": 7,
            "seen_id": 100,
            "readings": [
                {
                    "device_id": 10,
                    "code": "position",
                    "value": "INSIDE",
                    "attributes": {},
                }
            ],
        }
    )
    await coordinator._async_setup()
    await coordinator._async_update_data()
    assert coordinator.state.seen_id == 100
    assert client.api.call_args.args[0].params == {"since_id": 100, "page_size": 25}
    coordinator._store.async_save.assert_awaited_once_with(
        {"seen_id": 100}
    )


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
    timeline_coordinator.client.api.return_value = []
    await timeline_coordinator._async_update_data()
    await hass.async_block_till_done()
    assert events == []

    # Second poll: the remaining real events arrive, including the one with
    # an empty pets list - must not raise and must fire both.
    timeline_coordinator.client.api.return_value = real_events[1:]
    await timeline_coordinator._async_update_data()
    await hass.async_block_till_done()

    assert len(events) == 2
    assert [event.data for event in events] == snapshot


async def test_event_payload_preserves_api_data(
    hass, timeline_coordinator, timeline_events, snapshot: SnapshotAssertion
) -> None:
    """The API data string is preserved; automations can decode it if needed."""
    curfew_events = _load_scenario("curfew")
    events = async_capture_events(hass, EVENT_TIMELINE)

    # First poll: an unrelated event establishes the baseline, consumed without firing.
    timeline_coordinator.client.api.return_value = timeline_events[:1]
    await timeline_coordinator._async_update_data()
    await hass.async_block_till_done()

    # Second poll: the curfew events arrive and are fired.
    timeline_coordinator.client.api.return_value = curfew_events
    await timeline_coordinator._async_update_data()
    await hass.async_block_till_done()

    assert len(events) == 4
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
    timeline_coordinator.client.api.return_value = []
    await timeline_coordinator._async_update_data()
    await hass.async_block_till_done()
    assert events == []

    # Second poll: the remaining real events arrive and must fire correctly.
    timeline_coordinator.client.api.return_value = real_events[1:]
    await timeline_coordinator._async_update_data()
    await hass.async_block_till_done()

    assert len(events) == 2
    assert [event.data for event in events] == snapshot
