"""Device configuration schemas for Sure Petcare devices."""

from custom_components.surepcha.const import (
    LOCATION_INSIDE,
    LOCATION_OUTSIDE,
    MANUAL_PROPERTIES,
    POLLING_SPEED,
    SCAN_INTERVAL,
)
from homeassistant.helpers.selector import AreaSelector
from surepcio.enums import ProductId
from voluptuous import Optional, Range, All, Schema
from homeassistant.data_entry_flow import section

area_fields = {
    Optional(LOCATION_INSIDE): AreaSelector(),
    Optional(LOCATION_OUTSIDE): AreaSelector(),
}


DEVICE_CONFIG_SCHEMAS = {
    MANUAL_PROPERTIES: {Optional(MANUAL_PROPERTIES): section(Schema(area_fields))},
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
