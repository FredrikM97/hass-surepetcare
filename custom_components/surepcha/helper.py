"""Shared Home Assistant integration helpers."""

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from enum import Enum
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from pydantic import BaseModel
from surepcio.devices.device import SurePetCareBase
from surepcio.devices.pet import Pet
from surepcio.entities.pet import iter_pet_events
from surepcio.enums import BowlType
from surepcio.security.exceptions import ApiError, AuthenticationError
from surepcio.timeline import TimelineEvent

from .const import DOMAIN, OPTION_DEVICES


def iter_device_events(
    event: TimelineEvent,
    device: SurePetCareBase,
    devices: Iterable[SurePetCareBase],
) -> Iterator[TimelineEvent]:
    """Select timeline observations for an integration entity without caching."""
    if isinstance(device, Pet):
        for pet, source in iter_pet_events(
            event, (item for item in devices if isinstance(item, Pet))
        ):
            if pet.id == device.id:
                yield source
    elif event.created_at is not None:
        yield event


def has_second_bowl(device: Any) -> bool:
    bowls = getattr(getattr(device, "control", None), "bowls", None)
    return bowls is not None and (
        bowls.type == BowlType.TWO_SMALL
        or (bowls.type is None and len(bowls.settings or ()) > 1)
    )


def bowl_target(device: Any, index: int) -> float | None:
    bowls = device.control.bowls
    settings = bowls.settings if bowls is not None else None
    setting = (
        settings[index] if settings is not None and index < len(settings) else None
    )
    return setting.target if setting is not None else None


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
