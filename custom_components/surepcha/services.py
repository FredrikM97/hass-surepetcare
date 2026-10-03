import logging
from collections.abc import Callable, Coroutine
from typing import Any

import voluptuous as vol
from homeassistant.helpers import device_registry as dr
from surepcio.devices import Pet
from surepcio.enums import ModifyDeviceTag, PetDeviceLocationProfile, PetLocation

from .const import DOMAIN
from .coordinator import (
    SurePetCareDeviceDataUpdateCoordinator,
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
    coordinator = get_coordinator(call.hass, call.data.get("device_id"))
    await coordinator.client.api(
        coordinator._device.set_control(**call.data.get("control"))
    )


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
    device_coordinator = get_coordinator(call.hass, call.data.get("device_id"))
    pet_coordinator = get_coordinator(call.hass, call.data.get("pet_id"))
    await device_coordinator.client.api(
        device_coordinator._device.set_tag(
            pet_coordinator._device.tag, ModifyDeviceTag[call.data.get("action")]
        )
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
    device_coordinator = get_coordinator(call.hass, call.data.get("device_id"))
    pet_coordinator = get_coordinator(call.hass, call.data.get("pet_id"))
    await pet_coordinator.client.api(
        pet_coordinator._device.set_profile(
            device_coordinator._device.id,
            PetDeviceLocationProfile[call.data.get("profile")],
        )
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
    pet_coordinator = get_coordinator(call.hass, call.data.get("pet_id"))
    device: Pet = pet_coordinator._device
    await pet_coordinator.client.api(
        device.set_position(PetLocation[call.data.get("action")])
    )


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
    device_coordinator = get_coordinator(call.hass, call.data.get("device_id"))
    await device_coordinator.async_refresh()


def get_coordinator(hass, device_id) -> SurePetCareDeviceDataUpdateCoordinator:
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
        for coordinator in runtime_data.device_coordinators if runtime_data else []:
            if (DOMAIN, str(coordinator._device.id)) in device_identifiers:
                return coordinator

    raise ValueError(f"No coordinator found for device_id {device_id}")
