import logging
import pytest
from unittest.mock import patch
from syrupy.assertion import SnapshotAssertion
from surepcio.enums import (
    ProductId,
    PetLocation,
    ModifyDeviceTag,
    PetDeviceLocationProfile,
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import async_get as async_get_device_registry
from custom_components.surepcha.const import DOMAIN

from . import initialize_entry

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
)


def _get_registry_device_ids(device_registry):
    device_id = [
        d.id
        for d in device_registry.devices.values()
        if any(ident[0] == DOMAIN for ident in d.identifiers)
        and getattr(d, "model_id", None) != ProductId.PET
    ][0]
    pet_id = [
        d.id
        for d in device_registry.devices.values()
        if any(ident[0] == DOMAIN for ident in d.identifiers)
        and getattr(d, "model_id", None) == ProductId.PET
    ][0]
    return device_id, pet_id


def _get_surepetcare_id(device_entry) -> str:
    return next(ident[1] for ident in device_entry.identifiers if ident[0] == DOMAIN)


@patch("custom_components.surepcha.PLATFORMS", [Platform.SENSOR])
@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("entity_registry_enabled_default")
@pytest.mark.asyncio
async def test_platform_setup_and_service_call(
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
    surepetcare_logger = logging.getLogger("custom_components.surepcha")
    surepcio_logger = logging.getLogger("surepcio")

    assert surepetcare_logger.getEffectiveLevel() == logging.INFO
    assert surepcio_logger.getEffectiveLevel() == logging.INFO
    await hass.services.async_call(
        DOMAIN,
        "set_debug_logging",
        {"level": "DEBUG"},
        blocking=True,
    )

    assert surepetcare_logger.getEffectiveLevel() == logging.DEBUG
    assert surepcio_logger.getEffectiveLevel() == logging.DEBUG


@patch("custom_components.surepcha.PLATFORMS", [Platform.SENSOR])
@pytest.mark.usefixtures(
    "enable_custom_integrations", "entity_registry_enabled_default"
)
@pytest.mark.asyncio
async def test_platform_setup_and_set_tag_service(
    hass,
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
    device_registry = async_get_device_registry(hass)
    device_id, pet_id = _get_registry_device_ids(device_registry)
    pet_entry = device_registry.async_get(pet_id)
    assert pet_entry is not None
    pet_surepetcare_id = _get_surepetcare_id(pet_entry)

    mock_client.api.reset_mock()
    # Call add action
    await hass.services.async_call(
        DOMAIN,
        "set_tag",
        {
            "device_id": device_id,
            "pet_id": pet_id,
            "action": ModifyDeviceTag.REMOVE.name,
        },
        blocking=True,
    )
    remove_command = mock_client.api.await_args_list[0].args[0]
    assert remove_command.device is not None
    assert str(remove_command.device.id) == pet_surepetcare_id

    # Call remove action
    await hass.services.async_call(
        DOMAIN,
        "set_tag",
        {"device_id": device_id, "pet_id": pet_id, "action": ModifyDeviceTag.ADD.name},
        blocking=True,
    )
    add_command = mock_client.api.await_args_list[1].args[0]
    assert add_command.device is not None
    assert str(add_command.device.id) == pet_surepetcare_id


@patch("custom_components.surepcha.PLATFORMS", [Platform.SENSOR])
@pytest.mark.usefixtures(
    "enable_custom_integrations", "entity_registry_enabled_default"
)
@pytest.mark.asyncio
async def test_platform_setup_and_set_pet_access_mode_service(
    hass,
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
    device_registry = async_get_device_registry(hass)
    device_id, pet_id = _get_registry_device_ids(device_registry)
    await hass.services.async_call(
        DOMAIN,
        "set_pet_access_mode",
        {
            "device_id": device_id,
            "pet_id": pet_id,
            "profile": PetDeviceLocationProfile.INDOOR_ONLY.name,
        },
        blocking=True,
    )


@patch("custom_components.surepcha.PLATFORMS", [Platform.SENSOR])
@pytest.mark.usefixtures(
    "enable_custom_integrations", "entity_registry_enabled_default"
)
@pytest.mark.asyncio
async def test_platform_setup_and_set_pet_position_service(
    hass,
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
    device_registry = async_get_device_registry(hass)
    _, pet_id = _get_registry_device_ids(device_registry)
    pet_entry = device_registry.async_get(pet_id)
    assert pet_entry is not None
    pet_surepetcare_id = _get_surepetcare_id(pet_entry)

    mock_client.api.reset_mock()
    await hass.services.async_call(
        DOMAIN,
        "set_pet_position",
        {
            "pet_id": pet_id,
            "action": PetLocation.INSIDE.name,
        },
        blocking=True,
    )
    command = mock_client.api.await_args_list[0].args[0]
    assert command.device is not None
    assert str(command.device.id) == pet_surepetcare_id
