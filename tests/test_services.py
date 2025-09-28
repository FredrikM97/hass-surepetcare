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
from custom_components.surepetcare.const import DOMAIN

from . import initialize_entry

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
)


@patch("custom_components.surepetcare.PLATFORMS", [Platform.SENSOR])
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
    surepetcare_logger = logging.getLogger("custom_components.surepetcare")
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


@patch("custom_components.surepetcare.PLATFORMS", [Platform.SENSOR])
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
    # Call remove action
    await hass.services.async_call(
        DOMAIN,
        "set_tag",
        {"device_id": device_id, "pet_id": pet_id, "action": ModifyDeviceTag.ADD.name},
        blocking=True,
    )


@patch("custom_components.surepetcare.PLATFORMS", [Platform.SENSOR])
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


@patch("custom_components.surepetcare.PLATFORMS", [Platform.SENSOR])
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
    pet_id = [
        d.id
        for d in device_registry.devices.values()
        if any(ident[0] == DOMAIN for ident in d.identifiers)
        and getattr(d, "model_id", None) == ProductId.PET
    ][0]
    await hass.services.async_call(
        DOMAIN,
        "set_pet_position",
        {
            "pet_id": pet_id,
            "action": PetLocation.INSIDE.name,
        },
        blocking=True,
    )
