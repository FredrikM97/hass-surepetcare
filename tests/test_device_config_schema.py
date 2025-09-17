import pytest
from custom_components.surepetcare import device_config_schema
from custom_components.surepetcare.device_config_schema import DEVICE_CONFIG_SCHEMAS
from surepcio.enums import ProductId
import voluptuous as vol


def test_dual_scan_pet_door_schema_valid():
    schema = DEVICE_CONFIG_SCHEMAS[ProductId.DUAL_SCAN_PET_DOOR]
    assert isinstance(schema, dict)
    valid = {"location_inside": "Hall", "location_outside": "Garden"}
    vol_schema = vol.Schema(schema, extra=vol.REMOVE_EXTRA)
    assert vol_schema(valid) == valid


def test_dual_scan_pet_door_schema_invalid():
    schema = DEVICE_CONFIG_SCHEMAS[ProductId.DUAL_SCAN_PET_DOOR]
    vol_schema = vol.Schema(schema, extra=vol.REMOVE_EXTRA)
    with pytest.raises(vol.Invalid):
        vol_schema({"location_inside": 123})
    with pytest.raises(vol.Invalid):
        vol_schema({"location_outside": 123123})


def test_dual_scan_pet_door_schema_missing_keys():
    schema = DEVICE_CONFIG_SCHEMAS[ProductId.DUAL_SCAN_PET_DOOR]
    vol_schema = vol.Schema(schema, extra=vol.REMOVE_EXTRA)
    assert vol_schema({}) == {}
    assert vol_schema({"location_inside": "Hall"}) == {"location_inside": "Hall"}
    assert vol_schema({"location_outside": "Garden"}) == {"location_outside": "Garden"}
    valid = {
        "location_inside": "Hall",
        "location_outside": "Garden",
        "extra": "ignored",
    }
    assert vol_schema(
        {k: valid[k] for k in ["location_inside", "location_outside"]}
    ) == {"location_inside": "Hall", "location_outside": "Garden"}


def test_dual_scan_pet_door_schema_extra_keys_ignored():
    schema = DEVICE_CONFIG_SCHEMAS[ProductId.DUAL_SCAN_PET_DOOR]
    vol_schema = vol.Schema(schema, extra=vol.REMOVE_EXTRA)
    valid = {
        "location_inside": "Hall",
        "location_outside": "Garden",
        "extra": "ignored",
    }
    result = vol_schema(valid)
    assert "extra" not in result
    assert result == {"location_inside": "Hall", "location_outside": "Garden"}


def test_dual_scan_pet_door_schema_type_validation():
    schema = DEVICE_CONFIG_SCHEMAS[ProductId.DUAL_SCAN_PET_DOOR]
    vol_schema = vol.Schema(schema, extra=vol.REMOVE_EXTRA)
    # Both values must be str
    valid = {"location_inside": "Room", "location_outside": "Yard"}
    assert vol_schema(valid) == valid
    # Wrong type for location_inside
    with pytest.raises(vol.Invalid):
        vol_schema({"location_inside": 123, "location_outside": "Yard"})
    # Wrong type for location_outside
    with pytest.raises(vol.Invalid):
        vol_schema({"location_inside": "Room", "location_outside": 456})


def test_device_config_schemas_structure():
    # Ensure DEVICE_CONFIG_SCHEMAS exists and is a dict
    assert isinstance(device_config_schema.DEVICE_CONFIG_SCHEMAS, dict)
    # Check all expected ProductIds are present
    for pid in [
        ProductId.FEEDER_CONNECT,
        ProductId.DUAL_SCAN_PET_DOOR,
        ProductId.HUB,
        ProductId.PET,
    ]:
        assert pid in device_config_schema.DEVICE_CONFIG_SCHEMAS


def test_dual_scan_pet_door_schema_keys():
    schema = device_config_schema.DEVICE_CONFIG_SCHEMAS[ProductId.DUAL_SCAN_PET_DOOR]
    assert isinstance(schema, dict)
    assert "location_inside" in [k.schema for k in schema.keys()]
    assert "location_outside" in [k.schema for k in schema.keys()]


def test_schema_type_and_structure():
    # All schemas should be dict or None
    for pid, schema in DEVICE_CONFIG_SCHEMAS.items():
        assert schema is None or isinstance(schema, dict)
        if isinstance(schema, dict):
            for k, v in schema.items():
                # Keys should be voluptuous marker objects
                assert hasattr(k, "schema")
                # Values should be type or callable
                assert callable(v) or isinstance(v, type)


def test_schema_keys_are_unique():
    # If schema is a dict, keys should be unique
    for pid, schema in DEVICE_CONFIG_SCHEMAS.items():
        if isinstance(schema, dict):
            keys = [k.schema for k in schema.keys()]
            assert len(keys) == len(set(keys))


def test_schemas_are_none():
    for pid in [ProductId.FEEDER_CONNECT, ProductId.HUB, ProductId.PET]:
        assert device_config_schema.DEVICE_CONFIG_SCHEMAS[pid] is None
