"""TODO."""

from voluptuous import Required, Schema, Optional

from homeassistant.data_entry_flow import section
from surepetcare.enums import ProductId

DEVICE_CONFIG_SCHEMAS = {
    ProductId.FEEDER_CONNECT: {
        "schema": {Optional("location"): str},
        "title": "Feeder Connect Configuration",
    },
    ProductId.DUAL_SCAN_PET_DOOR: {
        "schema": {
            Required("location_inside"): str,
            Required("location_outside"): str,
        },
        "title": "Dual Scan Pet Door Configuration",
    },
    ProductId.HUB: {
        "schema": None,
        "title": "Hub Configuration",
    },
}
