"""Diagnostics support for SurePetCare integration."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from homeassistant.helpers import device_registry as dr

from .const import DOMAIN


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

    data = integration_data["coordinator"]["coordinator_dict"][device_id].data

    raw_data = getattr(data, "raw_data", {})

    return {"details": raw_data}
