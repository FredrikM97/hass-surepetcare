import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import async_get as async_get_device_registry
from surepcio.enums import (
    ModifyDeviceTag,
    PetDeviceLocationProfile,
    PetLocation,
    ProductId,
)
from syrupy.assertion import SnapshotAssertion

from custom_components.surepcha.const import DOMAIN
from custom_components.surepcha.services import async_set_control, get_coordinator

from . import initialize_entry
from .support import MockConfigEntry


def test_get_coordinator_unknown_device(hass: HomeAssistant) -> None:
    """Reject a device that is not present in the registry."""
    with (
        patch(
            "custom_components.surepcha.services.dr.async_get_device_and_config_entry_for_domain",
            return_value=(None, None),
        ),
        pytest.raises(ValueError, match="No coordinator found"),
    ):
        get_coordinator(hass, "unknown")


def test_get_coordinator_non_integration_device(hass: HomeAssistant) -> None:
    """Reject a device without a SurePetCare identifier."""
    device_entry = MagicMock(identifiers={("other", "device")})
    config_entry = MagicMock(entry_id="entry")
    with (
        patch(
            "custom_components.surepcha.services.dr.async_get_device_and_config_entry_for_domain",
            return_value=(device_entry, config_entry),
        ),
        pytest.raises(ValueError, match="No coordinator found"),
    ):
        get_coordinator(hass, "device")


def test_get_coordinator_without_matching_coordinator(hass: HomeAssistant) -> None:
    """Reject a registered device with no matching loaded coordinator."""
    device_entry = SimpleNamespace(identifiers={(DOMAIN, "device")})
    config_entry = SimpleNamespace(entry_id="entry")
    coordinator = SimpleNamespace(_device=SimpleNamespace(id="other"))
    unrelated_entry = SimpleNamespace(entry_id="unrelated", runtime_data=None)
    loaded_entry = SimpleNamespace(
        entry_id="entry",
        runtime_data=SimpleNamespace(device_coordinators=[coordinator]),
    )
    with (
        patch(
            "custom_components.surepcha.services.dr.async_get_device_and_config_entry_for_domain",
            return_value=(device_entry, config_entry),
        ),
        patch.object(
            hass.config_entries,
            "async_loaded_entries",
            return_value=[unrelated_entry, loaded_entry],
        ),
        pytest.raises(ValueError, match="No coordinator found"),
    ):
        get_coordinator(hass, "device")


@pytest.mark.asyncio
async def test_set_control_service(hass: HomeAssistant) -> None:
    """Send a control update through the selected device coordinator."""
    coordinator = MagicMock()
    coordinator._device.set_control.return_value = "command"
    coordinator.client.api = AsyncMock()
    call = SimpleNamespace(
        hass=hass,
        data={"device_id": "device", "control": {"curfew": {"enabled": True}}},
    )
    with patch(
        "custom_components.surepcha.services.get_coordinator",
        return_value=coordinator,
    ):
        await async_set_control(call)

    coordinator._device.set_control.assert_called_once_with(curfew={"enabled": True})
    coordinator.client.api.assert_awaited_once_with("command")


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
    device_id = next(
        d.id
        for d in device_registry.devices
        if any(ident[0] == DOMAIN for ident in d.identifiers)
        and getattr(d, "model_id", None) != str(ProductId.PET)
    )
    pet_id = next(
        d.id
        for d in device_registry.devices
        if any(ident[0] == DOMAIN for ident in d.identifiers)
        and getattr(d, "model_id", None) == str(ProductId.PET)
    )
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
    device_id = next(
        d.id
        for d in device_registry.devices
        if any(ident[0] == DOMAIN for ident in d.identifiers)
        and getattr(d, "model_id", None) != str(ProductId.PET)
    )
    pet_id = next(
        d.id
        for d in device_registry.devices
        if any(ident[0] == DOMAIN for ident in d.identifiers)
        and getattr(d, "model_id", None) == str(ProductId.PET)
    )
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
    pet_id = next(
        d.id
        for d in device_registry.devices
        if any(ident[0] == DOMAIN for ident in d.identifiers)
        and getattr(d, "model_id", None) == str(ProductId.PET)
    )
    await hass.services.async_call(
        DOMAIN,
        "set_pet_position",
        {
            "pet_id": pet_id,
            "action": PetLocation.INSIDE.name,
        },
        blocking=True,
    )


@patch("custom_components.surepcha.PLATFORMS", [Platform.SENSOR])
@pytest.mark.usefixtures(
    "enable_custom_integrations", "entity_registry_enabled_default"
)
@pytest.mark.asyncio
async def test_platform_setup_and_refresh_device_service(
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
    pet_id = next(
        d.id
        for d in device_registry.devices
        if any(ident[0] == DOMAIN for ident in d.identifiers)
        and getattr(d, "model_id", None) == str(ProductId.PET)
    )
    await hass.services.async_call(
        DOMAIN,
        "refresh_device",
        {
            "device_id": pet_id,
        },
        blocking=True,
    )
