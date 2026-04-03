import pytest
from unittest.mock import patch
from syrupy.assertion import SnapshotAssertion

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import async_get as async_get_device_registry
from surepcio.enums import ProductId
from custom_components.surepcha.const import DOMAIN

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
async def test_position_switch_sets_command_device(
    hass: HomeAssistant,
    mock_client,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    mock_devices,
    mock_pets,
) -> None:
    await initialize_entry(
        hass, mock_client, mock_config_entry, mock_devices, mock_pets
    )
    await hass.async_block_till_done()

    device_registry = async_get_device_registry(hass)
    pet_entry = next(
        d
        for d in device_registry.devices.values()
        if any(ident[0] == DOMAIN for ident in d.identifiers)
        and getattr(d, "model_id", None) == ProductId.PET
    )
    pet_surepetcare_id = next(
        ident[1] for ident in pet_entry.identifiers if ident[0] == DOMAIN
    )
    position_entity_id = next(
        entity_id
        for entity_id in hass.states.async_entity_ids("switch")
        if entity_id.endswith("_position")
    )

    mock_client.api.reset_mock()

    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": position_entity_id},
        blocking=True,
    )
    await hass.async_block_till_done()

    command = mock_client.api.await_args_list[0].args[0]
    assert command.device is not None
    assert str(command.device.id) == pet_surepetcare_id
