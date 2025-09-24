import pytest
from unittest.mock import patch
from syrupy.assertion import SnapshotAssertion

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import initialize_entry

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    snapshot_platform,
)


@patch("custom_components.surepetcare.PLATFORMS", [Platform.BUTTON])
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


@patch("custom_components.surepetcare.PLATFORMS", [Platform.BUTTON])
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
