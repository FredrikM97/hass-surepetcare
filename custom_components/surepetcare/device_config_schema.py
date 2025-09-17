"""TODO."""

from surepcio.enums import ProductId
from voluptuous import Optional

DEVICE_CONFIG_SCHEMAS = {
    ProductId.FEEDER_CONNECT: None,
    ProductId.DUAL_SCAN_CONNECT: {
        Optional("location_inside"): str,
        Optional("location_outside"): str,
    },
    ProductId.DUAL_SCAN_PET_DOOR: {
        Optional("location_inside"): str,
        Optional("location_outside"): str,
    },
    ProductId.HUB: None,
    ProductId.PET: None,
}
