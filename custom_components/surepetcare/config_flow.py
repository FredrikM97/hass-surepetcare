from typing import Any
from homeassistant import config_entries
from surepetcare.enums import ProductId
import homeassistant.helpers.config_validation as cv
from surepetcare.client import SurePetcareClient
import uuid
import logging
from homeassistant.core import callback

from custom_components.surepetcare.device_config_schema import DEVICE_CONFIG_SCHEMAS
from .const import CONF_EMAIL, CONF_PASSWORD, DOMAIN
import voluptuous as vol

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_EMAIL): str,
    vol.Required(CONF_PASSWORD): str,
})
class SurePetCareConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SurePetCare integration."""

    VERSION = 1 

    def __init__(self):
        self.email = None
        self.password = None
        self.client = None
        self.devices = None
        self.device_type = None
        self.client_device_id = None
        self.device_schemas = None

    async def async_step_user(self, user_input=None):
        logging.debug(f"[SurePetCareConfigFlow] async_step_user called with user_input: {user_input}")
        # Reset state to avoid leakage between runs
        self.device_type = None
        errors = {}
        if user_input is not None:
            self.email = user_input[CONF_EMAIL]
            self.password = user_input[CONF_PASSWORD]
            self.client = SurePetcareClient()
            self.generate_client_device_id()

            # Get device_id from the client after login (if available)
            if not await self.client.login(self.email, self.password):
                errors["base"] = "auth_failed"
            else:
                self.token = getattr(self.client, "token", None)
                # Try to get device_id from the client after login
              
                logging.debug(f"[SurePetCareConfigFlow] Login successful, client_device_id: {self.client_device_id}, advancing to device config step.")
                #return await self.async_step_device_config()
                devices = await self.client.get_devices()
                return self.async_create_entry(
                    title="SurePetCare device configuration",
                    data={
                        "token": getattr(self, "token", None),
                        "client_device_id": self.client_device_id,
                        "devices": devices,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
    
    def generate_client_device_id(self):
        # Generate a random device_id only once, when creating the config entry
        if not self.client_device_id:
            self.client_device_id = uuid.uuid4().hex

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry):
        return {
            "device": DeviceSubentryFlowHandler,
        }
    

class DeviceSubentryFlowHandler(config_entries.ConfigSubentryFlow):
    """Handle subentry flow for adding and modifying a location."""

    def __init__(self):
        self.product_id = None


    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """User flow to add a new device.""" 
        return await self.async_step_list_products()
        
    
    async def async_step_list_products(self, user_input={}):
        entry = self.hass.config_entries.async_get_known_entry(self._entry_id)
        devices = entry.data.get("devices", [])

        product_types = {}
        for d in devices:
            pid = d["product_id"]
            pname = ProductId(d["product_id"]).name
            product_types[pid] = pname
        return self.async_show_form(
            step_id="show_devices",
            data_schema=vol.Schema({
                vol.Required("product_id"): vol.In(product_types)
            }),
            errors={},
            description_placeholders={"product_types": ", ".join(product_types.values())}
        )
    
    async def async_step_show_devices(self, user_input:dict=None):
        self.product_id = user_input.get("product_id", None)
        entry = self.hass.config_entries.async_get_known_entry(self._entry_id)
        devices = entry.data.get("devices", [])
        matching_devices = [d for d in devices if d["product_id"] == self.product_id]
        schema_info = DEVICE_CONFIG_SCHEMAS.get(ProductId(self.product_id))
    
        combined_schema_dict = {}
        for idx, device in enumerate(matching_devices):
            combined_schema_dict.update({vol.Optional(f"{device['id']}"): schema_info['schema']})
            combined_schema = vol.Schema(combined_schema_dict)
            
            return self.async_show_form(
                    step_id="device_config",
                    data_schema=combined_schema,
                    errors={},
                    description_placeholders={"product_type": ProductId(self.product_id).name}
                )

    async def async_step_device_config(self, user_input=None):
       
       
        return self.async_create_entry(
            title=f"{ProductId(self.product_id).name} Devices",
            data={"product_id": self.product_id, "device": user_input},
        ) 