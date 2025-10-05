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


@patch("custom_components.surepcha.PLATFORMS", [Platform.NUMBER])
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
) -> None:
    await initialize_entry(
        hass, mock_client, mock_config_entry_missing_entities, mock_devices, mock_pets
    )
    await snapshot_platform(
        hass, entity_registry, snapshot, mock_config_entry_missing_entities.entry_id
    )


@patch("custom_components.surepcha.PLATFORMS", [Platform.NUMBER])
@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("entity_registry_enabled_default")
@pytest.mark.asyncio
async def test_number_set_and_snapshot(
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

    for entity_id in hass.states.async_entity_ids("number"):
        state = hass.states.get(entity_id)
        if not state:
            continue
        # Try setting to min, max, and mid value if possible
        min_value = state.attributes.get("min")
        max_value = state.attributes.get("max")
        values = []
        if min_value is not None and max_value is not None:
            try:
                min_value = float(min_value)
                max_value = float(max_value)
                mid_value = (min_value + max_value) / 2
                values = [min_value, mid_value, max_value]
            except Exception:
                values = [state.state]
        else:
            values = [state.state]

        for value in values:
            await hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": entity_id, "value": value},
                blocking=True,
            )
            await hass.async_block_till_done()
            updated_state = hass.states.get(entity_id)
            assert updated_state is not None
            snapshot.assert_match(updated_state)
