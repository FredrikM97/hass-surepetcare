# Shared test helpers for config_flow tests
from custom_components.surepetcare.const import (
    COORDINATOR,
    COORDINATOR_DICT,
    DOMAIN,
    KEY_API,
)
from custom_components.surepetcare.coordinator import (
    SurePetCareDeviceDataUpdateCoordinator,
)
from surepetcare.devices import load_device_class

FIXTURES = [
    "feeder_connect.json",
    "hub.json",
    "pet.json"
]

def create_device_from_fixture(fixture_data):
    real_device = load_device_class(fixture_data["entity_info"]["product_id"])(
        fixture_data["entity_info"]
    )
    refresh_command = real_device.refresh()
    parse_func = refresh_command.callback
    mock_response = {"data": fixture_data}
    return parse_func(mock_response)


def setup_coordinator(hass, config_entry, device):
    coordinator = SurePetCareDeviceDataUpdateCoordinator(
        hass=hass,
        config_entry=config_entry,
        client=None,
        device=device,
    )
    coordinator.data = device
    hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = {
        COORDINATOR: {KEY_API: None, COORDINATOR_DICT: {str(device.id): coordinator}}
    }
    return coordinator


def extract_sensor_outputs(async_add_entities):
    sensor_outputs = {}
    for call in async_add_entities.call_args_list:
        for entity in call[0][0]:
            if hasattr(entity, "is_on"):
                value = entity.is_on
            else:
                value = entity.native_value
            sensor_outputs[entity.unique_id] = {
                "value": value,
                "extra_attributes": getattr(entity, "extra_state_attributes", {}),
                "device_class": getattr(entity, "device_class", None),
                "unit": getattr(entity, "native_unit_of_measurement", None),
            }
    return sensor_outputs
