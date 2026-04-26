"""TODO."""

import asyncio
import logging
from typing import Any, List

from surepcio import SurePetcareClient
from surepcio import Household

from .services import _service_registry

from homeassistant.exceptions import ConfigEntryAuthFailed

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .const import (
    CLIENT_DEVICE_ID,
    DOMAIN,
    MANUAL_PROPERTIES,
    TOKEN,
    OPTION_PROPERTIES,
)
from .coordinator import SurePetCareDeviceDataUpdateCoordinator, SurePetcareConfigEntry

logger = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.BUTTON,
    Platform.LOCK,
    Platform.SWITCH,
]


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old config entry to ensure all required properties are present."""
    logger.debug(
        "Migrating configuration from version %s.%s",
        config_entry.version,
        config_entry.minor_version,
    )

    if config_entry.version > 1:
        # User downgraded from a future version
        return False

    if config_entry.version == 1:
        new_data = {**config_entry.data}
        new_options = {**config_entry.options}
        if config_entry.minor_version < 3:
            # Move legacy manual properties to the dedicated properties section.
            legacy_manual = new_options.pop(MANUAL_PROPERTIES, {})
            new_options.update(
                {
                    OPTION_PROPERTIES: (
                        {MANUAL_PROPERTIES: legacy_manual} if legacy_manual else {}
                    )
                }
            )
        hass.config_entries.async_update_entry(
            config_entry, data=new_data, options=new_options, minor_version=2, version=1
        )

    logger.debug(
        "Migration to configuration version %s.%s successful",
        config_entry.version,
        config_entry.minor_version,
    )
    return True


async def setup_devices(hass, entry) -> tuple[SurePetcareClient, list[Any]]:
    """Setup devices for a config entry."""
    client: SurePetcareClient = SurePetcareClient()
    try:
        await client.login(
            token=entry.data.get(TOKEN), device_id=entry.data.get(CLIENT_DEVICE_ID)
        )
    except Exception as exc:
        raise ConfigEntryAuthFailed from exc

    async def on_hass_stop(event: Event) -> None:
        """Close connection when hass stops."""
        await client.close()

    # Setup listeners
    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, on_hass_stop)
    )
    # Fetch initial devices
    try:
        households: List[Household] = await client.api(Household.get_households())
        entities = []
        for household in households:
            entities.extend(await client.api(household.get_pets()))
            entities.extend(await client.api(household.get_devices()))
        await client.close()
    except Exception as exc:
        await client.close()
        raise Exception("Configuration not finished") from exc
    return client, entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SurePetcareConfigEntry,
) -> bool:
    """Set up surepetcare from a config entry."""
    logger.info("async_setup_entry called for entry_id=%s", entry.entry_id)

    client, entities = await setup_devices(hass, entry)
    # Not sure if needed so disable for now
    # remove_stale_devices(hass, entry, entities)

    coordinators: list[SurePetCareDeviceDataUpdateCoordinator] = [
        SurePetCareDeviceDataUpdateCoordinator(hass, entry, client, device)
        for device in entities
    ]

    await asyncio.gather(
        *[
            coordinator.async_config_entry_first_refresh()
            for coordinator in coordinators
        ]
    )

    device_registry = dr.async_get(hass)
    for c in coordinators:
        device = c._device
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"{device.id}")},
            manufacturer="SurePetCare",
            model=device.product_name,
            model_id=device.product_id,
            name=device.name,
        )

    entry.runtime_data = coordinators
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: SurePetcareConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


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


async def async_setup(hass: HomeAssistant, config: ConfigEntry):
    for name, func, schema in _service_registry:
        hass.services.async_register(DOMAIN, name, func, schema=schema)
    return True
