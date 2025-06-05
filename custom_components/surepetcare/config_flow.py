"""Config flow for SurePetCare integration."""

import logging
import types
from typing import Any
import uuid

from surepetcare.client import SurePetcareClient
import voluptuous as vol

from config.custom_components.spc import Household
from homeassistant import config_entries
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback

from .const import CONF_EMAIL, CONF_PASSWORD, DOMAIN
from .device_config_schema import DEVICE_CONFIG_SCHEMAS

logger = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


def add_method(instance, id):
    """Add func as a method to cls."""
    name = f"async_step_{id}"

    async def device_step(self, user_input=None):
        return await self.async_step_configure_device(user_input, id=id)

    device_step.__name__ = name
    setattr(instance, name, types.MethodType(device_step, instance))


class SurePetCareConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SurePetCare integration."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.client = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Authenticate and fetch devices."""
        errors = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]
            self.client = SurePetcareClient()
            logged_in = await self.client.login(email=email, password=password)

            # Ensure client is closed after fetching data
            await self.client.close()
            if not logged_in:
                errors["base"] = "auth_failed"
            else:
                return await self.async_step_create_entry()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this integration."""
        return {"device": SurePetCareDeviceSubentryFlowHandler}

    async def async_step_create_entry(self, user_input: dict[str, Any] | None = None):
        """Create the config entry with all device configs."""

        return self.async_create_entry(
            title="SurePetCare Devices",
            data={
                "token": self.client.token,
                "client_device_id": self.client.device_id,
            },
            subentries=await self._setup_subentry_data(),
        )

    async def _setup_subentry_data(self):
        """Set up subentry data for devices and pets."""

        households = await self.client.api(Household.get_households())
        entities = []
        for household in households:
            entities.extend(await self.client.api(household.get_devices()))
            entities.extend(await self.client.api(household.get_pets()))
        # Ensure client is closed after fetching data
        await self.client.close()
        if not entities:
            return self.async_abort(reason="no_devices_or_pet_found")

        # devices = {d.id: d for d in devices}

        # Just iterate data to define which device available for subentry
        subentries = []
        subentries.extend(
            [
                {
                    "title": entity.name,
                    "data": {
                        "id": str(entity.id),
                        "name": entity.name,
                        "product_id": entity.product_id,
                    },
                    "subentry_type": "device",
                }
                for entity in entities
            ]
        )
        return subentries


class SurePetCareDeviceSubentryFlowHandler(ConfigSubentryFlow):
    """Handle subentry flow for adding and modifying a SurePetCare device."""

    def build_dynamic_schema(self, schema_info: dict, current_data: dict) -> vol.Schema:
        """Build a voluptuous schema with dynamic defaults based on current_data."""
        fields = {}
        for key, validator in schema_info.items():
            # Use the value from current_data if present, otherwise use the default from the schema
            default = current_data.get(key, getattr(key, "default", None))
            if isinstance(key, vol.Required):
                fields[vol.Required(key.schema, default=default)] = validator
            elif isinstance(key, vol.Optional):
                fields[vol.Optional(key.schema, default=default)] = validator
            else:
                # If key is just a string, treat as Required
                fields[vol.Required(key, default=default)] = validator
        return vol.Schema(fields)

    async def async_step_configure_user(self, user_input: dict[str, Any] | None = None):
        """Configure a device subentry."""
        if user_input is not None:
            # Save the updated options for this device subentry
            return self.async_create_entry(data=user_input)

        return await self.async_step_select_device()

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry()
        device = entry.subentries[subentry.subentry_id]
        product_id = device.data["product_id"]
        schema_info = DEVICE_CONFIG_SCHEMAS.get(product_id)

        if user_input is not None:
            return self.async_update_and_abort(
                entry=entry,
                subentry=subentry,
                data_updates=user_input,
            )

        if schema_info["schema"] is None:
            return self.async_abort(reason="no_reconfigure_schema")

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.build_dynamic_schema(schema_info["schema"], subentry.data),
            description_placeholders={
                "device_name": device.data["name"],
            },
        )
