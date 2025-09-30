from collections.abc import Callable
from enum import Enum
import re
from typing import Any
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
        v for v in (getattr(item, attr, default) for item in seq)
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

def build_nested_dict_v1(field_path: str, value: float | int | str) -> dict:
    """Build a nested dict/list structure from a dotted field path, handling list indices.
    Skips the top-level 'control' key.
    """
    parts = field_path.split(".")
    if parts and parts[0] == "control":
        parts = parts[1:]
    result: object = value
    for part in reversed(parts):
        if part.isdigit():
            idx = int(part)
            lst: list = []
            while len(lst) <= idx:
                lst.append(None)
            lst[idx] = result
            result = lst
        else:
            result = {part: result}
    return result if isinstance(result, dict) else {parts[0]: result}



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
            arr = [{}] * idx + [result]  # Only create up to idx, fill with {} before
            result = {key: arr}
        else:
            result = {part: result}
    return result

def get_by_path(obj, path):
    """Traverse a dotted path with optional list indices (e.g. 'control.bowls.settings[1].target')."""
    for part in path.split('.'):
        if obj is None:
            return None
        match = _LIST_INDEX_RE.match(part)
        if match:
            key, idx = match.groups()
            obj = getattr(obj, key, None)
            if obj is None:
                return None
            try:
                obj = obj[int(idx)]
            except (IndexError, ValueError, TypeError):
                return None
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

def make_command(fn: Callable[..., Any], *preset_args, **preset_kwargs) -> Callable:
    """
    Return a command function that calls `fn` with preset and runtime arguments.
    Useful for Home Assistant select/switch command patterns.
    """
    def command(*args, **kwargs):
        return fn(*preset_args, *args, **preset_kwargs, **kwargs)
    return command

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

