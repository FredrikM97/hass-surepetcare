"""TODO."""

from surepcio.enums import ProductId
from voluptuous import Optional

# Add default values in case new ProductIds are added in the library
DEVICE_CONFIG_SCHEMAS = {pid: None for pid in ProductId}

DEVICE_CONFIG_SCHEMAS.update(
    {
        ProductId.DUAL_SCAN_CONNECT: {
            Optional("location_inside"): str,
            Optional("location_outside"): str,
        },
        ProductId.DUAL_SCAN_PET_DOOR: {
            Optional("location_inside"): str,
            Optional("location_outside"): str,
        },
    }
)
