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


class SurePetCareConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore
    """Handle a config flow for SurePetCare integration."""

    VERSION = 1
    MINOR_VERSION = 3

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step to login the user"""
        errors: dict = {}
        if user_input is not None:
            client, error = await self._authenticate(
                email=user_input.get(CONF_EMAIL), password=user_input.get(CONF_PASSWORD)
            )
            errors.update(error)

            entity_info, error = await self._async_fetch_entities(client)
            errors.update(error)
            await client.close()
            if not errors:
                logger.debug(
                    "Configuration complete, updated entities: %s", entity_info
                )
                return self.async_create_entry(
                    title="SurePetCare Devices",
                    data={
                        CONF_TOKEN: client.token,
                        CLIENT_DEVICE_ID: client.device_id,
                    },
                    options={
                        OPTION_DEVICES: entity_info,
                    },
                )
        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def _async_fetch_entities(self, client: SurePetcareClient):
        """Authenticate and fetch devices/pets, return (entity_info, error)."""
        errors = {}
        households: list[Household] = await client.api(Household.get_households())
        _devices = {}
        for household in households:
            _devices.update(
                {
                    str(device.id): device
                    for device in await client.api(household.get_devices())
                }
            )
            _devices.update(
                {
                    str(device.id): device
                    for device in await client.api(household.get_pets())
                }
            )
        if not _devices:
            errors["base"] = "no_devices_or_pet_found"
            return None, errors
        # Append NAME and PRODUCT_ID to each device in OPTION_DEVICE
        entity_info = {
            str(device.id): {
                PRODUCT_ID: getattr(device, PRODUCT_ID, None),
                NAME: getattr(device, NAME, device.id),
            }
            for device in _devices.values()
        }
        return entity_info, errors

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        """Migration step in case entities not populated/new device added."""
        entry = self.hass.config_entries.async_get_entry(self.context[ENTRY_ID])
        client, _ = await self._authenticate(
            token=entry.data[TOKEN], device_id=entry.data[CLIENT_DEVICE_ID]
        )
        entity_info, _ = await self._async_fetch_entities(client)
        await client.close()
        self.hass.config_entries.async_update_entry(
            entry, options={OPTION_DEVICES: entity_info}
        )
        logger.debug("Reconfiguration complete, updated entities: %s", entity_info)
        return self.async_abort(reason="entities_reconfigured")

    async def _authenticate(
        self, email=None, password=None, token=None, device_id=None
    ) -> tuple[SurePetcareClient, dict]:
        errors = {}
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
            client, errors = await self._authenticate(
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
