"""Config flow for SurePetCare integration."""

from copy import deepcopy
import logging
from typing import Any
from enum import IntEnum

from surepcio.client import SurePetcareClient
from surepcio.household import Household

from surepcio.enums import ProductId
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.device_registry import callback
from homeassistant.helpers.selector import selector

from .const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    DOMAIN,
    POLLING_SPEED,
    SCAN_INTERVAL,
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
        self._entities: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Authenticate and fetch devices, then show menu for device config."""
        errors = {}
        if user_input is not None:
            email = user_input.get(CONF_EMAIL)
            password = user_input.get(CONF_PASSWORD)
            self.client = SurePetcareClient()
            logged_in = await self.client.login(email=email, password=password)
            if not logged_in:
                errors["base"] = "auth_failed"
            else:
                token = getattr(self.client, "token", None)
                if not token:
                    errors["base"] = "cannot_connect"
                else:
                    households = await self.client.api(Household.get_households())
                    self._entities = {}
                    for household in households:
                        self._entities.update(
                            {
                                str(device.id): device
                                for device in await self.client.api(
                                    household.get_devices()
                                )
                            }
                        )
                        self._entities.update(
                            {
                                str(device.id): device
                                for device in await self.client.api(
                                    household.get_pets()
                                )
                            }
                        )
                    await self.client.close()

                    if not self._entities:
                        errors["base"] = "no_devices_or_pet_found"
                    else:
                        # Save serializable info for each entity: entity_id, product_id, name
                        entity_info = {
                            str(device.id): {
                                "product_id": getattr(device, "product_id", None),
                                "name": getattr(device, "name", str(device.id)),
                            }
                            for device in self._entities.values()
                        }
                        return self.async_create_entry(
                            title="SurePetCare Devices",
                            data={
                                "token": token,
                                "client_device_id": self.client.device_id,
                                "entities": entity_info,
                            },
                        )
        return self.async_show_form(
            step_id="user",
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

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Show device selection menu."""

        if user_input is not None:
            if user_input.get("finished"):
                # End the flow and save current options
                return self.async_create_entry(data=self._options)
            self._device_id = user_input["device_option"]
            return await self.async_step_configure_device()

        entities = self.config_entry.data.get("entities", {})
        if not entities:
            return self.async_abort(reason="no_devices_or_pet_found")

        sorted_entities = sorted(
            entities.items(), key=lambda item: item[1].get("product_id", 0)
        )
        select_options = [
            {
                "value": str(k),
                "label": get_device_attr(v, "name", str(k))
                + f" ({ProductId(v['product_id']).name})",
            }
            for k, v in sorted_entities
        ]
        schema = vol.Schema(
            {
                vol.Required("device_option"): selector(
                    {"select": {"options": select_options}}
                ),
                vol.Optional("finished", default=False): bool,
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
            self._options[self._device_id] = user_input
            return await self.async_step_init()

        entity = self.config_entry.data.get("entities", {})[self._device_id]
        schema_info = DEVICE_CONFIG_SCHEMAS.get(get_device_attr(entity, "product_id"))
        existing_config = self._options.get(self._device_id, {})
        schema_dict = {}

        if schema_info:
            for key, field_type in schema_info.items():
                default_value = existing_config.get(key) if existing_config else None
                if default_value is not None:
                    schema_dict[type(key)(key.schema, default=default_value)] = (
                        field_type
                    )
                else:
                    schema_dict[key] = field_type

        # Add polling speed option (in seconds), default SCAN_INTERVAL
        polling_default = existing_config.get(POLLING_SPEED, SCAN_INTERVAL)
        schema_dict[vol.Optional(POLLING_SPEED, default=polling_default)] = vol.All(
            int, vol.Range(min=5, max=86400)
        )

        schema = vol.Schema(schema_dict)

        return self.async_show_form(
            step_id="configure_device",
            data_schema=schema,
            description_placeholders={"device_name": entity["name"]},
        )


def get_device_attr(device: Any, attr: str, default: Any = None) -> Any:
    """Get attribute or dict key from device."""
    if isinstance(device, dict):
        return device.get(attr, default)
    return getattr(device, attr, default)
