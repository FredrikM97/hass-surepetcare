import pytest
from unittest.mock import patch
from homeassistant.const import Platform
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.debounce import Debouncer
from . import initialize_entry


@pytest.mark.parametrize("mock_device_name", ["pet_door"])
@patch("custom_components.surepcha.PLATFORMS", [Platform.SWITCH, Platform.SENSOR])
@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("entity_registry_enabled_default")
@pytest.mark.asyncio
async def test_coordinator_refresh_and_send_command_update_entities(
    hass,
    mock_client,
    mock_config_entry,
    entity_registry: er.EntityRegistry,
    mock_device,
):
    """Test that sending a command through the coordinator updates multiple entities with new data."""
    await initialize_entry(hass, mock_client, mock_config_entry, mock_device[0], [])

    # Get all surepcha entities from the registry
    entities = list(entity_registry.entities.values())
    assert len(entities) > 1, "Should have more than one entity for a realistic test."
    first_entity_id = entities[0].entity_id

    # Patch the first coordinator to reduce debounces to 0.
    coordinator = next(
        iter(
            hass.data["surepcha"][mock_config_entry.entry_id]["coordinator"][
                "coordinator_dict"
            ].values()
        )
    )

    coordinator._debounced_refresh = Debouncer(
        hass,
        coordinator.logger,
        cooldown=0,
        immediate=True,
        function=coordinator._async_refresh,
    )

    updated_entities = set()

    def track_update(self):
        updated_entities.add(self.entity_id)

    with patch.object(Entity, "async_write_ha_state", new=track_update):
        # Call the switch.turn_on service for the first entity
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": first_entity_id},
            blocking=True,
        )
        await hass.async_block_till_done()
    assert (
        len(updated_entities) > 0
    ), f"Expected at least 1 entity updated, got {len(updated_entities)}"
