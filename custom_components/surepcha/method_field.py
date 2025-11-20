"""MethodField classes for SurePetCare entities."""

from collections.abc import Callable
from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import Any, Optional

from surepcio.devices.device import SurePetCareBase

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

    def get(
        self, device: SurePetCareBase, entry_options: MappingProxyType[str, Any]
    ) -> Any:
        """Get the value from the device."""
        if self.path:
            return get_by_path(device, self.path)
        if self.get_fn:
            return self.get_fn(device, entry_options)
        raise NotImplementedError("No get_fn or path defined")

    def get_extra(
        self, device: SurePetCareBase, entry_options: MappingProxyType[str, Any]
    ) -> Any:
        """Get extra attributes from the device."""
        if self.path_extra:
            return get_by_path(device, self.path_extra)
        if self.get_extra_fn:
            return self.get_extra_fn(device, entry_options)
        raise NotImplementedError("No get_extra_fn or path defined")

    def set(
        self,
        device: SurePetCareBase,
        entry_options: MappingProxyType[str, Any],
        value: Any,
    ) -> Any:
        """Set the value on the device."""
        if self.path:
            return device.set_control(**build_nested_dict(self.path, value))
        if self.set_fn:
            return self.set_fn(device, entry_options, value)
        raise NotImplementedError("No set_fn or path defined")

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


@dataclass(frozen=True, slots=True)
class LockMethodField(MethodField):
    """MethodField for lock-like entities."""
