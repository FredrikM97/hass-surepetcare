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


@patch("custom_components.surepetcare.PLATFORMS", [Platform.LOCK])
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


@patch("custom_components.surepetcare.PLATFORMS", [Platform.LOCK])
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

@patch("custom_components.surepetcare.PLATFORMS", [Platform.LOCK])
@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("entity_registry_enabled_default")
@pytest.mark.asyncio
async def test_lock_toggle_and_snapshot(
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

    for entity_id in hass.states.async_entity_ids("lock"):
        # Lock
        await hass.services.async_call(
            "lock",
            "lock",
            {"entity_id": entity_id},
            blocking=True,
        )
        await hass.async_block_till_done()
        state_locked = hass.states.get(entity_id)
        assert state_locked is not None
        snapshot(name=f"{entity_id}-locked").assert_match(state_locked)

        # Unlock
        await hass.services.async_call(
            "lock",
            "unlock",
            {"entity_id": entity_id},
            blocking=True,
        )
        await hass.async_block_till_done()
        state_unlocked = hass.states.get(entity_id)
        assert state_unlocked is not None
        snapshot(name=f"{entity_id}-unlocked").assert_match(state_unlocked)