"""Device configuration schemas for Sure Petcare devices."""

from typing import Any

from homeassistant.data_entry_flow import section
from homeassistant.helpers.selector import AreaSelector
from surepcio import get_device_features
from voluptuous import All, Optional, Range, Schema

from custom_components.surepcha.const import (
    LOCATION_INSIDE,
    LOCATION_OUTSIDE,
    MANUAL_PROPERTIES,
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

OPTION_CONFIG_SCHEMAS = {Optional(MANUAL_PROPERTIES): section(Schema(area_fields))}


def device_config_schema(product_id: int | str | None) -> dict[Any, Any]:
    """Offer scheduling and the optional label controls advertised by PS."""
    schema: dict[Any, Any] = {}
    if "location_labels" in get_device_features(product_id):
        schema.update(area_fields)
    return schema
