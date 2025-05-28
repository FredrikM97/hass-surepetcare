"""Config flow for SurePetCare integration."""

import logging
import types
import uuid
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from surepetcare.client import SurePetcareClient
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
    # return device_step  # Optional: allows normal use of func


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
                devices = await client.get_devices(household_ids)

                if not devices:
                    return self.async_abort(reason="no_devices_found")

                self.devices = {d.id: d for d in devices}
                await client.close()

                return await self.async_step_select_device()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_select_device(self, user_input: dict[str, Any] | None = None):
        """Let the user select which device to configure next using a menu."""
        if not self.devices:
            return self.async_abort(reason="no_devices_found")

        # Filter out already-configured devices
        configured_ids = {str(d["id"]) for d in self.device_configs}
        available_devices = [
            d for d in self.devices.values() if str(d.id) not in configured_ids
        ]
        # Always show the menu if there are devices left
        if not available_devices:
            return self.async_step_create_entry()

        # Dynamically create methods for each device to handle configuration
        # This allows us to have a separate step for each device
        # Maybe not the best design, but it keeps the flow "simple"
        for device in self.devices.values():
            add_method(self, device.id)
            # setattr(self, method_name, types.MethodType(device_step, self))

        menu_options = {str(d.id): d.name for d in available_devices}
        menu_options["create_entry"] = "Finish configuration"

        # if user_input is not None:
        #    selected_id = user_input["menu_option"]
        #    if selected_id == "skip":
        #        return self._create_entry_with_devices()
        # self._device_idx = next(
        #    idx for idx, d in enumerate(self.devices) if str(d.id) == selected_id
        # )
        # Always go to configure_device, even if only one device left
        #    return await self.async_step_configure_device()

        return self.async_show_menu(
            step_id="select_device",
            menu_options=menu_options,
            description_placeholders={},
        )

    async def async_step_configure_device(
        self, user_input: dict[str, Any] | None = None, id=None
    ):
        """Configure a single device."""
        if id is not None:
            device = self.devices[id]
        if user_input and "id" in user_input:
            device = self.devices.get(user_input["id"])
        if user_input is not None:
            config = {
                "id": str(device.id),
                "name": device.name,
                "product_id": device.product_id,
                **user_input,
            }
            self.device_configs.append(config)
            return await self.async_step_select_device()

        schema_info = DEVICE_CONFIG_SCHEMAS.get(device.product_id)
        data_schema = vol.Schema(
            {
                vol.Required("id"): device.id,
                **(
                    schema_info["schema"]
                    if schema_info and schema_info["schema"]
                    else {}
                ),
            }
        )

        description = f"Configure: {device.name}"

        return self.async_show_form(
            step_id="configure_device",
            data_schema=data_schema,
            description_placeholders={"device_name": device.name, "info": description},
        )

    async def async_step_create_entry(self, user_input: dict[str, Any] | None = None):
        """Create the config entry with all device configs."""
        return self.async_create_entry(
            title="SurePetCare Devices",
            data={
                "token": self.token,
                "client_device_id": self.client_device_id,
                "devices": self.device_configs,
            },
        )
