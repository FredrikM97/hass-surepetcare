"""Diagnostics support for SurePetCare integration."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from homeassistant.helpers import device_registry as dr

from custom_components.surepcha.helper import serialize

from .const import COORDINATOR, COORDINATOR_DICT, DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    return {
        "entry_data": dict(entry.data),
        "options": dict(entry.options),
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: dr.DeviceEntry
) -> dict[str, Any]:
    """Return diagnostics for a device."""
    device_id = list(device.identifiers)[0][1]
    integration_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not integration_data:
        return {}

    device = integration_data[COORDINATOR][COORDINATOR_DICT][device_id].data

    return {"options": dict(entry.options), "device": serialize(device)}
