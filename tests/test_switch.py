import pytest
from unittest.mock import patch
from syrupy.assertion import SnapshotAssertion
from surepcio.enums import PetLocation

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import initialize_entry

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    snapshot_platform,
)


@patch("custom_components.surepcha.PLATFORMS", [Platform.SWITCH])
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
) -> None:
    await initialize_entry(
        hass, mock_client, mock_config_entry, mock_devices, mock_pets
    )
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


@patch("custom_components.surepcha.PLATFORMS", [Platform.SWITCH])
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
) -> None:
    await initialize_entry(
        hass, mock_client, mock_config_entry_missing_entities, mock_devices, mock_pets
    )
    await snapshot_platform(
        hass, entity_registry, snapshot, mock_config_entry_missing_entities.entry_id
    )


@patch("custom_components.surepcha.PLATFORMS", [Platform.SWITCH])
@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("entity_registry_enabled_default")
@pytest.mark.asyncio
async def test_switch_toggle_and_snapshot(
    hass: HomeAssistant,
    mock_client,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    mock_devices,
    mock_pets,
) -> None:
    await initialize_entry(
        hass, mock_client, mock_config_entry, mock_devices, mock_pets
    )
    await hass.async_block_till_done()

    # Iterate over all switch entities
    for entity_id in hass.states.async_entity_ids("switch"):
        # Turn on the switch
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": entity_id},
            blocking=True,
        )
        await hass.async_block_till_done()
        state_on = hass.states.get(entity_id)
        assert state_on is not None
        assert state_on == snapshot(name=f"{entity_id}-on")

        # Turn off the switch
        await hass.services.async_call(
            "switch",
            "turn_off",
            {"entity_id": entity_id},
            blocking=True,
        )
        await hass.async_block_till_done()
        state_off = hass.states.get(entity_id)
        assert state_off is not None
        assert state_off == snapshot(name=f"{entity_id}-off")


@patch("custom_components.surepcha.PLATFORMS", [Platform.SWITCH])
@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("entity_registry_enabled_default")
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case_name", "raw_where", "expected_state"),
    [
        ("inside", PetLocation.INSIDE, "off"),
        ("outside", PetLocation.OUTSIDE, "on"),
        ("unknown", 999, "unavailable"),
        ("none", None, "unavailable"),
    ],
)
async def test_position_switch_mapping_snapshot(
    hass: HomeAssistant,
    mock_client,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    mock_devices,
    mock_pets,
    case_name: str,
    raw_where: PetLocation | int | None,
    expected_state: str,
) -> None:
    """Snapshot full position switch states for raw pet position values."""
    pets_by_id = {pet.id: pet for pet in mock_pets}
    pets_by_id[472721].status.activity.where = raw_where
    pets_by_id[532070].status.activity.where = raw_where

    await initialize_entry(
        hass, mock_client, mock_config_entry, mock_devices, mock_pets
    )
    await hass.async_block_till_done()

    for entity_id in ("switch.ajax_position", "switch.maui_position"):
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == expected_state
        assert state == snapshot(name=f"position-mapping-{case_name}-{entity_id}")
