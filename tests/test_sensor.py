from unittest.mock import patch

import pytest
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import restore_state
from surepcio.timeline import TimelineEvent
from syrupy.assertion import SnapshotAssertion

from . import initialize_entry
from .support import MockConfigEntry, snapshot_platform


@patch("custom_components.surepcha.PLATFORMS", [Platform.SENSOR])
@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("entity_registry_enabled_default")
@pytest.mark.asyncio
async def test_platform_setup_and_discovery(
    hass: HomeAssistant,
    mock_client,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    mock_devices,
    mock_pets,
    pet_and_two_feeder_timeline_event_responses: tuple[
        list[TimelineEvent], list[TimelineEvent]
    ],
) -> None:
    await initialize_entry(
        hass,
        mock_client,
        mock_config_entry,
        mock_devices,
        mock_pets,
        pet_and_two_feeder_timeline_event_responses,
    )
    timeline_coordinator = mock_config_entry.runtime_data.timeline_coordinators[0]
    await timeline_coordinator.async_request_refresh()
    await hass.async_block_till_done()
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


@patch("custom_components.surepcha.PLATFORMS", [Platform.SENSOR])
@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("entity_registry_enabled_default")
@pytest.mark.asyncio
async def test_platform_setup_and_discovery_missing_entities(
    hass: HomeAssistant,
    mock_client,
    mock_config_entry_missing_entities: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    mock_devices,
    mock_pets,
    pet_and_two_feeder_timeline_event_responses: tuple[
        list[TimelineEvent], list[TimelineEvent]
    ],
) -> None:
    await initialize_entry(
        hass,
        mock_client,
        mock_config_entry_missing_entities,
        mock_devices,
        mock_pets,
        pet_and_two_feeder_timeline_event_responses,
    )
    timeline_coordinator = (
        mock_config_entry_missing_entities.runtime_data.timeline_coordinators[0]
    )
    await timeline_coordinator.async_request_refresh()
    await hass.async_block_till_done()
    await snapshot_platform(
        hass, entity_registry, snapshot, mock_config_entry_missing_entities.entry_id
    )


@patch("custom_components.surepcha.PLATFORMS", [Platform.SENSOR])
@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("entity_registry_enabled_default")
@pytest.mark.asyncio
async def test_event_sensor_states_restore_on_reload(
    hass: HomeAssistant,
    mock_client,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    mock_devices,
    mock_pets,
    pet_and_feeder_timeline_event_responses: tuple[
        list[TimelineEvent], list[TimelineEvent]
    ],
    timeline_events: list[TimelineEvent],
) -> None:
    """Event-backed sensor values persist until the timeline provides a replacement."""
    await restore_state.async_load(hass, load_empty=True)
    await initialize_entry(
        hass,
        mock_client,
        mock_config_entry,
        mock_devices,
        mock_pets,
        pet_and_feeder_timeline_event_responses,
    )
    timeline_coordinator = mock_config_entry.runtime_data.timeline_coordinators[0]
    await timeline_coordinator.async_request_refresh()
    await hass.async_block_till_done()

    expected_states = {
        "269654-bowl_0_weight": "48",
        "269654-bowl_1_weight": "0",
        "269654-fill_percent": "24.2424242424242",
        "269654-weight_capacity": "198",
        "472721-last_activity": "Feeder",
    }
    for unique_id, expected_state in expected_states.items():
        entity_id = entity_registry.async_get_entity_id("sensor", "surepcha", unique_id)
        assert entity_id is not None
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == expected_state

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await initialize_entry(
        hass,
        mock_client,
        mock_config_entry,
        mock_devices,
        mock_pets,
        (timeline_events,),
    )

    for unique_id, expected_state in expected_states.items():
        entity_id = entity_registry.async_get_entity_id("sensor", "surepcha", unique_id)
        assert entity_id is not None
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == expected_state
