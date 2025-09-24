"""Config flow for SurePetCare integration."""

from copy import deepcopy
import logging
from typing import Any
from enum import IntEnum

from surepcio import SurePetcareClient
from surepcio import Household

from surepcio.enums import ProductId
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.device_registry import callback
from homeassistant.helpers.selector import selector

from .const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    DEVICE_OPTION,
    DOMAIN,
    OPTION_DEVICES,
    OPTIONS_FINISHED,
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
        self.client: SurePetcareClient | None = None
        self._devices: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step to login the user"""
        errors = {}
        if user_input is not None:
            email = user_input.get(CONF_EMAIL)
            password = user_input.get(CONF_PASSWORD)
            (
                token,
                client_device_id,
                entity_info,
                error,
            ) = await self._async_fetch_entities(email=email, password=password)
            if error:
                errors["base"] = error
            else:
                logger.debug(
                    "Configuration complete, updated entities: %s", entity_info
                )
                return self.async_create_entry(
                    title="SurePetCare Devices",
                    data={
                        "token": token,
                        "client_device_id": client_device_id,
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

    async def _async_fetch_entities(
        self,
        email: str | None = None,
        password: str | None = None,
        token: str | None = None,
        device_id: str | None = None,
    ):
        """Authenticate and fetch devices/pets, return (token, client_device_id, entity_info, error)."""
        self.client = SurePetcareClient()
        logged_in = await self.client.login(
            email=email, password=password, token=token, device_id=device_id
        )
        if not logged_in:
            return None, None, None, "auth_failed"
        token = getattr(self.client, "token", None)
        if not token:
            return None, None, None, "cannot_connect"
        households = await self.client.api(Household.get_households())
        self._devices = {}
        for household in households:
            self._devices.update(
                {
                    str(device.id): device
                    for device in await self.client.api(household.get_devices())
                }
            )
            self._devices.update(
                {
                    str(device.id): device
                    for device in await self.client.api(household.get_pets())
                }
            )
        await self.client.close()
        if not self._devices:
            return None, None, None, "no_devices_or_pet_found"
        entity_info = {
            str(device.id): {
                "product_id": getattr(device, "product_id", None),
                "name": getattr(device, "name", device.id),
            }
            for device in self._devices.values()
        }
        return token, self.client.device_id, entity_info, None

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        """Migration step in case entities not populated/new device added."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        token = entry.data["token"]
        device_id = entry.data["client_device_id"]

        _, _, entity_info, _ = await self._async_fetch_entities(
            token=token, device_id=device_id
        )

        self.hass.config_entries.async_update_entry(
            entry, options={OPTION_DEVICES: entity_info}
        )
        logger.debug("Reconfiguration complete, updated entities: %s", entity_info)
        return self.async_abort(reason="entities_reconfigured")

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
            self._devices.items(), key=lambda item: item[1].get("product_id", 0)
        )
        select_options = [
            {
                "value": str(k),
                "label": get_device_attr(v, "name", str(k))
                + f" ({ProductId(v['product_id']).name})",
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
            description_placeholders={"device_name": device["name"]},
        )


def get_device_attr(device: Any, attr: str, default: Any = None) -> Any:
    """Get attribute or dict key from device."""
    if isinstance(device, dict):
        return device.get(attr, default)
    return getattr(device, attr, default)


def _build_device_schema(entity: dict) -> dict:
    """Build the voluptuous schema dict for the selected device."""
    schema_info = DEVICE_CONFIG_SCHEMAS.get(get_device_attr(entity, "product_id"))
    schema_dict = {}
    if schema_info:
        for key, field_type in schema_info.items():
            default_value = entity.get(key) if entity else None
            if default_value is not None:
                schema_dict[type(key)(key.schema, default=default_value)] = field_type
            else:
                schema_dict[key] = field_type
    return schema_dict
