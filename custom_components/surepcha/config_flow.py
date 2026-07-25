"""Config flow for SurePetCare integration."""

from copy import deepcopy
import logging
from typing import Any, Mapping

from surepcio import SurePetcareClient
from surepcio import Household
from surepcio.enums import ProductId

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult
from homeassistant import config_entries
from homeassistant.data_entry_flow import section
from homeassistant.helpers.device_registry import callback
from homeassistant.const import CONF_PASSWORD, CONF_TOKEN, CONF_EMAIL


from .const import (
    DOMAIN,
    ENTRY_ID,
    HOUSEHOLD_ID,
    HOUSEHOLD_SUBENTRY_TYPE,
    NAME,
    OPTION_DEVICES,
    CLIENT_DEVICE_ID,
    TOKEN,
    PRODUCT_ID,
    OPTION_PROPERTIES,
)
from .device_config_schema import (
    DEVICE_CONFIG_SCHEMAS,
    MANUAL_PROPERTIES,
    OPTION_CONFIG_SCHEMAS,
)

logger = logging.getLogger(__name__)

MANUAL_PROPERTIES_SCHEMA = next(iter(OPTION_CONFIG_SCHEMAS.values())).schema.schema

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def _authenticate(
    email=None, password=None, token=None, device_id=None
) -> tuple[SurePetcareClient, dict]:
    """Authenticate a fresh client, returning it plus any error keyed for a form."""
    errors: dict = {}
    client = SurePetcareClient()
    logged_in = await client.login(
        email=email, password=password, token=token, device_id=device_id
    )

    if not logged_in:
        errors["base"] = "auth_failed"

    token = getattr(client, TOKEN, None)
    if not token:
        errors["base"] = "cannot_connect"

    return client, errors


async def _async_fetch_households(client: SurePetcareClient):
    """Fetch each household's devices/pets, return (households, error).

    Households with no devices or pets are omitted entirely.
    """
    errors: dict = {}
    households: list[Household] = await client.api(Household.get_households())
    result = []
    for household in households:
        devices = await client.api(household.get_devices())
        pets = await client.api(household.get_pets())
        combined = {str(d.id): d for d in [*devices, *pets]}
        if not combined:
            continue
        entity_info = {
            str(device.id): {
                PRODUCT_ID: getattr(device, PRODUCT_ID, None),
                NAME: getattr(device, NAME, device.id),
            }
            for device in combined.values()
        }
        result.append(
            {
                "id": household.id,
                "name": (household.data.get("name") or "").strip(),
                "entity_info": entity_info,
            }
        )
    if not result:
        errors["base"] = "no_devices_or_pet_found"
    return result, errors


def _merge_entity_info(households: list[dict]) -> dict:
    """Merge each household's entity_info into one flat dict, keyed by device id."""
    merged: dict = {}
    for household in households:
        merged.update(household["entity_info"])
    return merged


class SurePetCareConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore
    """Handle a config flow for SurePetCare integration."""

    VERSION = 1
    MINOR_VERSION = 4

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step to login the user"""
        errors: dict = {}
        if user_input is not None:
            client, error = await _authenticate(
                email=user_input.get(CONF_EMAIL), password=user_input.get(CONF_PASSWORD)
            )
            errors.update(error)

            households, error = await _async_fetch_households(client)
            errors.update(error)
            await client.close()
            if not errors:
                logger.debug(
                    "Configuration complete, households: %s",
                    [household["id"] for household in households],
                )
                return self.async_create_entry(
                    title="SurePetCare Devices",
                    data={
                        CONF_TOKEN: client.token,
                        CLIENT_DEVICE_ID: client.device_id,
                    },
                    options={
                        OPTION_DEVICES: _merge_entity_info(households),
                        OPTION_PROPERTIES: {},
                    },
                    subentries=[
                        config_entries.ConfigSubentryData(
                            title=household["name"] or f"Household {household['id']}",
                            unique_id=str(household["id"]),
                            subentry_type=HOUSEHOLD_SUBENTRY_TYPE,
                            data={HOUSEHOLD_ID: household["id"]},
                        )
                        for household in households
                    ],
                )
        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        """Refresh device metadata for an existing entry (does not add new households)."""
        entry = self.hass.config_entries.async_get_entry(self.context[ENTRY_ID])
        client, _ = await _authenticate(
            token=entry.data[TOKEN], device_id=entry.data[CLIENT_DEVICE_ID]
        )
        households, _errors = await _async_fetch_households(client)
        await client.close()
        option_properties = entry.options.get(OPTION_PROPERTIES, {})
        self.hass.config_entries.async_update_entry(
            entry,
            options={
                OPTION_DEVICES: _merge_entity_info(households),
                OPTION_PROPERTIES: option_properties,
            },
        )
        logger.debug(
            "Reconfiguration complete, households: %s",
            [household["id"] for household in households],
        )
        return self.async_abort(reason="entities_reconfigured")

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle configuration by re-auth."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Dialog that informs the user that reauth is required."""
        reauth_entry = self._get_reauth_entry()
        if user_input is not None:
            client, errors = await _authenticate(
                email=reauth_entry.data[CONF_EMAIL], password=user_input[CONF_PASSWORD]
            )
            await client.close()
            if not errors:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates={
                        CONF_TOKEN: client.token,
                        CLIENT_DEVICE_ID: client.device_id,
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        return SurePetCareOptionsFlow(config_entry)

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: config_entries.ConfigEntry
    ) -> dict[str, type[config_entries.ConfigSubentryFlow]]:
        """Return subentry types supported by this integration."""
        return {HOUSEHOLD_SUBENTRY_TYPE: HouseholdSubentryFlow}


class HouseholdSubentryFlow(config_entries.ConfigSubentryFlow):
    """Flow for adding an additional household as a subentry to an existing entry."""

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Add a household on this account that isn't yet configured."""
        entry = self._get_entry()
        client, errors = await _authenticate(
            token=entry.data[TOKEN], device_id=entry.data[CLIENT_DEVICE_ID]
        )
        households: list[dict] = []
        if not errors:
            households, fetch_errors = await _async_fetch_households(client)
            errors.update(fetch_errors)
        await client.close()

        if errors:
            return self.async_abort(reason="cannot_connect")

        existing_ids = {subentry.unique_id for subentry in entry.subentries.values()}
        new_households = [
            household
            for household in households
            if str(household["id"]) not in existing_ids
        ]
        if not new_households:
            return self.async_abort(reason="no_new_household_found")

        household = new_households[0]
        return self.async_create_entry(
            title=household["name"] or f"Household {household['id']}",
            unique_id=str(household["id"]),
            data={HOUSEHOLD_ID: household["id"]},
        )


class SurePetCareOptionsFlow(config_entries.OptionsFlowWithReload):
    """Options flow for SurePetCare integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._options = deepcopy(dict(config_entry.options))

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Show the top-level options menu."""

        if not self._options[OPTION_DEVICES]:
            return self.async_abort(reason="no_devices_or_pet_found")

        return self.async_show_menu(
            step_id="init",
            menu_options=["manual_properties", "devices"],
        )

    async def async_step_manual_properties(
        self, user_input: dict[str, Any] | None = None
    ):
        """Configure manual location labels."""

        if user_input is not None:
            option_properties = dict(self._options.get(OPTION_PROPERTIES, {}))
            if user_input:
                option_properties[MANUAL_PROPERTIES] = user_input
            self._options[OPTION_PROPERTIES] = option_properties
            return self.async_create_entry(title="", data=self._options)

        manual_properties = self._options.get(OPTION_PROPERTIES, {}).get(
            MANUAL_PROPERTIES, {}
        )
        manual_form_schema, _ = _build_schema_and_defaults(
            MANUAL_PROPERTIES_SCHEMA, manual_properties
        )
        return self.async_show_form(
            step_id="manual_properties",
            data_schema=vol.Schema(manual_form_schema),
        )

    async def async_step_devices(self, user_input: dict[str, Any] | None = None):
        """Configure all devices in a single form."""

        device_sections = _device_picker_options(self._options[OPTION_DEVICES])

        if user_input is not None:
            for device_id, section_key in device_sections:
                if section_key in user_input:
                    self._options[OPTION_DEVICES][device_id].update(
                        user_input[section_key]
                    )
            return self.async_create_entry(title="", data=self._options)

        schema_dict = {}
        for device_id, section_key in device_sections:
            device = self._options[OPTION_DEVICES][device_id]
            device_schema, section_defaults = _build_schema_and_defaults(
                DEVICE_CONFIG_SCHEMAS.get(device.get(PRODUCT_ID)), device
            )
            schema_dict[
                vol.Optional(
                    section_key,
                    default=section_defaults,
                )
            ] = section(vol.Schema(device_schema), {"collapsed": True})

        return self.async_show_form(
            step_id="devices",
            data_schema=vol.Schema(schema_dict),
        )


def _build_schema_and_defaults(
    schema_info: dict[Any, Any] | None, values: dict[str, Any]
) -> tuple[dict[Any, Any], dict[str, Any]]:
    """Build a schema and the corresponding default payload from saved values."""
    schema_dict = {}
    defaults = {}

    for key, field_type in (schema_info or {}).items():
        field_name = key.schema if hasattr(key, "schema") else key

        if field_name in values:
            default_value = values[field_name]
            schema_dict[type(key)(field_name, default=default_value)] = field_type
            defaults[field_name] = default_value
        elif hasattr(key, "default") and key.default is not vol.UNDEFINED:
            defaults[field_name] = key.default()
            schema_dict[key] = field_type
        else:
            schema_dict[key] = field_type

    return schema_dict, defaults


def _device_picker_options(devices: dict[str, dict[str, Any]]) -> list[tuple[str, str]]:
    """Return readable device labels for device sections."""
    options = []

    for device_id, device in devices.items():
        product_id = device.get(PRODUCT_ID)
        try:
            product_name = ProductId(product_id).name
        except (TypeError, ValueError):
            product_name = str(product_id) if product_id is not None else "UNKNOWN"

        label = (
            f"{product_name.replace('_', ' ').title()}: {device.get(NAME) or device_id}"
        )
        options.append((device_id, label))

    return options
