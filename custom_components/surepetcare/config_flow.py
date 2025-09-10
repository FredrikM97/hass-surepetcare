"""Config flow for SurePetCare integration."""

import logging
from typing import Any
from enum import IntEnum

from surepcio.client import SurePetcareClient
from surepcio.household import Household
import voluptuous as vol

from homeassistant import config_entries

from .const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    COORDINATOR,
    COORDINATOR_DICT,
    DOMAIN,
    ENTRY_ID,
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
        """Initialize the config flow."""
        self.client: SurePetcareClient = None
        self._entities: dict = {}
        self._device_index: str | None = None
        self._device_config: dict = {}
        self._device_id: str | None = None
        self.action: FlowAction | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Authenticate and fetch devices, then show menu for device config."""
        errors = {}
        self.action = FlowAction.SETUP
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
                    return self.async_show_form(
                        step_id="user",
                        data_schema=STEP_USER_DATA_SCHEMA,
                        errors=errors,
                    )
                households = await self.client.api(Household.get_households())
                self._entities = {}
                for household in households:
                    self._entities.update(
                        {
                            str(device.id): device
                            for device in await self.client.api(household.get_devices())
                        }
                    )
                    self._entities.update(
                        {
                            str(device.id): device
                            for device in await self.client.api(household.get_pets())
                        }
                    )
                await self.client.close()

                if not self._entities:
                    errors["base"] = "no_devices_or_pet_found"
                    return self.async_show_form(
                        step_id="user",
                        data_schema=STEP_USER_DATA_SCHEMA,
                        errors=errors,
                    )
                return await self.async_step_select_device()
        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_select_device(self, user_input: dict[str, Any] | None = None):
        """Show a form to select a device to configure. Require all with schema."""

        if user_input is not None and user_input["device_option"] == "Finish setup":
            return await self.async_step_create_entry()

        devices_with_schema = {
            idt: e
            for idt, e in self._entities.items()
            if (
                (
                    schema_info := DEVICE_CONFIG_SCHEMAS.get(
                        get_device_attr(e, "product_id")
                    )
                )
                and isinstance(schema_info, dict)
                and schema_info.get("schema") not in (None, {}, [])
            )
        }
        device_map = {
            get_device_attr(entity, "name"): idt
            for idt, entity in devices_with_schema.items()
        }

        if user_input is not None:
            self._device_id = device_map[user_input["device_option"]]
            return await self.async_step_configure_device()

        schema = vol.Schema(
            {
                vol.Required("device_option"): vol.In(
                    [*list(device_map.keys()), "Finish setup"]
                )
            }
        )

        return self.async_show_form(
            step_id="select_device",
            data_schema=schema,
            description_placeholders={"device_count": len(device_map)},
            errors={},
        )

    async def async_step_configure_device(
        self, user_input: dict[str, Any] | None = None
    ):
        """Configure the selected device using its schema."""
        entity = self._entities[self._device_id]
        schema_info = DEVICE_CONFIG_SCHEMAS.get(get_device_attr(entity, "product_id"))
        schema = schema_info.get("schema", {}) if isinstance(schema_info, dict) else {}

        existing_config = self._device_config.get(self._device_id, {})
        if len(existing_config) == 0:
            schema_dict = schema
        else:
            # Rework in future update - Currently works to set default value if exists
            schema_dict = {}
            for key, field_type in schema.items():
                default_value = existing_config.get(key) if existing_config else None
                if default_value is not None:
                    schema_dict[vol.Required(key.schema, default=default_value)] = (
                        field_type
                    )
                else:  # If no previous value, just use the field type
                    schema_dict.update({key: field_type})
        schema = vol.Schema(schema_dict)

        if user_input is not None:
            self._device_config[self._device_id] = user_input
            return await self.async_step_select_device()

        if not isinstance(schema, vol.Schema):
            schema = vol.Schema(schema)

        return self.async_show_form(
            step_id="configure_device",
            data_schema=schema,
            description_placeholders={
                "device_name": get_device_attr(entity, "name"),
                "product_id": get_device_attr(entity, "product_id"),
            },
            errors={},
        )

    async def async_step_create_entry(self, user_input: dict[str, Any] | None = None):
        """Create the config entry with all device configs."""
        if self.action == FlowAction.SETUP:
            return self.async_create_entry(
                title="SurePetCare Devices",
                data={
                    "token": getattr(self.client, "token", None),
                    "client_device_id": self.client.device_id,
                },
                options=self._device_config,
            )
        if self.action == FlowAction.RECONFIGURE:
            return self.async_update_reload_and_abort(
                self._get_reconfigure_entry(),
                options=self._device_config,
            )
        raise Exception("Invalid flow action")

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        """Allow user to reconfigure settings for any device with a schema."""
        self.action = FlowAction.RECONFIGURE
        self._entities = {
            str(device.data.id): device.data
            for device in self.hass.data[DOMAIN][self.context[ENTRY_ID]][COORDINATOR][
                COORDINATOR_DICT
            ].values()
        }
        self._device_config = dict(
            self.hass.config_entries.async_get_known_entry(
                self.context[ENTRY_ID]
            ).options
        )
        return await self.async_step_select_device()


def get_device_attr(device: Any, attr: str, default: Any = None) -> Any:
    """Get attribute or dict key from device."""
    if isinstance(device, dict):
        return device.get(attr, default)
    return getattr(device, attr, default)
