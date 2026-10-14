from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import restore_state
from surepcio import SurePetcareClient
from surepcio.devices.device import DeviceBase, PetBase
from surepcio.timeline import TimelineEvent
from syrupy.assertion import SnapshotAssertion

from custom_components.surepcha.sensor import _bowl_weight_attributes

from . import initialize_entry
from .support import MockConfigEntry, snapshot_platform


def test_bowl_weight_attributes_when_second_bowl_is_missing() -> None:
    ctx = SimpleNamespace(
        device=SimpleNamespace(
            status=SimpleNamespace(bowl_status=[object()]),
            control=SimpleNamespace(bowls=SimpleNamespace(settings=[object()])),
        )
    )

    assert _bowl_weight_attributes(ctx, 1) == {
        "position": None,
        "food_type": None,
        "last_filled_at": None,
        "last_zeroed_at": None,
        "last_fill_weight": None,
        "substance_type": None,
    }


@patch("custom_components.surepcha.PLATFORMS", [Platform.SENSOR])
@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("entity_registry_enabled_default")
@pytest.mark.asyncio
async def test_platform_setup_and_discovery(
    hass: HomeAssistant,
    mock_client,
    mock_timeline_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    mock_devices: list[DeviceBase],
    mock_pets: list[PetBase],
    timeline_event_responses: tuple[list[TimelineEvent], list[TimelineEvent]],
) -> None:
    await initialize_entry(
        hass,
        mock_client,
        mock_timeline_config_entry,
        mock_devices,
        mock_pets,
        timeline_event_responses,
    )
    await snapshot_platform(
        hass, entity_registry, snapshot, mock_timeline_config_entry.entry_id
    )


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
    mock_devices: list[DeviceBase],
    mock_pets: list[PetBase],
    timeline_event_responses: tuple[list[TimelineEvent], list[TimelineEvent]],
) -> None:
    await initialize_entry(
        hass,
        mock_client,
        mock_config_entry_missing_entities,
        mock_devices,
        mock_pets,
        timeline_event_responses,
    )
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
    mock_timeline_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    mock_devices,
    mock_pets,
    timeline_event_responses: tuple[list[TimelineEvent], list[TimelineEvent]],
    timeline_events: list[TimelineEvent],
) -> None:
    """Event-backed sensor values persist until the timeline provides a replacement."""
    await restore_state.async_load(hass, load_empty=True)
    await initialize_entry(
        hass,
        mock_client,
        mock_timeline_config_entry,
        mock_devices,
        mock_pets,
        timeline_event_responses,
    )
    expected_states = {
        "22222-bowl_0_weight": "48",
        "22222-bowl_1_weight": "0",
        "22222-fill_percent": "24.2424242424242",
        "22222-weight_capacity": "198",
        "472721-feeding": "2",
        "333333-last_activity": "Feeder",
    }
    for unique_id, expected_state in expected_states.items():
        entity_id = entity_registry.async_get_entity_id("sensor", "surepcha", unique_id)
        assert entity_id is not None
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == expected_state

    assert await hass.config_entries.async_unload(mock_timeline_config_entry.entry_id)
    await initialize_entry(
        hass,
        mock_client,
        mock_timeline_config_entry,
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


@patch("custom_components.surepcha.PLATFORMS", [Platform.SENSOR])
@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("entity_registry_enabled_default")
@pytest.mark.asyncio
async def test_event_sensor_initial_values_use_timeline_history(
    hass: HomeAssistant,
    mock_client: SurePetcareClient,
    mock_timeline_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    mock_devices: list[DeviceBase],
    mock_pets: list[PetBase],
    timeline_events: list[TimelineEvent],
) -> None:
    await initialize_entry(
        hass,
        mock_client,
        mock_timeline_config_entry,
        mock_devices,
        mock_pets,
        (timeline_events,),
    )

    expected_states = {
        "22222-bowl_0_weight": "48",
        "22222-weight_capacity": "198",
        "472721-feeding": "2",
        "472721-drinking": "4",
        "472721-last_activity": "Poseidon connect",
    }
    for unique_id, expected_state in expected_states.items():
        entity_id = entity_registry.async_get_entity_id("sensor", "surepcha", unique_id)
        assert entity_id is not None
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == expected_state


@patch("custom_components.surepcha.PLATFORMS", [Platform.SENSOR])
@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("entity_registry_enabled_default")
@pytest.mark.asyncio
async def test_event_sensor_without_timeline_event_is_unavailable(
    hass: HomeAssistant,
    mock_client: SurePetcareClient,
    mock_timeline_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    mock_devices: list[DeviceBase],
    mock_pets: list[PetBase],
) -> None:
    await initialize_entry(
        hass,
        mock_client,
        mock_timeline_config_entry,
        mock_devices,
        mock_pets,
        ([],),
    )

    event_backed_unique_ids = (
        "269654-bowl_0_weight",
        "269654-bowl_1_weight",
        "269654-fill_percent",
        "269654-weight_capacity",
        "472721-feeding",
        "472721-position",
        "472721-drinking",
        "472721-last_activity",
    )
    for unique_id in event_backed_unique_ids:
        entity_id = entity_registry.async_get_entity_id("sensor", "surepcha", unique_id)
        assert entity_id is not None
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == "unavailable"
