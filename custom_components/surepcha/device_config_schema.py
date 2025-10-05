"""Device configuration schemas for Sure Petcare devices."""

from custom_components.surepcha.const import (
    LOCATION_INSIDE,
    LOCATION_OUTSIDE,
    POLLING_SPEED,
    SCAN_INTERVAL,
)
from surepcio.enums import ProductId
from voluptuous import Optional, Range, All

DEVICE_CONFIG_SCHEMAS = {
    ProductId.DUAL_SCAN_CONNECT: {
        Optional(LOCATION_INSIDE): str,
        Optional(LOCATION_OUTSIDE): str,
    },
    ProductId.DUAL_SCAN_PET_DOOR: {
        Optional(LOCATION_INSIDE): str,
        Optional(LOCATION_OUTSIDE): str,
    },
    ProductId.PET_DOOR: {
        Optional(LOCATION_INSIDE): str,
        Optional(LOCATION_OUTSIDE): str,
    },
}

# Ensure every schema includes the polling speed range
for pid in ProductId:
    schema = DEVICE_CONFIG_SCHEMAS.setdefault(pid, {})
    schema[Optional(POLLING_SPEED, default=SCAN_INTERVAL)] = All(
        int, Range(min=5, max=86400)
    )
