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
from surepcio.devices import load_device_class
from surepcio.devices.entities import EntityInfo

FIXTURES = ["feeder_connect.json", "hub.json", "pet.json","dual_scan_connect.json"]


def create_device_from_fixture(fixture_data, timezone="Europe/Stockholm"):
    real_device = load_device_class(fixture_data["entity_info"]["product_id"])(
        fixture_data["entity_info"], timezone=timezone
    )
    #refresh_command = real_device.refresh()
    #parse_func = refresh_command.callback
    real_device.status=real_device.statusCls(**fixture_data['status'])
    real_device.control=real_device.controlCls(**fixture_data['control'])
    real_device.entity_info=EntityInfo(**fixture_data['entity_info'])
    #mock_response = {"data": fixture_data}
    #Status.construct(**fixture_data['status'])
    #return parse_func(mock_response)
    return real_device
"""
NOTE:
This works

parse_func({"data": {"movement": {"datapoints":[{
                    "from_": "2025-09-11T19:11:53+00:00",
                    "to": "2025-09-11T19:21:05+00:00",
                    "duration": 552,
                    "entry_device_id": 1334025,
                    "exit_device_id": 1334025,
                    "exit_movement_id": 0,
                    "entry_movement_id": 0
                }]}}})
or real_device.status.parse_obj(fixture_data['status'])           
"""

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
