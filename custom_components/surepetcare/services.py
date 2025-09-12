import logging
import voluptuous as vol
from custom_components.surepetcare.const import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import async_get as async_get_device_registry

import logging

logger = logging.getLogger(__name__)
_service_registry = []


def global_service(name, schema=None):
    """Decorator to register a global service for the integration."""

    def decorator(func):
        _service_registry.append((name, func, schema))
        return func

    return decorator


# Import for entity-specific service registration


@global_service(
    "set_debug_logging",
    schema=vol.Schema(
        {
            vol.Required("level"): vol.In(
                ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            )
        }
    ),
)
async def async_set_debug_logging(call):
    """Set debug logging level for surepetcare integration and library."""
    level = getattr(logging, call.data["level"], logging.INFO)
    logging.getLogger("custom_components.surepetcare").setLevel(level)
    logging.getLogger("surepcio").setLevel(level)


@global_service(
    "set_control",
    schema=vol.Schema(
        {
            vol.Required("device_id"): str,
            vol.Optional("control"): dict,
        }
    ),
)
async def async_set_control(call):
    coordinator = get_coordinator(call.hass, call.data.get("device_id"))
    await coordinator.client.api(
        coordinator._device.set_control(**call.data.get("control"))
    )


@global_service(
    "set_tag",
    schema=vol.Schema(
        {
            vol.Required("device_id"): str,
            vol.Required("tag"): str,
            vol.Required("action"): vol.In(["add", "remove"]),
        }
    ),
)
async def async_set_tag(call):
    device_coordinator = get_coordinator(call.hass, call.data.get("device_id"))
    pet_coordinator = get_coordinator(call.hass, call.data.get("tag"))
    pet_coordinator
    if call.data.get("action") == "add":
        await device_coordinator.client.api(
            device_coordinator._device.add_tag(
                get_coordinator(call.hass, call.data.get("tag"))._device.tag
            )
        )
    elif call.data.get("action") == "remove":
        await device_coordinator.client.api(
            device_coordinator._device.remove_tag(
                get_coordinator(call.hass, call.data.get("tag"))._device.tag
            )
        )


def get_coordinator(hass, device_id):
    device_registry = async_get_device_registry(hass)
    device = device_registry.async_get(device_id)
    domain, device_id = next(iter(device.identifiers))

    coordinator = hass.data[domain][device.primary_config_entry]["coordinator"][
        "coordinator_dict"
    ][device_id]
    return coordinator
