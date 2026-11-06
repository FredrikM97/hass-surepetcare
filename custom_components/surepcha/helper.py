"""Shared serialization for Home Assistant states and diagnostics."""

from collections.abc import Iterator
from contextlib import contextmanager
from enum import Enum
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from pydantic import BaseModel
from surepcio.security.exceptions import ApiError, AuthenticationError

from .const import DOMAIN, OPTION_DEVICES


@contextmanager
def translate_auth_errors(
    message: str = "Sure Petcare authentication expired",
) -> Iterator[None]:
    """Translate credential failures consistently at the HA boundary."""
    try:
        yield
    except (AuthenticationError, ApiError) as exc:
        if isinstance(exc, AuthenticationError) or exc.status == 401:
            raise ConfigEntryAuthFailed(message) from exc
        raise


def get_device_options(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, dict[str, Any]]:
    """Include cross-entry devices, with this entry's overrides taking precedence."""
    devices = {}
    for configured_entry in hass.config_entries.async_entries(DOMAIN):
        devices.update(configured_entry.options.get(OPTION_DEVICES, {}))
    devices.update(entry.options.get(OPTION_DEVICES, {}))
    return devices


def serialize(obj):
    """Serialize values, including models and enum names."""
    if isinstance(obj, Enum):
        return obj.name
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    if isinstance(obj, BaseModel):
        if hasattr(obj, "model_dump"):
            return serialize(obj.model_dump())
        return serialize(obj.dict())
    if isinstance(obj, dict):
        return {key: serialize(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [serialize(value) for value in obj]
    if hasattr(obj, "__dict__"):
        result = {
            key: serialize(value)
            for key, value in obj.__dict__.items()
            if not key.startswith("_")
        }
        properties = [
            name
            for name in dir(obj)
            if not name.startswith("_")
            and name not in result
            and isinstance(getattr(type(obj), name, None), property)
        ]
        result.update(
            {name: serialize(getattr(obj, name, None)) for name in properties}
        )
        return result
    return str(obj)
