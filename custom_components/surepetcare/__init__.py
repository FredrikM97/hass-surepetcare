"""TODO."""

import logging
from typing import Any, List

from surepetcare.client import SurePetcareClient
from surepetcare.household import Household
from surepetcare.enums import ProductId

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .const import (
    CLIENT_DEVICE_ID,
    COORDINATOR,
    COORDINATOR_DICT,
    DOMAIN,
    FACTORY,
    KEY_API,
    TOKEN,
)
from .coordinator import SurePetCareDeviceDataUpdateCoordinator

logger = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """TODO."""
    logger.info("async_setup_entry called for entry_id=%s", entry.entry_id)

    surepetcare_data: dict[str, Any] = {}
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = surepetcare_data

    client: SurePetcareClient = SurePetcareClient()
    # Try login with token+device_id, else fallback to email+password
    token = entry.data.get(TOKEN)
    device_id = entry.data.get(CLIENT_DEVICE_ID)
    email = entry.data.get("email")
    password = entry.data.get("password")
    if token and device_id:
        await client.login(token=token, device_id=device_id)
    elif email and password:
        await client.login(email=email, password=password)
    else:
        raise Exception("No valid credentials found in config entry data")
    surepetcare_data[FACTORY] = client

    async def on_hass_stop(event: Event) -> None:
        """Close connection when hass stops."""
        await client.close()

    # Setup listeners
    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, on_hass_stop)
    )
    try:
        households: List[Household] = await client.api(Household.get_households())
        entities = []
        for household in households:
            entities.extend(await client.api(household.get_pets()))
            entities.extend(await client.api(household.get_devices()))
            # Add each hub device to hubs list
        await client.close()
    except Exception as exc:
        await client.close()
        raise Exception("Configuration not finished") from exc

    remove_stale_devices(hass, entry, entities)
    # Setup the device coordinators
    coordinator_data = {
        KEY_API: client,
        COORDINATOR_DICT: {},
    }

    for device in entities:
        if device.product != ProductId.HUB:
            continue
        entities.remove(device)
        device_id = str(device.id)
        if device_id not in coordinator_data[COORDINATOR_DICT]:
            coordinator = SurePetCareDeviceDataUpdateCoordinator(
                hass=hass,
                config_entry=entry,
                client=client,
                device=device,
            )
            await coordinator.async_config_entry_first_refresh()

            coordinator_data[COORDINATOR_DICT][device_id] = coordinator
        else:
            logger.warning("Coordinator already exists for device %s", device_id)

    for device in entities:
        device_id = str(device.id)
        if device_id not in coordinator_data[COORDINATOR_DICT]:
            coordinator = SurePetCareDeviceDataUpdateCoordinator(
                hass=hass,
                config_entry=entry,
                client=client,
                device=device,
            )
            await coordinator.async_config_entry_first_refresh()

            coordinator_data[COORDINATOR_DICT][device_id] = coordinator
        else:
            logger.warning("Coordinator already exists for device %s", device_id)

    surepetcare_data[COORDINATOR] = coordinator_data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        surepetcare_data = hass.data[DOMAIN].pop(entry.entry_id)
        client: SurePetcareClient = surepetcare_data[FACTORY]
        await client.close()

    return unload_ok


@callback
def remove_stale_devices(
    hass: HomeAssistant, config_entry: ConfigEntry, devices: list[Any]
) -> None:
    """Remove stale devices from device registry. TODO: Work in progress and not functional yet"""

    device_registry = dr.async_get(hass)
    device_entries = dr.async_entries_for_config_entry(
        device_registry, config_entry.entry_id
    )
    all_device_ids = {str(device.id) for device in devices}
    for device_entry in device_entries:
        device_id: str | None = None  # Only define here
        # Check that device part of DOMAIN
        for identifier in device_entry.identifiers:
            if identifier[0] != DOMAIN:
                continue

            _id = identifier[1]
            device_id = str(_id)
        if device_id is None or device_id not in all_device_ids:
            logger.info(
                "Removing stale device entry %s for config entry %s",
                device_entry.id,
                config_entry.entry_id,
            )
            device_registry.async_update_device(
                device_entry.id, remove_config_entry_id=config_entry.entry_id
            )
