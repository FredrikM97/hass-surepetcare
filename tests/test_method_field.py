"""Tests for method_field module."""

from types import MappingProxyType
from unittest.mock import MagicMock

import pytest
from custom_components.surepcha.method_field import (
    BinarySensorMethodField,
    ButtonMethodField,
    LockMethodField,
    MethodField,
    SelectMethodField,
    SwitchMethodField,
    build_nested_dict,
    get_by_path,
)


class TestBuildNestedDict:
    """Tests for build_nested_dict helper function."""

    def test_simple_path(self):
        """Test building nested dict from simple path."""
        assert build_nested_dict("simple", "value") == {"simple": "value"}

    def test_two_level_path(self):
        """Test building nested dict from two-level path."""
        assert build_nested_dict("control.led_mode", 1) == {"control": {"led_mode": 1}}

    def test_three_level_path(self):
        """Test building nested dict from three-level path."""
        assert build_nested_dict("control.curfew.enabled", True) == {
            "control": {"curfew": {"enabled": True}}
        }

    def test_with_list_index(self):
        """Test building nested dict with list index notation."""
        result = build_nested_dict("control.bowls[0].target", 100)
        assert result == {"control": {"bowls": [{"target": 100}]}}

    def test_with_multiple_list_indices(self):
        """Test building nested dict with multiple list indices."""
        result = build_nested_dict("settings[1].items[2].value", "test")
        assert result == {
            "settings": [None, {"items": [None, None, {"value": "test"}]}]
        }


class TestGetByPath:
    """Tests for get_by_path helper function."""

    def test_simple_attribute(self):
        """Test getting simple attribute."""
        device = MagicMock()
        device.value = 42
        assert get_by_path(device, "value") == 42

    def test_nested_attributes(self):
        """Test getting nested attributes."""
        device = MagicMock()
        device.status.led_mode = 1
        assert get_by_path(device, "status.led_mode") == 1

    def test_deeply_nested_attributes(self):
        """Test getting deeply nested attributes."""
        device = MagicMock()
        device.status.curfew.enabled = True
        assert get_by_path(device, "status.curfew.enabled") is True

    def test_list_index_access(self):
        """Test accessing list elements by index."""
        device = MagicMock()
        device.bowls = [{"target": 100}, {"target": 200}]
        assert get_by_path(device, "bowls[0].target") == 100
        assert get_by_path(device, "bowls[1].target") == 200

    def test_none_device(self):
        """Test handling None device."""
        assert get_by_path(None, "status.value") is None

    def test_none_intermediate_value(self):
        """Test handling None intermediate value."""
        device = MagicMock()
        device.status = None
        assert get_by_path(device, "status.value") is None

    def test_missing_attribute(self):
        """Test handling missing attribute."""
        device = MagicMock()
        device.status = MagicMock(spec=[])  # status exists but has no attributes
        assert get_by_path(device, "status.nonexistent") is None

    def test_index_out_of_range(self):
        """Test handling index out of range."""
        device = MagicMock()
        device.items = [1, 2, 3]
        assert get_by_path(device, "items[10]") is None

    def test_dict_input(self):
        """Test getting multiple paths with dict input."""
        device = MagicMock()
        device.status.temp = 20
        device.status.humidity = 60
        result = get_by_path(device, {"t": "status.temp", "h": "status.humidity"})
        assert result == {"t": 20, "h": 60}

    def test_dict_access(self):
        """Test accessing dict keys."""
        device = {"status": {"led_mode": 1}}
        assert get_by_path(device, "status.led_mode") == 1

    def test_dict_with_list_index(self):
        """Test accessing dict with list index notation."""
        device = {"bowls": [{"target": 100}, {"target": 200}]}
        assert get_by_path(device, "bowls[0].target") == 100
        assert get_by_path(device, "bowls[1].target") == 200

    def test_dict_with_missing_list_key(self):
        """Test handling missing key in dict with list notation."""
        device = {"status": {"value": 1}}
        assert get_by_path(device, "bowls[0].target") is None


class TestMethodField:
    """Tests for MethodField base class."""

    def test_with_path_get(self):
        """Test MethodField.get with path parameter."""
        device = MagicMock()
        device.status.led_mode = 1

        field = MethodField(path="status.led_mode")
        options = MappingProxyType({})

        assert field.get(device, options) == 1

    def test_with_path_set(self):
        """Test MethodField.set with path parameter."""
        device = MagicMock()
        device.set_control = MagicMock(return_value=None)

        field = MethodField(path="control.led_mode")
        options = MappingProxyType({})

        field.set(device, options, 2)
        device.set_control.assert_called_once_with(control={"led_mode": 2})

    def test_with_nested_path_set(self):
        """Test MethodField.set with nested path."""
        device = MagicMock()
        device.set_control = MagicMock(return_value=None)

        field = MethodField(path="control.curfew.enabled")
        options = MappingProxyType({})

        field.set(device, options, True)
        device.set_control.assert_called_once_with(
            control={"curfew": {"enabled": True}}
        )

    def test_with_custom_get_fn(self):
        """Test MethodField with custom get function."""
        device = MagicMock()
        device.custom_value = 42

        field = MethodField(get_fn=lambda d, r: d.custom_value * 2)
        options = MappingProxyType({})

        assert field.get(device, options) == 84

    def test_with_custom_set_fn(self):
        """Test MethodField with custom set function."""
        device = MagicMock()
        device.custom_set = MagicMock()

        field = MethodField(
            get_fn=lambda d, r: None, set_fn=lambda d, r, v: d.custom_set(v * 2)
        )
        options = MappingProxyType({})

        field.set(device, options, 10)
        device.custom_set.assert_called_once_with(20)

    def test_path_with_custom_set_fn_override(self):
        """Test that custom set_fn overrides path default."""
        device = MagicMock()
        device.status.value = 10
        device.custom_set = MagicMock()

        field = MethodField(path="status.value", set_fn=lambda d, r, v: d.custom_set(v))
        options = MappingProxyType({})

        # Get uses path
        assert field.get(device, options) == 10

        # Set uses custom function
        field.set(device, options, 20)
        device.custom_set.assert_called_once_with(20)

    def test_path_with_custom_get_fn_override(self):
        """Test that custom get_fn overrides path default."""
        device = MagicMock()
        device.status.value = 10
        device.set_control = MagicMock()

        field = MethodField(path="status.value", get_fn=lambda d, r: d.status.value * 3)
        options = MappingProxyType({})

        # Get uses custom function
        assert field.get(device, options) == 30

        # Set uses path default
        field.set(device, options, 20)
        device.set_control.assert_called_once()

    def test_get_extra_with_path_extra(self):
        """Test MethodField.get_extra with path_extra."""
        device = MagicMock()
        device.status.extra_data = {"key": "value"}

        field = MethodField(path="status.value", path_extra="status.extra_data")
        options = MappingProxyType({})

        assert field.get_extra(device, options) == {"key": "value"}

    def test_get_extra_with_get_extra_fn(self):
        """Test MethodField.get_extra with custom function."""
        device = MagicMock()

        field = MethodField(
            path="status.value",
            get_extra_fn=lambda d, r: {"custom": "data", "count": 42},
        )
        options = MappingProxyType({})

        assert field.get_extra(device, options) == {"custom": "data", "count": 42}

    def test_get_extra_with_dict_path_extra(self):
        """Test MethodField.get_extra with dict path_extra."""
        device = MagicMock()
        device.status.temp = 20
        device.status.humidity = 60

        field = MethodField(
            path="status.value",
            path_extra={"temperature": "status.temp", "humidity": "status.humidity"},
        )
        options = MappingProxyType({})

        assert field.get_extra(device, options) == {"temperature": 20, "humidity": 60}

    def test_no_get_fn_raises(self):
        """Test MethodField raises when no get_fn is defined."""
        field = MethodField()
        options = MappingProxyType({})
        device = MagicMock()

        with pytest.raises(NotImplementedError, match="No get_fn or path defined"):
            field.get(device, options)

    def test_no_set_fn_raises(self):
        """Test MethodField raises when no set_fn is defined."""
        field = MethodField(get_fn=lambda d, r: None)
        options = MappingProxyType({})
        device = MagicMock()

        with pytest.raises(NotImplementedError, match="No set_fn or path defined"):
            field.set(device, options, None)

    def test_no_get_extra_fn_raises(self):
        """Test MethodField raises when no get_extra_fn or path_extra is defined."""
        field = MethodField(path="status.value")
        options = MappingProxyType({})
        device = MagicMock()

        with pytest.raises(NotImplementedError, match="No get_extra_fn or path_extra"):
            field.get_extra(device, options)

    def test_call_delegates_to_set(self):
        """Test that __call__ delegates to set method."""
        device = MagicMock()
        device.set_control = MagicMock()

        field = MethodField(path="control.value")
        options = MappingProxyType({})

        field(device, options, 42)
        device.set_control.assert_called_once_with(control={"value": 42})


class TestButtonMethodField:
    """Tests for ButtonMethodField."""

    def test_maps_true_to_on_value(self):
        """Test ButtonMethodField maps True to on value."""
        device = MagicMock()
        device.set_control = MagicMock()

        field = ButtonMethodField(path="control.pairing_mode", on="PAIRING")
        options = MappingProxyType({})

        field.set(device, options, True)
        device.set_control.assert_called_with(control={"pairing_mode": "PAIRING"})

    def test_passthrough_non_true_values(self):
        """Test ButtonMethodField passes through non-True values."""
        device = MagicMock()
        device.set_control = MagicMock()

        field = ButtonMethodField(path="control.value", on="ON")
        options = MappingProxyType({})

        field.set(device, options, "CUSTOM")
        device.set_control.assert_called_with(control={"value": "CUSTOM"})

    def test_default_on_value(self):
        """Test ButtonMethodField with default on value (True)."""
        device = MagicMock()
        device.set_control = MagicMock()

        field = ButtonMethodField(path="control.button")
        options = MappingProxyType({})

        field.set(device, options, True)
        device.set_control.assert_called_with(control={"button": True})


class TestSelectMethodField:
    """Tests for SelectMethodField."""

    def test_with_path_works_normally(self):
        """Test SelectMethodField with path works like base MethodField."""
        device = MagicMock()
        device.status.mode = "AUTO"

        field = SelectMethodField(path="status.mode")
        options = MappingProxyType({})

        assert field.get(device, options) == "AUTO"

    def test_with_only_options_fn_returns_none(self):
        """Test SelectMethodField with only options_fn returns None."""
        device = MagicMock()

        field = SelectMethodField(options_fn=lambda d, r: ["opt1", "opt2", "opt3"])
        options = MappingProxyType({})

        # When only options_fn is set, get returns None
        assert field.get(device, options) is None

    def test_with_path_and_options_fn(self):
        """Test SelectMethodField with both path and options_fn."""
        device = MagicMock()
        device.status.mode = "AUTO"

        field = SelectMethodField(
            path="status.mode", options_fn=lambda d, r: ["AUTO", "MANUAL"]
        )
        options = MappingProxyType({})

        # Get still works with path
        assert field.get(device, options) == "AUTO"

    def test_set_works_normally(self):
        """Test SelectMethodField.set works like base MethodField."""
        device = MagicMock()
        device.set_control = MagicMock()

        field = SelectMethodField(path="control.mode")
        options = MappingProxyType({})

        field.set(device, options, "MANUAL")
        device.set_control.assert_called_with(control={"mode": "MANUAL"})


class TestSwitchMethodField:
    """Tests for SwitchMethodField."""

    def test_maps_true_to_on_value(self):
        """Test SwitchMethodField maps True to on value."""
        device = MagicMock()
        device.set_control = MagicMock()

        field = SwitchMethodField(path="control.enabled", on="ENABLED", off="DISABLED")
        options = MappingProxyType({})

        field.set(device, options, True)
        device.set_control.assert_called_with(control={"enabled": "ENABLED"})

    def test_maps_false_to_off_value(self):
        """Test SwitchMethodField maps False to off value."""
        device = MagicMock()
        device.set_control = MagicMock()

        field = SwitchMethodField(path="control.enabled", on="ENABLED", off="DISABLED")
        options = MappingProxyType({})

        field.set(device, options, False)
        device.set_control.assert_called_with(control={"enabled": "DISABLED"})

    def test_raises_on_none_value(self):
        """Test SwitchMethodField raises ValueError for None."""
        device = MagicMock()
        field = SwitchMethodField(path="control.enabled")
        options = MappingProxyType({})

        with pytest.raises(ValueError, match="Cannot set switch to None"):
            field.set(device, options, None)

    def test_passthrough_non_boolean_values(self):
        """Test SwitchMethodField passes through non-boolean values."""
        device = MagicMock()
        device.set_control = MagicMock()

        field = SwitchMethodField(path="control.value")
        options = MappingProxyType({})

        field.set(device, options, "CUSTOM")
        device.set_control.assert_called_with(control={"value": "CUSTOM"})

    def test_default_on_off_values(self):
        """Test SwitchMethodField with default on/off values."""
        device = MagicMock()
        device.set_control = MagicMock()

        field = SwitchMethodField(path="control.switch")
        options = MappingProxyType({})

        field.set(device, options, True)
        device.set_control.assert_called_with(control={"switch": True})

        field.set(device, options, False)
        device.set_control.assert_called_with(control={"switch": False})


class TestLockMethodField:
    """Tests for LockMethodField."""

    def test_inherits_from_method_field(self):
        """Test LockMethodField inherits from MethodField."""
        assert issubclass(LockMethodField, MethodField)

    def test_basic_functionality(self):
        """Test LockMethodField basic get/set functionality."""
        device = MagicMock()
        device.control.locked = True
        device.set_control = MagicMock()

        field = LockMethodField(path="control.locked")
        options = MappingProxyType({})

        # Get works
        assert field.get(device, options) is True

        # Set works
        field.set(device, options, False)
        device.set_control.assert_called_with(control={"locked": False})


class TestBinarySensorMethodField:
    """Tests for BinarySensorMethodField."""

    def test_maps_on_value_to_true(self):
        """Test BinarySensorMethodField maps on value to True."""
        device = MagicMock()
        device.status.position = "INSIDE"

        field = BinarySensorMethodField(
            path="status.position", on="INSIDE", off="OUTSIDE"
        )
        options = MappingProxyType({})

        assert field.get(device, options) is True

    def test_maps_off_value_to_false(self):
        """Test BinarySensorMethodField maps off value to False."""
        device = MagicMock()
        device.status.position = "OUTSIDE"

        field = BinarySensorMethodField(
            path="status.position", on="INSIDE", off="OUTSIDE"
        )
        options = MappingProxyType({})

        assert field.get(device, options) is False

    def test_maps_unknown_value_to_none(self):
        """Test BinarySensorMethodField maps unknown values to None."""
        device = MagicMock()
        device.status.position = "UNKNOWN"

        field = BinarySensorMethodField(
            path="status.position", on="INSIDE", off="OUTSIDE"
        )
        options = MappingProxyType({})

        assert field.get(device, options) is None

    def test_handles_none_value(self):
        """Test BinarySensorMethodField handles None value."""
        device = MagicMock()
        device.status.position = None

        field = BinarySensorMethodField(
            path="status.position", on="INSIDE", off="OUTSIDE"
        )
        options = MappingProxyType({})

        assert field.get(device, options) is None

    def test_default_on_off_values(self):
        """Test BinarySensorMethodField with default on/off values."""
        device = MagicMock()
        device.status.active = True

        field = BinarySensorMethodField(path="status.active")
        options = MappingProxyType({})

        assert field.get(device, options) is True

        device.status.active = False
        assert field.get(device, options) is False

    def test_with_custom_get_fn(self):
        """Test BinarySensorMethodField with custom get_fn."""
        device = MagicMock()
        device.status.activity = MagicMock()
        device.status.activity.where = "INSIDE"

        field = BinarySensorMethodField(
            get_fn=lambda d, r: getattr(
                getattr(d.status, "activity", None), "where", None
            ),
            on="INSIDE",
            off="OUTSIDE",
        )
        options = MappingProxyType({})

        assert field.get(device, options) is True

        device.status.activity.where = "OUTSIDE"
        assert field.get(device, options) is False

        device.status.activity = None
        assert field.get(device, options) is None
