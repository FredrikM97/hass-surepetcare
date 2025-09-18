"""TODO."""

from surepcio.enums import ProductId
from voluptuous import Optional

from custom_components.surepetcare.const import LOCATION_INSIDE, LOCATION_OUTSIDE

# Add default values in case new ProductIds are added in the library
DEVICE_CONFIG_SCHEMAS = {pid: None for pid in ProductId}

DEVICE_CONFIG_SCHEMAS.update(
    {
        ProductId.DUAL_SCAN_CONNECT: {
            Optional(LOCATION_INSIDE): str,
            Optional(LOCATION_OUTSIDE): str,
        },
        ProductId.DUAL_SCAN_PET_DOOR: {
            Optional(LOCATION_INSIDE): str,
            Optional(LOCATION_OUTSIDE): str,
        },
    }
)
