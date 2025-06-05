"""TODO."""

from voluptuous import Required

from surepetcare.enums import ProductId

DEVICE_CONFIG_SCHEMAS = {
    ProductId.FEEDER_CONNECT: {
        "schema": {
            Required("location_inside"): str,
            Required("location_outside"): str,
        },
    },
    ProductId.DUAL_SCAN_PET_DOOR: {
        "schema": {
            Required("location_inside"): str,
            Required("location_outside"): str,
        },
    },
    ProductId.HUB: {
        "schema": None,
    },
    ProductId.PET: {
        "schema": None,
    },
}
