"""Config flow for SurePetCare integration."""

from copy import deepcopy
import logging
from typing import Any, Mapping
from enum import IntEnum

from surepcio import SurePetcareClient
from surepcio import Household

from surepcio.enums import ProductId
import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult
from homeassistant import config_entries
from homeassistant.helpers.device_registry import callback
from homeassistant.helpers.selector import selector
from homeassistant.const import CONF_PASSWORD, CONF_TOKEN, CONF_EMAIL
from .const import (
    DEVICE_OPTION,
    DOMAIN,
    ENTRY_ID,
    NAME,
    OPTION_DEVICES,
    OPTIONS_FINISHED,
    CLIENT_DEVICE_ID,
    TOKEN,
    PRODUCT_ID,
)
from .device_config_schema import DEVICE_CONFIG_SCHEMAS

logger = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class FlowAction(IntEnum):
    """Determine if setting up or reconfiguring."""

    SETUP = 0
    RECONFIGURE = 1


class SurePetCareConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore
    """Handle a config flow for SurePetCare integration."""

    VERSION = 1

    def __init__(self) -> None:
        # self.client: SurePetcareClient | None = None
        self._devices: dict[str, Any] = {}

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
        self._devices = {}
        for household in households:
            self._devices.update(
                {
                    str(device.id): device
                    for device in await client.api(household.get_devices())
                }
            )
            self._devices.update(
                {
                    str(device.id): device
                    for device in await client.api(household.get_pets())
                }
            )
        if not self._devices:
            errors["base"] = "no_devices_or_pet_found"
            return None, errors
        entity_info = {
            str(device.id): {
                PRODUCT_ID: getattr(device, PRODUCT_ID, None),
                NAME: getattr(device, NAME, device.id),
            }
            for device in self._devices.values()
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

    _device_id: str | None

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._options = deepcopy(dict(config_entry.options))
        self._devices = self._options.get(OPTION_DEVICES, {})

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Show device selection menu."""

        if user_input is not None:
            if user_input.get(OPTIONS_FINISHED):
                # End the flow and save current options
                logger.debug("OptionFlow complete, updated entities: %s", self._options)
                return self.async_create_entry(data=self._options)
            self._device_id = user_input[DEVICE_OPTION]
            return await self.async_step_configure_device()

        if not self._devices:
            return self.async_abort(reason="no_devices_or_pet_found")

        sorted_devices = sorted(
            self._devices.items(), key=lambda item: item[1].get(PRODUCT_ID, 0)
        )
        select_options = [
            {
                "value": str(k),
                "label": get_device_attr(v, NAME, str(k))
                + f" ({ProductId(v[PRODUCT_ID]).name})",
            }
            for k, v in sorted_devices
        ]
        schema = vol.Schema(
            {
                vol.Required(DEVICE_OPTION): selector(
                    {"select": {"options": select_options}}
                ),
                vol.Optional(OPTIONS_FINISHED, default=False): bool,
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
        )

    async def async_step_configure_device(
        self, user_input: dict[str, Any] | None = None
    ):
        """Configure the selected device."""

        if user_input is not None:
            self._devices[self._device_id].update(user_input)
            return await self.async_step_init()

        device = self._devices.get(self._device_id, {})
        schema_dict = _build_device_schema(device)
        return self.async_show_form(
            step_id="configure_device",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={"device_name": device[NAME]},
        )


def get_device_attr(device: Any, attr: str, default: Any = None) -> Any:
    """Get attribute or dict key from device."""
    if isinstance(device, dict):
        return device.get(attr, default)
    return getattr(device, attr, default)


def _build_device_schema(entity: dict) -> dict:
    """Build the voluptuous schema dict for the selected device."""
    schema_info = DEVICE_CONFIG_SCHEMAS.get(get_device_attr(entity, PRODUCT_ID))
    schema_dict = {}
    if schema_info:
        for key, field_type in schema_info.items():
            default_value = entity.get(key) if entity else None
            if default_value is not None:
                schema_dict[type(key)(key.schema, default=default_value)] = field_type
            else:
                schema_dict[key] = field_type
    return schema_dict
