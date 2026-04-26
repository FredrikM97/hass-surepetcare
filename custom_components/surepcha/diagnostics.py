"""Diagnostics support for SurePetCare integration."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.redact import async_redact_data

from custom_components.surepcha.coordinator import SurePetcareConfigEntry
from custom_components.surepcha.helper import serialize


TO_REDACT = {"token", "client_device_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SurePetcareConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    return async_redact_data(
        {
            "entry_data": dict(entry.data),
            "options": dict(entry.options),
        },
        TO_REDACT,
    )


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: SurePetcareConfigEntry, device: dr.DeviceEntry
) -> dict[str, Any]:
    """Return diagnostics for a device."""
    device_id = list(device.identifiers)[0][1]
    coordinators = getattr(entry, "runtime_data", None)

    if not coordinators:
        return {}

    for coordinator in coordinators or []:
        if str(getattr(coordinator._device, "id", "")) == str(device_id):
            device_obj = coordinator.data
            break

    return async_redact_data(
        {"options": dict(entry.options), "device": serialize(device_obj)}, TO_REDACT
    )
