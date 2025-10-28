"""Device configuration schemas for Sure Petcare devices."""

from custom_components.surepcha.const import (
    LOCATION_INSIDE,
    LOCATION_OUTSIDE,
    MANUAL_PROPERTIES,
    POLLING_SPEED,
    SCAN_INTERVAL,
)
from surepcio.enums import ProductId
from voluptuous import Optional, Range, All

area_fields = {
    Optional(
        LOCATION_INSIDE
    ): str,  # This is not really string but a more complex structure defined in runtime.
    Optional(LOCATION_OUTSIDE): str,
}


DEVICE_CONFIG_SCHEMAS = {
    MANUAL_PROPERTIES: {**area_fields},
    ProductId.DUAL_SCAN_CONNECT: {**area_fields},
    ProductId.DUAL_SCAN_PET_DOOR: {**area_fields},
    ProductId.PET_DOOR: {**area_fields},
}

# Ensure every schema includes the polling speed range
for pid in ProductId:
    schema = DEVICE_CONFIG_SCHEMAS.setdefault(pid, {})
    schema[Optional(POLLING_SPEED, default=SCAN_INTERVAL)] = All(
        int, Range(min=5, max=86400)
    )
