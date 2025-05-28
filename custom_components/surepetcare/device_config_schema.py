"""TODO."""

from voluptuous import Required

from surepetcare.enums import ProductId

DEVICE_CONFIG_SCHEMAS = {
    ProductId.FEEDER_CONNECT: {
        "schema": None,
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
