"""TODO."""

import asyncio
import logging
from types import MappingProxyType
from typing import Any, List

from surepcio import SurePetcareClient
from surepcio import Household

from .services import _service_registry

from homeassistant.exceptions import ConfigEntryAuthFailed

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .const import (
    CLIENT_DEVICE_ID,
    DOMAIN,
    HOUSEHOLD_ID,
    HOUSEHOLD_SUBENTRY_TYPE,
    MANUAL_PROPERTIES,
    TOKEN,
    OPTION_PROPERTIES,
)
from .coordinator import SurePetCareDeviceDataUpdateCoordinator, SurePetcareConfigEntry
from .subentries import subentry_id_for_household

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
                config_entry,
                data=new_data,
                options=new_options,
                minor_version=2,
                version=1,
            )

        if config_entry.minor_version < 4:
            if not await _async_migrate_to_household_subentries(hass, config_entry):
                return False
            hass.config_entries.async_update_entry(config_entry, minor_version=4)

    logger.debug(
        "Migration to configuration version %s.%s successful",
        config_entry.version,
        config_entry.minor_version,
    )
    return True


async def _async_migrate_to_household_subentries(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> bool:
    """Give each household on the account its own subentry.

    Only ever sets a device's config_subentry_id — config_entry_id never
    changes — so existing entity_ids, areas, and history are untouched.
    Returns False (leaving minor_version unbumped, so HA retries next
    startup) if households can't be fetched right now.
    """
    if config_entry.subentries:
        # Already migrated, or a fresh entry created post-refactor.
        return True

    client = SurePetcareClient()
    try:
        await client.login(
            token=config_entry.data.get(TOKEN),
            device_id=config_entry.data.get(CLIENT_DEVICE_ID),
        )
        households: List[Household] = await client.api(Household.get_households())
        households_with_devices = []
        for household in households:
            devices = await client.api(household.get_devices())
            pets = await client.api(household.get_pets())
            device_ids = {device.id for device in [*devices, *pets]}
            if device_ids:
                households_with_devices.append((household, device_ids))
    except Exception:
        logger.warning(
            "Could not fetch households while migrating entry %s to household "
            "subentries; will retry on next startup",
            config_entry.entry_id,
            exc_info=True,
        )
        return False
    finally:
        await client.close()

    device_registry = dr.async_get(hass)
    for household, device_ids in households_with_devices:
        subentry = ConfigSubentry(
            subentry_type=HOUSEHOLD_SUBENTRY_TYPE,
            title=(household.data.get("name") or "").strip()
            or f"Household {household.id}",
            unique_id=str(household.id),
            data=MappingProxyType({HOUSEHOLD_ID: household.id}),
        )
        hass.config_entries.async_add_subentry(config_entry, subentry)
        for device_id in device_ids:
            registry_entry = device_registry.async_get_device(
                identifiers={(DOMAIN, str(device_id))}
            )
            if registry_entry is not None:
                _move_device_to_subentry(
                    device_registry,
                    registry_entry.id,
                    config_entry.entry_id,
                    subentry.subentry_id,
                )

    return True


def _move_device_to_subentry(
    device_registry: dr.DeviceRegistry,
    device_id: str,
    entry_id: str,
    subentry_id: str,
) -> None:
    """Assign a device to its household's subentry, on old- or new-API HA alike."""
    try:
        # HA 2026.8+ exposes this single-call API; not yet in older pins, hence
        # the runtime feature-detection below rather than a version check.
        device_registry.async_update_device(
            device_id,
            new_config_entry_id=entry_id,  # type: ignore[call-arg]
            new_config_subentry_id=subentry_id,  # type: ignore[call-arg]
        )
    except TypeError:
        # The old API only ever adds associations, never replaces them. A
        # device registered before subentries existed is associated with
        # entry_id's "no subentry" bucket (None) - add_config_subentry_id
        # alone would leave it in *both* that bucket and the real subentry.
        #
        # These must be two SEPARATE calls, not combined add_/remove_ kwargs
        # in one call: HA's device registry computes the remove from the
        # pre-call state, discarding whatever the add in the same call just
        # did. For a device with only this one config entry, that computes
        # an empty entry set and deletes the device outright. Sequencing
        # them avoids that entirely - confirmed via a regression test that
        # the device is neither deleted nor left in both buckets.
        device_registry.async_update_device(
            device_id,
            add_config_entry_id=entry_id,
            add_config_subentry_id=subentry_id,
        )
        device_registry.async_update_device(
            device_id,
            remove_config_entry_id=entry_id,
            remove_config_subentry_id=None,
        )


async def setup_devices(hass, entry) -> tuple[SurePetcareClient, list[Any]]:
    """Setup devices for a config entry, scoped to its household subentries."""
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
    # Fetch devices only for households the user has added as a subentry.
    try:
        household_ids = {
            subentry.data[HOUSEHOLD_ID] for subentry in entry.subentries.values()
        }
        households: List[Household] = await client.api(Household.get_households())
        entities = []
        for household in households:
            if household.id not in household_ids:
                continue
            entities.extend(await client.api(household.get_pets()))
            entities.extend(await client.api(household.get_devices()))

            # Bind pet device assignments
            await client.api(household.fetch_pet_device_assignments())
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
        registry_entry = device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"{device.id}")},
            manufacturer="SurePetCare",
            model=device.product_name,
            model_id=str(device.product_id),
            name=device.name,
        )
        subentry_id = subentry_id_for_household(entry, device.household_id)
        if subentry_id is not None:
            _move_device_to_subentry(
                device_registry, registry_entry.id, entry.entry_id, subentry_id
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


async def async_setup(hass: HomeAssistant, config: ConfigEntry) -> bool:
    """Register integration services before config entries load."""
    for name, func, schema in _service_registry:
        hass.services.async_register(DOMAIN, name, func, schema=schema)
    return True
