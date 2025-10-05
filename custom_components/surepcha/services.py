import logging
import voluptuous as vol
from homeassistant.helpers.device_registry import async_get as async_get_device_registry
from surepcio.enums import PetDeviceLocationProfile
from surepcio.enums import ModifyDeviceTag, PetLocation
from surepcio.devices import Pet

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
    logging.getLogger("custom_components.surepcha").setLevel(level)
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
            vol.Required("pet_id"): str,
            vol.Required("action"): vol.In([e.name for e in ModifyDeviceTag]),
        }
    ),
)
async def async_set_tag(call):
    device_coordinator = get_coordinator(call.hass, call.data.get("device_id"))
    pet_coordinator = get_coordinator(call.hass, call.data.get("pet_id"))
    await device_coordinator.client.api(
        device_coordinator._device.set_tag(
            pet_coordinator._device.tag, ModifyDeviceTag[call.data.get("action")]
        )
    )


@global_service(
    "set_pet_access_mode",
    schema=vol.Schema(
        {
            vol.Required("device_id"): str,
            vol.Required("pet_id"): str,
            vol.Required("profile"): vol.In([e.name for e in PetDeviceLocationProfile]),
        }
    ),
)
async def set_pet_access_mode(call) -> None:
    """Set pet access mode to indoor or outdoor"""
    device_coordinator = get_coordinator(call.hass, call.data.get("device_id"))
    pet_coordinator = get_coordinator(call.hass, call.data.get("pet_id"))
    await pet_coordinator.client.api(
        pet_coordinator._device.set_profile(
            device_coordinator._device.id,
            PetDeviceLocationProfile[call.data.get("profile")],
        )
    )


@global_service(
    "set_pet_position",
    schema=vol.Schema(
        {
            vol.Required("pet_id"): str,
            vol.Required("action"): vol.In([e.name for e in PetLocation]),
        }
    ),
)
async def set_pet_position(call) -> None:
    """Set pet position to inside or outside"""
    pet_coordinator = get_coordinator(call.hass, call.data.get("pet_id"))
    device: Pet = pet_coordinator._device
    await pet_coordinator.client.api(
        device.set_position(PetLocation[call.data.get("action")])
    )


def get_coordinator(hass, device_id):
    device_registry = async_get_device_registry(hass)
    device = device_registry.async_get(device_id)
    domain, device_id = next(iter(device.identifiers))

    coordinator = hass.data[domain][device.primary_config_entry]["coordinator"][
        "coordinator_dict"
    ][device_id]
    return coordinator
