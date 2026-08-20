"""Device configuration schemas for Sure Petcare devices."""

from typing import Any

from homeassistant.data_entry_flow import section
from homeassistant.helpers.selector import AreaSelector
from surepcio.enums import ProductId
from voluptuous import All, Optional, Range, Schema

from custom_components.surepcha.const import (
    LOCATION_INSIDE,
    LOCATION_OUTSIDE,
    MANUAL_PROPERTIES,
    POLLING_SPEED,
    SCAN_INTERVAL,
    TIMELINE_POLLING_SPEED,
)

area_fields = {
    Optional(LOCATION_INSIDE): AreaSelector(),
    Optional(LOCATION_OUTSIDE): AreaSelector(),
}

TIMELINE_CONFIG_SCHEMA = {
    Optional(TIMELINE_POLLING_SPEED, default=SCAN_INTERVAL): All(
        int, Range(min=5, max=86400)
    )
}

DEVICE_CONFIG_SCHEMAS: dict[ProductId, dict[Any, Any]] = {
    ProductId.DUAL_SCAN_CONNECT: {**area_fields},
    ProductId.DUAL_SCAN_PET_DOOR: {**area_fields},
    ProductId.PET_DOOR: {**area_fields},
}
OPTION_CONFIG_SCHEMAS = {Optional(MANUAL_PROPERTIES): section(Schema(area_fields))}

# Ensure every schema includes the polling speed range
for pid in ProductId:
    schema = DEVICE_CONFIG_SCHEMAS.setdefault(pid, {})
    schema[Optional(POLLING_SPEED, default=SCAN_INTERVAL)] = All(
        int, Range(min=5, max=86400)
    )
