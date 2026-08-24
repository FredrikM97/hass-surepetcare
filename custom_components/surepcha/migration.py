"""Config-entry migration: legacy option reshaping and the household split."""

import logging
from typing import Any

from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY, ConfigEntry
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from surepcio import Household, SurePetcareClient

from .config_flow import SurePetCareConfigFlow
from .const import (
    CLIENT_DEVICE_ID,
    DOMAIN,
    HOUSEHOLD_ID,
    MANUAL_PROPERTIES,
    NAME,
    OPTION_DEVICES,
    OPTION_PROPERTIES,
    TOKEN,
)

logger = logging.getLogger(__name__)


def migrate_legacy_manual_properties(new_options: dict[str, Any]) -> None:
    """Move top-level legacy manual_properties into the dedicated properties section."""
    legacy_manual = new_options.pop(MANUAL_PROPERTIES, {})
    new_options[OPTION_PROPERTIES] = (
        {MANUAL_PROPERTIES: legacy_manual} if legacy_manual else {}
    )


async def create_sibling_entries(
    hass: HomeAssistant,
    token: str,
    device_id: str,
    households: list[tuple[Household, dict]],
) -> bool:
    """Create discovery-flow entries for the given households.

    Idempotent: the discovery step aborts on its own once a household is
    already configured, so calling this again for the same households is
    safe. Returns False if a create failed, so the caller can retry later.
    """
    for household, entity_info in households:
        try:
            await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_INTEGRATION_DISCOVERY},
                data={
                    CONF_TOKEN: token,
                    CLIENT_DEVICE_ID: device_id,
                    HOUSEHOLD_ID: household.id,
                    NAME: household.data.get("name"),
                    OPTION_DEVICES: entity_info,
                },
            )
        except Exception:
            logger.warning(
                "Could not create a separate entry for household %s; the whole "
                "household split will be retried",
                household.id,
                exc_info=True,
            )
            return False
    return True


async def _fetch_unconfigured_households(
    hass: HomeAssistant, token: str | None, device_id: str | None
) -> list[tuple[Household, dict]] | None:
    """Fetch households not yet claimed by another config entry.

    Returns None if there's nothing to do: the fetch failed, or every
    household is already represented by an entry.
    """
    client = SurePetcareClient()
    flow = SurePetCareConfigFlow()
    flow.hass = hass
    try:
        await client.login(token=token, device_id=device_id)
        household_data = await flow._fetch_all_household_data(client)
    except Exception:
        logger.warning(
            "Could not fetch households for the household split; it will "
            "be retried on the next setup",
            exc_info=True,
        )
        return None
    finally:
        await client.close()

    if not household_data:
        return None

    unconfigured, _ = flow._split_by_configured(household_data)
    return unconfigured or None


async def migrate_household_split(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    new_data: dict[str, Any],
    new_options: dict[str, Any],
) -> tuple[str, str | None]:
    """Split a legacy multi-household entry into per-household entries.

    Called from async_migrate_entry for entries genuinely below minor_version 4.
    Mutates new_data/new_options in place with the first household's info and
    creates sibling entries for any remaining households, so the split lands in
    the same async_update_entry call the rest of the migration already does.
    Returns the (title, unique_id) to apply there (unchanged if the split
    couldn't be completed yet, e.g. a network failure - it will be retried by
    _ensure_household_split on the next setup).
    """
    if HOUSEHOLD_ID in new_data:
        return config_entry.title, config_entry.unique_id

    unconfigured = await _fetch_unconfigured_households(
        hass, new_data.get(TOKEN), new_data.get(CLIENT_DEVICE_ID)
    )
    if not unconfigured:
        return config_entry.title, config_entry.unique_id

    (first_household, first_entity_info), *remaining = unconfigured
    if not await create_sibling_entries(
        hass, new_data[TOKEN], new_data[CLIENT_DEVICE_ID], remaining
    ):
        return config_entry.title, config_entry.unique_id

    new_data[HOUSEHOLD_ID] = first_household.id
    new_options[OPTION_DEVICES] = first_entity_info
    return SurePetCareConfigFlow._household_title(first_household), str(
        first_household.id
    )


async def _ensure_household_split(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Split a legacy multi-household entry into per-household entries.

    Runs on every setup rather than being gated behind a config-entry version
    bump, so entries that were previously left without a HOUSEHOLD_ID (e.g. from
    a prior release that bumped minor_version without performing the split, or
    a split that partially failed) keep retrying until it succeeds, without
    requiring another version increment.
    """
    if HOUSEHOLD_ID in entry.data:
        return

    unconfigured = await _fetch_unconfigured_households(
        hass, entry.data.get(TOKEN), entry.data.get(CLIENT_DEVICE_ID)
    )
    if not unconfigured:
        return

    (first_household, first_entity_info), *remaining = unconfigured
    if not await create_sibling_entries(
        hass, entry.data[TOKEN], entry.data[CLIENT_DEVICE_ID], remaining
    ):
        return

    hass.config_entries.async_update_entry(
        entry,
        title=SurePetCareConfigFlow._household_title(first_household),
        data={**entry.data, HOUSEHOLD_ID: first_household.id},
        options={**entry.options, OPTION_DEVICES: first_entity_info},
        unique_id=str(first_household.id),
    )
