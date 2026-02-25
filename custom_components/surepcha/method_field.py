"""MethodField classes for SurePetCare entities."""

from collections.abc import Callable
from dataclasses import dataclass
import logging
import re
from types import MappingProxyType
from typing import Any, Optional
from homeassistant.components.lock.const import LockState

from surepcio.devices.device import SurePetCareBase

logger = logging.getLogger(__name__)

_LIST_INDEX_RE = re.compile(r"(\w+)\[(\d+)\]$")


def build_nested_dict(field_path, value):
    """Build a nested dict from a dotted path, supporting list indices like 'settings[1]'."""
    parts = field_path.split(".")
    result = value
    for part in reversed(parts):
        match = _LIST_INDEX_RE.match(part)
        if match:
            key, idx = match.groups()
            idx = int(idx)
            arr = [None for _ in range(idx + 1)]
            arr[idx] = result
            result = {key: arr}
        else:
            result = {part: result}
    return result


def get_by_path(obj, path):
    """Traverse a dotted path with optional list indices (e.g. 'control.bowls.settings[1].target').
    Works for both dicts and objects. If path is a dict, returns a dict of results.
    """
    if isinstance(path, dict):
        return {k: get_by_path(obj, v) for k, v in path.items()}
    for part in path.split("."):
        if obj is None:
            return None
        match = _LIST_INDEX_RE.match(part)
        if match:
            key, idx = match.groups()
            if isinstance(obj, dict):
                obj = obj.get(key)
            else:
                obj = getattr(obj, key, None)
            if obj is None:
                return None
            try:
                obj = obj[int(idx)]
            except (IndexError, ValueError, TypeError, KeyError):
                return None
        else:
            if isinstance(obj, dict):
                obj = obj.get(part)
            else:
                obj = getattr(obj, part, None)
    return obj


@dataclass(frozen=True, slots=True)
class MethodField:
    """Field that uses provided functions or paths to get/set values."""

    get_fn: Optional[Callable[[SurePetCareBase, MappingProxyType[str, Any]], Any]] = (
        None
    )
    set_fn: Optional[
        Callable[[SurePetCareBase, MappingProxyType[str, Any], Any], Any]
    ] = None
    path: Optional[str] = None
    path_extra: Optional[str | dict] = None
    get_extra_fn: Optional[
        Callable[[SurePetCareBase, MappingProxyType[str, Any]], Any]
    ] = None
    entity_picture: Optional[str] = None

    def __post_init__(self):
        """Set default get_fn and set_fn if not provided but path is."""
        if self.path:
            # Only set get_fn default if not explicitly provided
            if self.get_fn is None:
                object.__setattr__(
                    self, "get_fn", lambda device, r: get_by_path(device, self.path)
                )
            # Only set set_fn default if not explicitly provided
            if self.set_fn is None:
                object.__setattr__(
                    self,
                    "set_fn",
                    lambda device, r, value: device.set_control(
                        **build_nested_dict(self.path, value)
                    ),
                )

        # Set get_extra_fn from path_extra if not explicitly provided
        if self.path_extra and self.get_extra_fn is None:
            object.__setattr__(
                self,
                "get_extra_fn",
                lambda device, r: get_by_path(device, self.path_extra),
            )

    def get(
        self, device: SurePetCareBase, entry_options: MappingProxyType[str, Any]
    ) -> Any:
        """Get the value from the device."""
        if self.get_fn:
            value = self.get_fn(device, entry_options)
            logger.debug(
                "MethodField.get: device_id: %s, devicepath=%s, value=%s",
                device.id,
                self.path or "<custom_fn>",
                value,
            )
            return value
        raise NotImplementedError("No get_fn or path defined")

    def set(
        self,
        device: SurePetCareBase,
        entry_options: MappingProxyType[str, Any],
        value: Any,
    ) -> Any:
        """Set the value on the device."""
        if self.set_fn:
            logger.debug(
                "MethodField.set: device_id: %s, path=%s, value=%s",
                device.id,
                self.path or "<custom_fn>",
                value,
            )
            return self.set_fn(device, entry_options, value)
        raise NotImplementedError("No set_fn or path defined")

    def get_extra(
        self, device: SurePetCareBase, entry_options: MappingProxyType[str, Any]
    ) -> Any:
        """Get extra attributes from the device."""
        if self.get_extra_fn:
            return self.get_extra_fn(device, entry_options)
        raise NotImplementedError("No get_extra_fn or path_extra defined")

    def get_entity_picture(self, device) -> Optional[str]:
        """Return the entity picture URL if set."""
        return get_by_path(device, self.entity_picture) if self.entity_picture else None

    def __call__(
        self,
        device: SurePetCareBase,
        entry_options: MappingProxyType[str, Any],
        value: Any,
    ) -> Any:
        """Call to set the value."""
        return self.set(device, entry_options, value)


@dataclass(frozen=True, slots=True)
class ButtonMethodField(MethodField):
    """MethodField for button-like entities, supporting on mapping."""

    on: Any = True

    def set(
        self, device: object, entry_options: MappingProxyType[str, Any], value: Any
    ) -> Any:
        if value is True and self.on:
            value = self.on
        return MethodField.set(self, device, entry_options, value)


@dataclass(frozen=True, slots=True)
class SelectMethodField(MethodField):
    """MethodField for select-like entities, supporting options function."""

    options_fn: Callable | None = None

    def get(self, device: object, entry_options: MappingProxyType[str, Any]) -> Any:
        if self.get_fn is None and self.path is None and self.options_fn is not None:
            # Bonky solution but this might return multiple values and therefore we just return None.
            return None
        return MethodField.get(self, device, entry_options)

    def set(
        self, device: object, entry_options: MappingProxyType[str, Any], value: Any
    ) -> Any:
        return MethodField.set(self, device, entry_options, value)


@dataclass(frozen=True, slots=True)
class SwitchMethodField(MethodField):
    """MethodField for switch-like entities, supporting on/off mapping."""

    on: Any = True
    off: Any = False

    def set(
        self, device: object, entry_options: MappingProxyType[str, Any], value: Any
    ) -> Any:
        # Map True/False to on/off, otherwise pass value as-is
        if value is True:
            value = self.on
        elif value is False:
            value = self.off
        elif value is None:
            raise ValueError("Cannot set switch to None for %s", device)
        return MethodField.set(self, device, entry_options, value)


@dataclass(frozen=True)
class LockMethodField(MethodField):
    """MethodField for lock-like entities."""

    states: dict[LockState, Any] | None = None
    _reverse_states: dict[Any, LockState] | None = None

    def __post_init__(self):
        """Create reverse mapping for efficient lookups."""
        # Call parent's __post_init__ to set up get_fn/set_fn from path
        MethodField.__post_init__(self)
        if not self.states:
            raise ValueError("LockMethodField requires 'states' to be provided")
        # Create reverse mapping: FlapLocking -> LockState
        object.__setattr__(
            self, "_reverse_states", {v: k for k, v in self.states.items()}
        )

    def get(self, device: object, entry_options: MappingProxyType[str, Any]) -> Any:
        """Get the value from the device and map it to LockState."""
        raw_value = MethodField.get(self, device, entry_options)
        # _reverse_states is guaranteed to be set in __post_init__
        assert self._reverse_states is not None
        return self._reverse_states.get(raw_value)

    def set(
        self, device: object, entry_options: MappingProxyType[str, Any], value: Any
    ) -> Any:
        """Set the value on the device by mapping LockState to the corresponding value."""
        # states is guaranteed to be set (checked in __post_init__)
        assert self.states is not None
        if value not in self.states:
            raise ValueError(f"Unknown lock state: {value} for {device}")
        mapped_value = self.states[value]
        return MethodField.set(self, device, entry_options, mapped_value)


@dataclass(frozen=True, slots=True)
class BinarySensorMethodField(MethodField):
    """MethodField for binary sensor entities, supporting on/off value mapping."""

    on: Any = True
    off: Any = False

    def get(self, device: object, entry_options: MappingProxyType[str, Any]) -> Any:
        """Get the value and map it to True/False based on on/off values."""
        # Get the raw value using parent's get method
        raw_value = MethodField.get(self, device, entry_options)

        # Map the value to boolean
        if raw_value == self.on:
            return True
        elif raw_value == self.off:
            return False
        else:
            # Return None for unknown values
            return None
