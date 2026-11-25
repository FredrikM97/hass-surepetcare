from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from surepcio.enums import FlapLocking, ModifyDeviceTag, ProductId, Tare
from syrupy.assertion import SnapshotAssertion

from custom_components.surepcha.const import NAME, PRODUCT_ID
from custom_components.surepcha.entity import FieldOption
from custom_components.surepcha.select import (
    SurePetCareSelectEntityDescription,
    assignment_options,
)

from . import initialize_entry
from .support import MockConfigEntry, snapshot_platform


def test_native_select_options_and_dynamic_api_options_are_distinct(snapshot):
    description = SurePetCareSelectEntityDescription(
        key="choice", options=["First", "Second"]
    )
    dynamic = SurePetCareSelectEntityDescription(
        key="choice",
        options=["Static"],
        options_fn=lambda *_: (FieldOption("write_value", "Dynamic"),),
    )
    assert {
        "static": description.get_options(None),
        "dynamic_metadata": dynamic.options,
        "dynamic": dynamic.get_options(None),
    } == snapshot
    with pytest.raises(FrozenInstanceError):
        description.key = "changed"
    with pytest.raises(TypeError):
        SurePetCareSelectEntityDescription("choice")


def test_assignment_options_read_current_configuration_without_copied_inventory(
    snapshot,
):
    entity = SimpleNamespace(
        hass=object(),
        coordinator=SimpleNamespace(config_entry=object()),
        device=SimpleNamespace(
            status=SimpleNamespace(devices=SimpleNamespace(items=[]))
        ),
    )
    options = {
        "20": {NAME: "Feeder", PRODUCT_ID: ProductId.FEEDER_CONNECT},
        "21": {NAME: "Hub", PRODUCT_ID: ProductId.HUB},
    }
    with patch(
        "custom_components.surepcha.select.get_device_options",
        return_value=options,
    ):
        assert assignment_options(entity, ModifyDeviceTag.ADD) == snapshot(
            name="initial"
        )
        options["20"][NAME] = "Renamed"
        assert assignment_options(entity, ModifyDeviceTag.ADD) == snapshot(
            name="renamed"
        )


def test_select_command_prepares_api_choice_and_rejects_unavailable_choice(snapshot):
    description = SurePetCareSelectEntityDescription(
        key="locking",
        choices=FlapLocking,
        options_fn=lambda *_: (
            FieldOption("locked", "Locked"),
            FieldOption("unlocked", "Unlocked"),
        ),
    )
    entity = SimpleNamespace(device=object())
    assert {
        "normalized": description.normalize_value(FlapLocking.UNLOCKED, entity),
        "prepared": description.prepare_command_value("Locked", entity),
    } == snapshot
    with pytest.raises(ValueError, match="unavailable"):
        description.prepare_command_value("Unknown", entity)


@patch("custom_components.surepcha.PLATFORMS", [Platform.SELECT])
@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("entity_registry_enabled_default")
async def test_tare_select_tracks_reported_value_and_explicit_unknown(
    hass, mock_client, mock_config_entry, entity_registry, mock_devices, mock_pets
):
    await initialize_entry(
        hass, mock_client, mock_config_entry, mock_devices, mock_pets
    )
    coordinator = mock_config_entry.runtime_data.coordinator
    for device in mock_devices:
        if device.product != ProductId.FEEDER_CONNECT:
            continue
        entity_id = entity_registry.async_get_entity_id(
            "select", "surepcha", f"{device.id}-tare"
        )
        assert entity_id is not None
        device.control.tare = Tare.RESET_RIGHT
        coordinator.async_update_listeners()
        assert hass.states.get(entity_id).state == "reset_right"
        device.control.tare = None
        coordinator.async_update_listeners()
        assert hass.states.get(entity_id).state == "unknown"
        device.control.tare = Tare.RESET_LEFT
        coordinator.async_update_listeners()
        assert hass.states.get(entity_id).state == "reset_left"


@patch("custom_components.surepcha.PLATFORMS", [Platform.SELECT])
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


@patch("custom_components.surepcha.PLATFORMS", [Platform.SELECT])
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


@patch("custom_components.surepcha.PLATFORMS", [Platform.SELECT])
@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("entity_registry_enabled_default")
@pytest.mark.asyncio
async def test_select_set_option_and_snapshot(
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

    # Iterate over all select entities
    for entity_id in hass.states.async_entity_ids("select"):
        state = hass.states.get(entity_id)
        if not state:
            continue

        # Try to get the available options from the state attributes
        options = state.attributes.get("options")
        if not options:
            continue

        # Try each option for this select
        for option in options:
            if option is None:
                continue  # Skip None options
            await hass.services.async_call(
                "select",
                "select_option",
                {"entity_id": entity_id, "option": option},
                blocking=True,
            )
            await hass.async_block_till_done()

            # Snapshot the updated state after setting each option
            updated_state = hass.states.get(entity_id)
            assert updated_state is not None
            assert updated_state == snapshot(name=f"{entity_id}-{option}")
