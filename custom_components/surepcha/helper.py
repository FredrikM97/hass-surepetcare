import logging
from types import MappingProxyType
from pydantic import BaseModel
from enum import Enum
from typing import Any
from surepcio.command import Command
from surepcio.devices.device import SurePetCareBase
from custom_components.surepcha.const import NAME, OPTION_DEVICES, PRODUCT_ID

logger = logging.getLogger(__name__)


def device_option(entry_options: MappingProxyType[str, Any], device_id: int) -> dict:
    """Return the option dict for the device."""
    return entry_options[OPTION_DEVICES].get(str(device_id), {})


def option_name(
    entry_options: MappingProxyType[str, Any], device_id: int
) -> str | None:
    """Return the name of the device option."""
    return device_option(entry_options, device_id).get(NAME)


def option_product_id(
    entry_options: MappingProxyType[str, Any], device_id: int
) -> str | None:
    """Return the name of the device option."""
    return device_option(entry_options, device_id).get(PRODUCT_ID)


def index_attr(seq, idx, attr=None, default=None):
    """Safely get attribute from item at idx in seq, or return default."""
    try:
        if attr is None:
            return seq[idx]
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


def avg_attr(items, attr):
    vals = [
        getattr(item, attr, None)
        for item in items
        if getattr(item, attr, None) is not None
    ]
    return sum(vals) / len(vals) if vals else None


def abs_sum_attr(obj, attr):
    values = getattr(obj, attr, [])
    return abs(sum(values)) if values else None


def stringify(value: Any) -> str | None:
    """Convert value to string, handling None."""
    return str(value) if value is not None else None


def serialize(obj):
    """Recursively convert objects/enums/lists/dicts to JSON-serializable types, including properties, skipping functions, and using model_dump for Pydantic models."""
    if isinstance(obj, Enum):
        return obj.name
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    if isinstance(obj, BaseModel):
        if hasattr(obj, "model_dump"):
            return serialize(obj.model_dump())
        return serialize(obj.dict())
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [serialize(v) for v in obj]
    if hasattr(obj, "__dict__"):
        result = {
            k: serialize(v) for k, v in obj.__dict__.items() if not k.startswith("_")
        }
        props = [
            attr
            for attr in dir(obj)
            if not attr.startswith("_")
            and attr not in result
            and not callable(getattr(obj, attr, None))
        ]
        if props:
            result.update({attr: serialize(getattr(obj, attr, None)) for attr in props})
        return result
    return str(obj)


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


def find_entity_id_by_name(
    entry_options: MappingProxyType[str, Any], name: str
) -> str | None:
    """Find the entity ID by its name in entry_data['entities']."""
    return next(
        (
            entity_id
            for entity_id, entity in entry_options.get(OPTION_DEVICES, {}).items()
            if entity.get(NAME) == name
        ),
        None,
    )


def ensure_command_device(
    command: Command | list[Command] | Any,
    device: SurePetCareBase,
) -> Command | list[Command] | Any:
    """Attach a fallback device to commands missing refresh context."""
    if isinstance(command, list):
        return [ensure_command_device(item, device) for item in command]

    if isinstance(command, Command) and command.device is None:
        command.device = device

    return command
