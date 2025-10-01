from collections.abc import Callable
from dataclasses import dataclass
from surepcio.devices.device import SurePetCareBase
from enum import Enum
import re
from typing import Any, Optional
from custom_components.surepetcare.const import OPTION_DEVICES


def device_option(config: dict, device_id: int) -> dict:
    """Return the option dict for the device."""
    return config[OPTION_DEVICES].get(str(device_id), {})


def option_name(config: dict, device_id: int) -> str | None:
    """Return the name of the device option."""
    return device_option(config, device_id).get("name")


def option_product_id(config: dict, device_id: int) -> str | None:
    """Return the name of the device option."""
    return device_option(config, device_id).get("product_id")


def index_attr(seq, idx, attr, default=None):
    """Safely get attribute from item at idx in seq, or return default."""
    try:
        return getattr(seq[idx], attr, default)
    except (IndexError, TypeError, AttributeError):
        return default


def sum_attr(seq, attr, default=0):
    """Sum numeric attributes from a sequence, skipping non-numeric or missing."""
    return sum(
        v
        for v in (getattr(item, attr, default) for item in seq)
        if isinstance(v, (int, float))
    )


def serialize(obj):
    """Recursively convert objects/enums/lists/dicts to JSON-serializable types."""
    if isinstance(obj, Enum):
        return obj.name
    elif isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    elif isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple, set)):
        return [serialize(v) for v in obj]
    elif hasattr(obj, "__dict__"):
        return {
            k: serialize(v) for k, v in obj.__dict__.items() if not k.startswith("_")
        }
    else:
        return str(obj)


_LIST_INDEX_RE = re.compile(r"(\w+)\[(\d+)\]$")


def build_nested_dict(field_path, value):
    """
    Build a nested dict from a dotted path, supporting list indices like 'settings[1]'.
    """
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


def traverse_attrs(obj, *attrs):
    """Traverse attributes and return an iterator, or an empty iterator if missing or not a list."""
    for attr in attrs:
        obj = getattr(obj, attr, None)
        if obj is None:
            return None
    return obj


def ensure_list(obj, *attrs):
    """Ensure obj is a list and filter out None values."""
    obj = traverse_attrs(obj, *attrs)
    if obj is None:
        return []
    if isinstance(obj, list):
        return [x for x in obj if x is not None]
    if isinstance(obj, dict):
        return [v for v in obj.values() if v is not None]
    return [obj]


def list_attr(obj, *attrs):
    """Ensure the result of attribute traversal is a list or return an empty list."""
    obj = traverse_attrs(obj, *attrs)
    return obj if isinstance(obj, list) else []


def map_attr(seq, fn):
    """Apply fn to each item in seq and return the list."""
    return [fn(item) for item in seq]


def find_entity_id_by_name(entry_data: dict, name: str) -> str | None:
    """Find the entity ID by its name in entry_data['entities']."""
    return next(
        (
            entity_id
            for entity_id, entity in entry_data.get(OPTION_DEVICES, {}).items()
            if entity.get("name") == name
        ),
        None,
    )


@dataclass(frozen=True, slots=True)
class MethodField:
    """Field that uses provided functions or paths to get/set values."""

    get_fn: Optional[Callable[[SurePetCareBase, dict], Any]] = None
    set_fn: Optional[Callable[[SurePetCareBase, dict, Any], Any]] = None
    path: Optional[str] = None
    path_extra: Optional[str | dict] = None
    get_extra_fn: Optional[Callable[[SurePetCareBase, dict], Any]] = None

    def get(self, device: SurePetCareBase, config: dict) -> Any:
        """Get the value from the device."""
        if self.path:
            return get_by_path(device, self.path)
        if self.get_fn:
            return self.get_fn(device, config)
        raise NotImplementedError("No get_fn or path defined")

    def get_extra(self, device: SurePetCareBase, config: dict) -> Any:
        """Get extra attributes from the device."""
        if self.path_extra:
            return get_by_path(device, self.path_extra)
        if self.get_extra_fn:
            return self.get_extra_fn(device, config)
        raise NotImplementedError("No get_extra_fn or path defined")

    def set(self, device: SurePetCareBase, config: dict, value: Any) -> Any:
        """Set the value on the device."""
        if self.path:
            return device.set_control(**build_nested_dict(self.path, value))
        if self.set_fn:
            return self.set_fn(device, config, value)
        raise NotImplementedError("No set_fn or path defined")

    def __call__(self, device: SurePetCareBase, config: dict, value: Any) -> Any:
        """Call to set the value."""
        return self.set(device, config, value)


def resolve_select_option_value(desc, option: str) -> Any:
    """Resolve the correct value for a select option, handling Enum classes or plain lists."""
    if (
        desc.options is not None
        and isinstance(desc.options, type)
        and issubclass(desc.options, Enum)
    ):
        return getattr(desc.options, option)
    return option

def should_add_entity(
    description: Any,
    device_data: Any,
    config_options: dict,
) -> bool:
    """Return True if the entity should be added, False otherwise. Entities with entity_registry_enabled_default at registration and None as native_value won't show up in the UI"""
    get_fn = getattr(description.field, "get_fn", None)
    options = getattr(description, "options", None) or config_options or {}
    if get_fn is not None:
        value = get_fn(device_data, options)
        if value is None and getattr(description, "entity_registry_enabled_default") is False:
            return False
    return True