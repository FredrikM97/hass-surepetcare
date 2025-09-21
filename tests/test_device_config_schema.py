from custom_components.surepetcare.const import (
    LOCATION_INSIDE,
    LOCATION_OUTSIDE,
    POLLING_SPEED,
)
from custom_components.surepetcare.device_config_schema import DEVICE_CONFIG_SCHEMAS
from surepcio.enums import ProductId
import voluptuous as vol


def test_snapshot_schema(snapshot):
    assert DEVICE_CONFIG_SCHEMAS == snapshot


def test_snapshot_schema_with_example_values(snapshot):
    """
    For each schema, validate example config values and snapshot the results.
    """
    example_values = {
        ProductId.DUAL_SCAN_PET_DOOR: {
            LOCATION_INSIDE: "Hall",
            LOCATION_OUTSIDE: "Garden",
            POLLING_SPEED: 300,
        },
    }
    validated = {}
    for pid, schema in DEVICE_CONFIG_SCHEMAS.items():
        if schema is None:
            validated[pid] = None
        else:
            vol_schema = vol.Schema(schema, extra=vol.REMOVE_EXTRA)
            values = example_values.get(pid, {})
            validated[pid] = vol_schema(values)
    assert validated == snapshot


def test_snapshot_schema_with_missing_values(snapshot):
    """
    For each schema, validate empty config dict and snapshot the results.
    """
    validated = {}
    for pid, schema in DEVICE_CONFIG_SCHEMAS.items():
        if schema is None:
            validated[pid] = None
        else:
            vol_schema = vol.Schema(schema, extra=vol.REMOVE_EXTRA)
            validated[pid] = vol_schema({})
    assert validated == snapshot
