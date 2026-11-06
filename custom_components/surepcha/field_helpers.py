"""Shared bowl, pet-assignment, and curfew calculations for HA fields."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING, Any

from surepcio.devices.device import SurePetCareBase
from surepcio.devices.entities import DevicePetTag
from surepcio.devices.pet import Pet
from surepcio.entities.bowl import bowl_weights
from surepcio.entities.pet import iter_pet_events
from surepcio.enums import (
    BowlType,
    ModifyDeviceTag,
    PetDeviceLocationProfile,
    ProductId,
)
from surepcio.timeline import TimelineEvent

from .const import NAME, PRODUCT_ID
from .fields import FLAP_PRODUCTS, FieldOption
from .helper import get_device_options

if TYPE_CHECKING:
    from .entity import SurePetCareBaseEntity

logger = logging.getLogger(__name__)


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


def _device_information(device: Any) -> dict[str, Any]:
    return {
        "household_id": device.household_id,
        "id": device.id,
        "parent_device_id": device.entity_info.parent_device_id,
        "photo": device.photo,
    }


def _pet_information(pet: Any) -> dict[str, Any]:
    return {
        **_device_information(pet),
        "product_id": pet.product_id,
        "tag": pet.tag,
    }


def _has_second_bowl(device: Any) -> bool:
    bowls = getattr(getattr(device, "control", None), "bowls", None)
    return bowls is not None and (
        bowls.type == BowlType.TWO_SMALL
        or (bowls.type is None and len(bowls.settings or ()) > 1)
    )


def _bowl_target(device: Any, index: int) -> float | None:
    bowls = device.control.bowls
    settings = bowls.settings if bowls is not None else None
    setting = (
        settings[index] if settings is not None and index < len(settings) else None
    )
    return setting.target if setting is not None else None


def _sum_targets(device: Any) -> float | None:
    settings = getattr(getattr(device.control, "bowls", None), "settings", None) or []
    targets = [
        setting.target for setting in settings if setting and setting.target is not None
    ]
    return sum(targets) if targets else None


def _bowl_extra(
    device: Any, index: int, *, include_substance: bool = False
) -> dict[str, Any]:
    statuses = getattr(device.status, "bowl_status", None) or []
    settings = getattr(getattr(device.control, "bowls", None), "settings", None) or []
    if index >= len(statuses):
        return {}
    status = statuses[index]
    setting = settings[index] if index < len(settings) else None
    result: dict[str, Any] = {
        "position": (
            status.position.name.lower() if status.position is not None else None
        ),
        "food_type": (
            setting.food_type.name.lower()
            if setting is not None and setting.food_type is not None
            else None
        ),
        "last_filled_at": status.last_filled_at,
        "last_zeroed_at": status.last_zeroed_at,
        "last_fill_weight": status.last_fill_weight,
    }
    if include_substance:
        result["substance_type"] = status.substance_type
    return result


def _event_weights(device: Any, event: TimelineEvent) -> dict[int, float]:
    return bowl_weights(
        event,
        device_id=device.id,
        indices=(0, 1) if _has_second_bowl(device) else (0,),
    )


def _weight_reading(
    device: Any, event: TimelineEvent, index: int
) -> tuple[float, dict[str, Any]] | None:
    weights = _event_weights(device, event)
    if index not in weights:
        return None
    return (weights[index], _bowl_extra(device, index, include_substance=index == 1))


def _fill_reading(
    device: Any, event: TimelineEvent
) -> tuple[float | None, dict[str, Any]] | None:
    weights = _event_weights(device, event)
    if not weights:
        return None
    total_weight = total_target = 0.0
    attributes: dict[str, Any] = {}
    for index, weight in weights.items():
        target = _bowl_target(device, index)
        percent = None
        if target is not None and target > 0:
            clamped = max(weight, 0)
            percent = clamped / target * 100
            total_weight += clamped
            total_target += target
        attributes[f"bowl_{index}_fill_percent"] = percent
    return (total_weight / total_target * 100 if total_target > 0 else None, attributes)


def _weight_capacity_extra(device: Any) -> dict[str, Any]:
    bowls = getattr(getattr(device.control, "bowls", None), "settings", None) or []
    return {
        f"bowls_{index}_target": (
            bowls[index].target if index < len(bowls) and bowls[index] else None
        )
        for index in range(2)
    }


def _poseidon_bowl_value(device: Any, attribute: str) -> Any:
    bowls = device.status.bowl_status
    return getattr(bowls[0], attribute) if bowls else None


def _poseidon_extra(device: Any) -> dict[str, Any]:
    statuses = getattr(device.status, "bowl_status", None) or []
    if not statuses:
        return {}
    status = statuses[0]
    return {
        "last_filled_at": status.last_filled_at,
        "last_zeroed_at": status.last_zeroed_at,
        "last_fill_weight": status.last_fill_weight,
    }


def _poseidon_volume(
    device: Any, event: TimelineEvent
) -> tuple[float, dict[str, Any]] | None:
    weights = bowl_weights(event, device_id=device.id, indices=(0,))
    return (weights[0], _poseidon_extra(device)) if 0 in weights else None


def _flap_profiles(entity: SurePetCareBaseEntity) -> list[DevicePetTag]:
    options = get_device_options(entity.hass, entity.coordinator.config_entry)
    flaps = {
        int(device_id)
        for device_id, metadata in options.items()
        if ProductId.find(metadata.get(PRODUCT_ID)) in FLAP_PRODUCTS
    }
    return [item for item in entity.device.status.devices.items if item.id in flaps]


def _indoor_only(entity: SurePetCareBaseEntity) -> bool | None:
    profiles = {item.profile for item in _flap_profiles(entity)}
    if not profiles:
        return None
    if len(profiles) > 1:
        logger.warning(
            "Flap device profiles are not uniform for pet %s: %s",
            entity.device.id,
            profiles,
        )
    return profiles == {PetDeviceLocationProfile.INDOOR_ONLY}


def _write_indoor_only(entity: SurePetCareBaseEntity, value: Any) -> list[Any]:
    pet: Any = entity.device
    profiles = _flap_profiles(entity)
    if not profiles:
        raise ValueError(f"No flap devices are assigned to pet {pet.id}")
    profile = (
        PetDeviceLocationProfile.INDOOR_ONLY
        if value
        else PetDeviceLocationProfile.NO_RESTRICTION
    )
    return [
        pet.set_profile(item.id, profile) for item in profiles if item.id is not None
    ]


def _assignment_options(
    entity: SurePetCareBaseEntity, action: ModifyDeviceTag
) -> tuple[FieldOption, ...]:
    pet = entity.device
    assigned = [item.id for item in pet.status.devices.items if item.id is not None]
    options = get_device_options(entity.hass, entity.coordinator.config_entry)
    eligible = [
        (int(device_id), metadata.get(NAME, str(device_id)))
        for device_id, metadata in options.items()
        if (product := ProductId.find(metadata.get(PRODUCT_ID))) is not None
        and product not in {ProductId.PET, ProductId.HUB}
        and ((int(device_id) in assigned) == (action == ModifyDeviceTag.REMOVE))
    ]
    if action == ModifyDeviceTag.REMOVE:
        eligible.sort(key=lambda item: assigned.index(item[0]))
    return tuple(
        FieldOption(
            str(device_id),
            f"{name} ({device_id})"
            if sum(other_name == name for _, other_name in eligible) > 1
            else name,
        )
        for device_id, name in eligible
    )


def _curfew_active(device: Any) -> bool | None:
    return device.is_curfew_active if device.control.curfew is not None else None


def _curfew_extra(device: Any) -> dict[str, Any]:
    curfew = getattr(device.control, "curfew", None)
    if not curfew:
        return {}
    curfews = curfew if isinstance(curfew, list) else [curfew]
    if not isinstance(curfew, list):
        item = curfews[0]
        return {
            "enabled": item.enabled,
            "lock_time": str(item.lock_time)[:5] if item.lock_time else None,
            "unlock_time": str(item.unlock_time)[:5] if item.unlock_time else None,
        }
    return {
        "curfew": [
            {
                "enabled": item.enabled,
                "lock_time": str(item.lock_time),
                "unlock_time": str(item.unlock_time),
            }
            for item in curfews
        ]
    }
