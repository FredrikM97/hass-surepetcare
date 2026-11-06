"""Set up SurePetCare config entries and integration services."""

import logging
from collections.abc import Iterable
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType
from surepcio import Household, SurePetcareClient
from surepcio.devices.device import SurePetCareBase
from surepcio.security.exceptions import AuthenticationError

from .const import (
    CLIENT_DEVICE_ID,
    DOMAIN,
    HOUSEHOLD_ID,
    OPTION_DEVICES,
    OPTION_TIMELINE,
    POLLING_SPEED,
    SCAN_INTERVAL,
    TIMELINE_POLLING_SPEED,
    TOKEN,
)
from .coordinator import (
    SurePetcareConfigEntry,
    SurePetCareCoordinator,
    SurePetCareRuntimeData,
)
from .helper import translate_auth_errors
from .migration import (
    migrate_household_split,
    migrate_legacy_manual_properties,
)
from .services import _service_registry

logger = logging.getLogger(__name__)

# This integration is only configurable through config entries, not YAML.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

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
        new_title = config_entry.title
        new_unique_id = config_entry.unique_id
        if config_entry.minor_version < 3:
            migrate_legacy_manual_properties(new_options)
        if config_entry.minor_version < 5:
            # Bumped to force re-migration of entries stuck on a prior version.
            new_title, new_unique_id = await migrate_household_split(
                hass, config_entry, new_data, new_options
            )
        if config_entry.minor_version < 6:
            # Preserve the existing timeline cadence; device overrides no longer
            # apply when all endpoints share one household refresh.
            new_options[OPTION_DEVICES] = {
                key: {
                    name: value
                    for name, value in metadata.items()
                    if name != POLLING_SPEED
                }
                for key, metadata in new_options.get(OPTION_DEVICES, {}).items()
            }
        hass.config_entries.async_update_entry(
            config_entry,
            data=new_data,
            options=new_options,
            title=new_title,
            unique_id=new_unique_id,
            minor_version=6,
            version=1,
        )

    logger.debug(
        "Migration to configuration version %s.%s successful",
        config_entry.version,
        config_entry.minor_version,
    )
    return True


async def setup_devices(
    hass, entry
) -> tuple[SurePetcareClient, list[Any], list[Household]]:
    """Setup devices for a config entry."""
    client: SurePetcareClient = SurePetcareClient()
    try:
        with translate_auth_errors("Sure Petcare authentication failed"):
            logged_in = await client.login(
                token=entry.data.get(TOKEN), device_id=entry.data.get(CLIENT_DEVICE_ID)
            )
            if not logged_in:
                raise AuthenticationError("Sure Petcare login failed")
    except ConfigEntryAuthFailed:
        await client.close()
        raise
    except Exception as exc:
        await client.close()
        raise ConfigEntryNotReady("Unable to connect to Sure Petcare") from exc

    async def close_client(event: Event | None = None) -> None:
        """Close the client - on hass-stop, and again on entry unload/reload."""
        await client.close()

    # Both listeners are needed: hass-stop doesn't unload entries, and
    # unload/reload doesn't fire on a full hass stop.
    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, close_client)
    )
    entry.async_on_unload(close_client)
    # Fetch initial devices
    try:
        with translate_auth_errors():
            household_id = entry.data.get(HOUSEHOLD_ID)
            all_households: list[Household] = await client.api(
                Household.get_households()
            )
            households = (
                [
                    household
                    for household in all_households
                    if household.id == household_id
                ]
                if household_id
                else all_households
            )
            entities = []
            for household in households:
                entities.extend(await client.api(household.get_pets()))
                entities.extend(await client.api(household.get_devices()))
                await client.api(household.fetch_pet_device_assignments())
        await client.close()
    except ConfigEntryAuthFailed:
        await client.close()
        raise
    except Exception as exc:
        await client.close()
        raise ConfigEntryNotReady("Configuration not finished") from exc
    return client, entities, households


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SurePetcareConfigEntry,
) -> bool:
    """Set up surepetcare from a config entry."""
    logger.info("async_setup_entry called for entry_id=%s", entry.entry_id)

    client, entities, households = await setup_devices(hass, entry)
    if len(households) != 1:
        await client.close()
        raise ConfigEntryNotReady("Expected one household per configuration entry")
    coordinator = SurePetCareCoordinator(hass, entry, client, households[0], entities)
    device_registry = dr.async_get(hass)
    remove_stale_devices(device_registry, entry, entities)
    for device in entities:
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"{device.id}")},
            manufacturer="SurePetCare",
            model=device.product_name,
            model_id=str(device.product_id),
            name=device.name,
        )

    entry.runtime_data = SurePetCareRuntimeData(coordinator)
    setup_complete = False
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        coordinator.update_interval = timedelta(
            seconds=entry.options.get(OPTION_TIMELINE, {}).get(
                TIMELINE_POLLING_SPEED, SCAN_INTERVAL
            )
        )
        await coordinator.async_config_entry_first_refresh()
        setup_complete = True
    finally:
        if not setup_complete:
            try:
                await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
            finally:
                await client.close()
    entry.async_on_unload(coordinator.async_add_listener(lambda: None))

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: SurePetcareConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register integration services before config entries load."""
    for name, func, schema in _service_registry:
        hass.services.async_register(DOMAIN, name, func, schema=schema)
    return True


@callback
def remove_stale_devices(
    device_registry: dr.DeviceRegistry,
    entry: SurePetcareConfigEntry,
    devices: Iterable[SurePetCareBase],
) -> None:
    """Remove entry-owned devices absent from a complete household inventory."""
    current_identifiers = {(DOMAIN, str(device.id)) for device in devices}
    for registered in dr.async_entries_for_config_entry(
        device_registry, entry.entry_id
    ):
        identifiers = {
            identifier
            for identifier in registered.identifiers
            if identifier[0] == DOMAIN
        }
        if identifiers and not identifiers.intersection(current_identifiers):
            logger.info(
                "Removing device %s no longer present in config entry %s",
                registered.id,
                entry.entry_id,
            )
            device_registry.async_remove_device(registered.id)
