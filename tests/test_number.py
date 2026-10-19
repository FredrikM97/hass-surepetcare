from unittest.mock import patch

import pytest
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from surepcio import SurePetcareClient
from surepcio.devices.device import DeviceBase, PetBase
from surepcio.timeline import TimelineEvent
from syrupy.assertion import SnapshotAssertion

from . import initialize_entry
from .support import MockConfigEntry, snapshot_platform


@patch("custom_components.surepcha.PLATFORMS", [Platform.NUMBER])
@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("entity_registry_enabled_default")
@pytest.mark.asyncio
async def test_platform_setup_and_discovery(
    hass: HomeAssistant,
    mock_client,
    mock_timeline_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    mock_devices,
    mock_pets,
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


@patch("custom_components.surepcha.PLATFORMS", [Platform.NUMBER])
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


@patch("custom_components.surepcha.PLATFORMS", [Platform.NUMBER])
@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("entity_registry_enabled_default")
@pytest.mark.asyncio
@pytest.mark.parametrize("target_index", [0, 1])
async def test_number_set_and_snapshot(
    hass: HomeAssistant,
    mock_client: SurePetcareClient,
    mock_timeline_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    mock_devices: list[DeviceBase],
    mock_pets: list[PetBase],
    timeline_event_responses: tuple[list[TimelineEvent], list[TimelineEvent]],
    target_index: int,
) -> None:
    await initialize_entry(
        hass,
        mock_client,
        mock_timeline_config_entry,
        mock_devices,
        mock_pets,
        timeline_event_responses,
    )
    await hass.async_block_till_done()

    entity_id = entity_registry.async_get_entity_id(
        "number", "surepcha", f"22222-bowl_{target_index}_target_weight"
    )
    assert entity_id is not None
    for value in (0.0, 150.0, 300.0):
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": entity_id, "value": value},
            blocking=True,
        )
        await hass.async_block_till_done()
        updated_state = hass.states.get(entity_id)
        assert updated_state is not None
        assert updated_state == snapshot(name=f"{entity_id}-{value}")
        command = mock_client.api.await_args_list[-1].args[0]
        assert command.params["bowls"]["settings"][target_index]["target"] == value
