"""Config flow for SurePetCare integration."""

import logging
import uuid
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from surepetcare.client import SurePetcareClient
from .const import CONF_EMAIL, CONF_PASSWORD, DOMAIN
from .device_config_schema import DEVICE_CONFIG_SCHEMAS
from homeassistant.data_entry_flow import section

logger = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class SurePetCareConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SurePetCare integration."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.devices: list[Any] = []
        self.device_configs: list[dict[str, Any]] = []
        self.token: str | None = None
        self.client_device_id: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Authenticate and fetch devices."""
        errors = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]
            client = SurePetcareClient()

            if not await client.login(email=email, password=password):
                errors["base"] = "auth_failed"
            else:
                self.token = getattr(client, "_token", None)
                self.client_device_id = uuid.uuid4().hex
                household_ids = [
                    household["id"] for household in (await client.get_households())
                ]
                self.devices = await client.get_devices(household_ids)
                await client.close()
                if not self.devices:
                    return self.async_abort(reason="no_devices_found")
                return await self.async_step_configure_devices()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_configure_devices(
        self, user_input: dict[str, Any] | None = None
    ):
        """Configure all devices in a single form with sections."""
        if user_input is not None:
            self.device_configs = []
            for device in self.devices:
                section_key = f"{device.name} ({device.product_id})"
                device_section = user_input.get(section_key, {})
                config = {
                    "id": str(device.id),
                    "name": device.name,
                    "product_id": device.product_id,
                    **device_section,
                }
                self.device_configs.append(config)
            return self._create_entry_with_devices()

        schema_dict = {}
        description_placeholders = {}
        for device in self.devices:
            schema_info = DEVICE_CONFIG_SCHEMAS.get(device.product_id)
            # if schema_info and schema_info["schema"]:
            #    device_schema = schema_info["schema"]
            # else:
            #    device_schema = vol.Schema({})
            # schema_dict[section(f"{device.name} ({device.product_id})")] = device_schema
            if not schema_info["schema"]:
                continue
            # schema_dict[vol.Required(f"{device.id}")] = section(
            #    vol.Schema(schema_info["schema"])
            # )
            # TODO ISSUE IS THAT en.json does not contain text therefor section is emopty...
            section_title = self.hass.config_entries.async_entry_for_domain_unique_id.translation.async_translate(
                "config.step.configure_devices.section_title",
                {"device_name": device.name, "product_id": device.product_id},
            )
            schema_dict[section(section_title)] = section(
                vol.Schema(schema_info["schema"])
            )
        data_schema = vol.Schema(schema_dict)

        return self.async_show_form(
            step_id="configure_devices",
            data_schema=data_schema,
            errors={},
        )

    def _create_entry_with_devices(self):
        """Create the config entry with all device configs."""
        return self.async_create_entry(
            title="SurePetCare Devices",
            data={
                "token": self.token,
                "client_device_id": self.client_device_id,
                "devices": self.device_configs,
            },
        )
