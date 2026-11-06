import logging
from collections.abc import Callable, Coroutine
from typing import Any

import voluptuous as vol
from homeassistant.helpers import device_registry as dr
from surepcio.devices.device import DeviceBase, SurePetCareBase
from surepcio.devices.pet import Pet
from surepcio.enums import ModifyDeviceTag, PetDeviceLocationProfile, PetLocation

from .const import DOMAIN
from .coordinator import (
    SurePetCareCoordinator,
)

logger = logging.getLogger(__name__)

_service_registry: list[
    tuple[str, Callable[..., Coroutine[Any, Any, None]], vol.Schema | None]
] = []


def global_service(name, schema=None):
    """Decorator to register a global service for the integration."""

    def decorator(func):
        _service_registry.append((name, func, schema))
        return func

    return decorator


# Import for entity-specific service registration


@global_service(
    "set_debug_logging",
    schema=vol.Schema(
        {
            vol.Required("level"): vol.In(
                ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            )
        }
    ),
)
async def async_set_debug_logging(call):
    """Set debug logging level for surepetcare integration and library."""
    level = getattr(logging, call.data["level"], logging.INFO)
    logging.getLogger("custom_components.surepcha").setLevel(level)
    logging.getLogger("surepcio").setLevel(level)


@global_service(
    "set_control",
    schema=vol.Schema(
        {
            vol.Required("device_id"): str,
            vol.Optional("control"): dict,
        }
    ),
)
async def async_set_control(call):
    coordinator, device = get_coordinator(call.hass, call.data.get("device_id"))
    if not isinstance(device, DeviceBase):
        raise TypeError("Control settings require a device, not a pet")
    await coordinator.client.api(device.set_control(**call.data.get("control", {})))


@global_service(
    "set_tag",
    schema=vol.Schema(
        {
            vol.Required("device_id"): str,
            vol.Required("pet_id"): str,
            vol.Required("action"): vol.In([e.name for e in ModifyDeviceTag]),
        }
    ),
)
async def async_set_tag(call):
    device_coordinator, device = get_coordinator(call.hass, call.data.get("device_id"))
    _, pet = get_coordinator(call.hass, call.data.get("pet_id"))
    if not isinstance(device, DeviceBase) or not isinstance(pet, Pet):
        raise TypeError("Tag assignment requires a device and a pet")
    pet_tag = pet.tag
    if pet_tag is None or pet_tag <= 0:
        raise ValueError(f"Pet {pet.id} has no valid tag")
    await device_coordinator.client.api(
        device.set_tag(pet_tag, ModifyDeviceTag[call.data["action"]])
    )


@global_service(
    "set_pet_access_mode",
    schema=vol.Schema(
        {
            vol.Required("device_id"): str,
            vol.Required("pet_id"): str,
            vol.Required("profile"): vol.In([e.name for e in PetDeviceLocationProfile]),
        }
    ),
)
async def set_pet_access_mode(call) -> None:
    """Set pet access mode to indoor or outdoor"""
    _, device = get_coordinator(call.hass, call.data.get("device_id"))
    pet_coordinator, pet = get_coordinator(call.hass, call.data.get("pet_id"))
    if not isinstance(pet, Pet):
        raise TypeError("Access profiles require a pet")
    await pet_coordinator.client.api(
        pet.set_profile(device.id, PetDeviceLocationProfile[call.data["profile"]])
    )


@global_service(
    "set_pet_position",
    schema=vol.Schema(
        {
            vol.Required("pet_id"): str,
            vol.Required("action"): vol.In([e.name for e in PetLocation]),
        }
    ),
)
async def set_pet_position(call) -> None:
    """Set pet position to inside or outside"""
    pet_coordinator, pet = get_coordinator(call.hass, call.data.get("pet_id"))
    if not isinstance(pet, Pet):
        raise TypeError("Position updates require a pet")
    await pet_coordinator.client.api(pet.set_position(PetLocation[call.data["action"]]))


@global_service(
    "refresh_device",
    schema=vol.Schema(
        {
            vol.Required("device_id"): str,
        }
    ),
)
async def refresh_device(call) -> None:
    """Refresh a pet or device"""
    device_coordinator, device = get_coordinator(call.hass, call.data.get("device_id"))
    await device_coordinator.async_refresh_device(device)


def get_coordinator(hass, device_id) -> tuple[SurePetCareCoordinator, SurePetCareBase]:
    device_entry, config_entry = dr.async_get_device_and_config_entry_for_domain(
        hass, device_id, domain=DOMAIN
    )
    if device_entry is None or config_entry is None:
        raise ValueError(f"No coordinator found for device_id {device_id}")

    device_identifiers = {
        identifier for identifier in device_entry.identifiers if identifier[0] == DOMAIN
    }
    if not device_identifiers:
        raise ValueError(f"No coordinator found for device_id {device_id}")

    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        if entry.entry_id != config_entry.entry_id:
            continue
        runtime_data = getattr(entry, "runtime_data", None)
        if runtime_data:
            coordinator = runtime_data.coordinator
            for device in coordinator.devices.values():
                if (DOMAIN, str(device.id)) in device_identifiers:
                    return coordinator, device

    raise ValueError(f"No coordinator found for device_id {device_id}")
