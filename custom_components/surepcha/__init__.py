"""TODO."""

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType
from surepcio import Household, SurePetcareClient

from .config_flow import SurePetCareConfigFlow
from .const import (
    CLIENT_DEVICE_ID,
    DOMAIN,
    HOUSEHOLD_ID,
    MANUAL_PROPERTIES,
    OPTION_DEVICES,
    OPTION_PROPERTIES,
    TOKEN,
)
from .coordinator import (
    SurePetcareConfigEntry,
    SurePetCareDeviceDataUpdateCoordinator,
    SurePetCareHouseholdTimelineCoordinator,
    SurePetCareRuntimeData,
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
        new_unique_id = config_entry.unique_id
        if HOUSEHOLD_ID not in new_data:
            # Entries stuck on minor_version 4 from a prior release that bumped
            # the version without ever performing the split are re-migrated here too.
            new_unique_id = await _migrate_household_split(
                hass, config_entry, new_data, new_options
            )
        hass.config_entries.async_update_entry(
            config_entry,
            data=new_data,
            options=new_options,
            unique_id=new_unique_id,
            minor_version=5,
            version=1,
        )

    logger.debug(
        "Migration to configuration version %s.%s successful",
        config_entry.version,
        config_entry.minor_version,
    )
    return True


async def _migrate_household_split(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    new_data: dict[str, Any],
    new_options: dict[str, Any],
) -> str | None:
    """Split a legacy multi-household entry into per-household entries.

    Mutates new_data/new_options in place with the first household's info and
    schedules discovery flows for any remaining households. Returns the unique_id
    to assign to this entry (unchanged if the split could not be performed).
    """
    client = SurePetcareClient()
    flow = SurePetCareConfigFlow()
    flow.hass = hass
    try:
        await client.login(
            token=new_data.get(TOKEN), device_id=new_data.get(CLIENT_DEVICE_ID)
        )
        household_data = await flow._fetch_all_household_data(client)
    except Exception:
        logger.warning(
            "Could not split households for entry %s during migration; "
            "it will keep loading all households until a manual reconfigure",
            config_entry.entry_id,
            exc_info=True,
        )
        return config_entry.unique_id
    finally:
        await client.close()

    if not household_data:
        return config_entry.unique_id

    (first_household, first_entity_info), *remaining = household_data
    flow._trigger_discovery_flows(
        new_data[TOKEN], new_data[CLIENT_DEVICE_ID], remaining
    )
    new_data[HOUSEHOLD_ID] = first_household.id
    new_options[OPTION_DEVICES] = first_entity_info
    return str(first_household.id)


async def setup_devices(
    hass, entry
) -> tuple[SurePetcareClient, list[Any], list[Household]]:
    """Setup devices for a config entry."""
    client: SurePetcareClient = SurePetcareClient()
    try:
        await client.login(
            token=entry.data.get(TOKEN), device_id=entry.data.get(CLIENT_DEVICE_ID)
        )
    except Exception as exc:
        raise ConfigEntryAuthFailed from exc

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
        household_id = entry.data.get(HOUSEHOLD_ID)
        if household_id:
            all_households: list[Household] = await client.api(
                Household.get_households()
            )
            households = [h for h in all_households if h.id == household_id]
        else:
            # Legacy entries pre-dating per-household splits have no HOUSEHOLD_ID;
            # load all households so the entry keeps working until the user reconfigures.
            households = await client.api(Household.get_households())
        entities = []
        for household in households:
            entities.extend(await client.api(household.get_pets()))
            entities.extend(await client.api(household.get_devices()))

            # Bind pet device assignments
            await client.api(household.fetch_pet_device_assignments())
        await client.close()
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
    # Not sure if needed so disable for now
    # remove_stale_devices(hass, entry, entities)

    coordinators: list[SurePetCareDeviceDataUpdateCoordinator] = [
        SurePetCareDeviceDataUpdateCoordinator(hass, entry, client, device)
        for device in entities
    ]

    timeline_coordinators = [
        SurePetCareHouseholdTimelineCoordinator(hass, entry, client, household)
        for household in households
    ]

    await asyncio.gather(
        *[
            coordinator.async_config_entry_first_refresh()
            for coordinator in coordinators
        ]
    )

    # Timeline coordinators are supplementary (bus events only, no entities
    # depend on them), so a failure here must not raise ConfigEntryNotReady
    # and trigger the whole entry's fast setup-retry loop; it keeps retrying
    # on its own update_interval like any other failed coordinator refresh.
    for coordinator in timeline_coordinators:
        entry.async_on_unload(coordinator.async_add_listener(lambda: None))
        try:
            await coordinator.async_config_entry_first_refresh()
        except ConfigEntryNotReady:
            logger.warning(
                "Initial timeline refresh failed for household %s; "
                "will keep retrying in the background",
                coordinator.household.id,
            )

    device_registry = dr.async_get(hass)
    for c in coordinators:
        device = c._device
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"{device.id}")},
            manufacturer="SurePetCare",
            model=device.product_name,
            model_id=str(device.product_id),
            name=device.name,
        )

    entry.runtime_data = SurePetCareRuntimeData(
        device_coordinators=coordinators, timeline_coordinators=timeline_coordinators
    )
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


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register integration services before config entries load."""
    for name, func, schema in _service_registry:
        hass.services.async_register(DOMAIN, name, func, schema=schema)
    return True
