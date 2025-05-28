"""TODO."""

from custom_components.surepetcare.coordinator import SurePetcareCoordinator
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from config.custom_components.surepetcare.const import DOMAIN

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SurePetCare from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    coordinator = SurePetcareCoordinator(hass, entry.data)
    hass.data[DOMAIN]["coordinator"] = coordinator
    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass, entry):
    """Unload SurePetCare config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    coordinator = hass.data[DOMAIN]["coordinator"]
    await coordinator.client.close()
    hass.data[DOMAIN].pop("coordinator", None)
    return unload_ok
