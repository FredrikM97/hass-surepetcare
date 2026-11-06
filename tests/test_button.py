from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from syrupy.assertion import SnapshotAssertion

from custom_components.surepcha.button import (
    SurePetCareButton,
    SurePetCareButtonEntityDescription,
)

from . import initialize_entry
from .support import MockConfigEntry, snapshot_platform


async def test_button_press_sends_true_to_command_and_refreshes_device():
    device = MagicMock(id=42)
    command = MagicMock(return_value="api-command")
    description = SurePetCareButtonEntityDescription(key="example", command=command)
    coordinator = MagicMock()
    coordinator.client.api = AsyncMock(return_value="sent")
    coordinator.async_refresh_device = AsyncMock()
    entity = SurePetCareButton(coordinator, device, description)

    await entity.async_press()

    command.assert_called_once_with(entity, True)
    coordinator.client.api.assert_awaited_once_with("api-command")
    coordinator.async_refresh_device.assert_awaited_once_with(device)


@patch("custom_components.surepcha.PLATFORMS", [Platform.BUTTON])
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


@patch("custom_components.surepcha.PLATFORMS", [Platform.BUTTON])
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


@patch("custom_components.surepcha.PLATFORMS", [Platform.BUTTON])
@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("entity_registry_enabled_default")
@pytest.mark.asyncio
async def test_button_press_and_snapshot(
    hass,
    mock_client,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    mock_devices,
    mock_pets,
):
    await initialize_entry(
        hass, mock_client, mock_config_entry, mock_devices, mock_pets
    )
    await hass.async_block_till_done()

    for entity_id in hass.states.async_entity_ids("button"):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": entity_id},
            blocking=True,
        )
        await hass.async_block_till_done()
        state = hass.states.get(entity_id)
        assert state is not None
        from syrupy.filters import props

        assert state == snapshot(name=f"{entity_id}-press", exclude=props("state"))
