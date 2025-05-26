from voluptuous import Schema, Required
from surepetcare.enums import ProductId
from homeassistant.data_entry_flow import section

DEVICE_CONFIG_SCHEMAS = {
    ProductId.FEEDER_CONNECT: {
        "schema": Schema({
            Required("location"): str,
        }),
        "title": "Feeder Connect Configuration",
    },
    ProductId.DUAL_SCAN_PET_DOOR: {
        "schema": section(Schema({
            Required("location_inside"): str,
            Required("location_outside"): str,
        })),
        "title": "Dual Scan Pet Door Configuration",
    },
}

