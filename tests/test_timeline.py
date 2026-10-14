from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import Event, HomeAssistant, callback
from surepcio import Household, SurePetcareClient
from surepcio.timeline import TimelineEvent
from syrupy.assertion import SnapshotAssertion

from custom_components.surepcha.coordinator import (
    SurePetCareHouseholdTimelineCoordinator,
)
from custom_components.surepcha.timeline import build_event_payload

from .support import MockConfigEntry


def test_timeline_fixture_payloads(
    timeline_events: list[TimelineEvent], snapshot: SnapshotAssertion
) -> None:
    """Snapshot the serialized payloads for all representative timeline events."""
    assert {
        str(event.id): build_event_payload(222527, event) for event in timeline_events
    } == snapshot


@pytest.mark.asyncio
async def test_timeline_coordinator_resumes_after_restart(
    hass: HomeAssistant,
    mock_client: SurePetcareClient,
    mock_timeline_config_entry: MockConfigEntry,
    baseline_movement_timeline_event: TimelineEvent,
    feeding_timeline_event: TimelineEvent,
    second_feeder_timeline_event: TimelineEvent,
) -> None:
    fired_event_ids: list[int] = []

    @callback
    def record_event(event: Event) -> None:
        fired_event_ids.append(event.data["id"])

    hass.bus.async_listen("surepcha_timeline_event", record_event)
    household = MagicMock(spec=Household)
    household.id = 222527
    timeline_command = MagicMock()
    household.get_timeline.return_value = timeline_command
    first_store = AsyncMock()
    first_store.async_load.return_value = None
    resumed_store = AsyncMock()
    mock_client.api = AsyncMock(
        side_effect=[
            [baseline_movement_timeline_event],
            [feeding_timeline_event],
            [feeding_timeline_event, second_feeder_timeline_event],
        ]
    )

    with patch(
        "custom_components.surepcha.coordinator.Store",
        side_effect=[first_store, resumed_store],
    ):
        coordinator = SurePetCareHouseholdTimelineCoordinator(
            hass, mock_timeline_config_entry, mock_client, household
        )
        await coordinator._async_setup()
        await coordinator._async_update_data()
        assert [event["id"] for event in coordinator.recent_events] == [
            baseline_movement_timeline_event.id
        ]
        await coordinator._async_update_data()
        await hass.async_block_till_done()

        resumed_store.async_load.return_value = first_store.async_save.await_args.args[
            0
        ]
        resumed = SurePetCareHouseholdTimelineCoordinator(
            hass, mock_timeline_config_entry, mock_client, household
        )
        await resumed._async_setup()
        await resumed._async_update_data()
        await hass.async_block_till_done()

    assert fired_event_ids == [
        feeding_timeline_event.id,
        second_feeder_timeline_event.id,
    ]
    assert household.get_timeline.call_args_list[-1].kwargs == {
        "since_id": baseline_movement_timeline_event.id
    }
