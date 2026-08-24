"""Household timeline event-payload building."""

from typing import Any

from surepcio.enums import TimelineEventType
from surepcio.timeline import MovementResource, TimelineEvent, WeightResource

# Event types that carry door movement data (event.movements).
_MOVEMENT_EVENT_TYPES = {
    TimelineEventType.MOVEMENT,
    TimelineEventType.INTRUDER_MOVEMENT,
}

# Event types that carry feeder/fountain weight data (event.weights).
_FEEDING_EVENT_TYPES = {
    TimelineEventType.FEEDING,
    TimelineEventType.WEIGHT_CHANGED,
    TimelineEventType.WEIGHT_CHANGED_TARGET_MET,
    TimelineEventType.TARGET_WEIGHT_SET,
    TimelineEventType.TARE,
}

_DRINKING_EVENT_TYPES = {
    TimelineEventType.POSEIDON_DRINKING,
    TimelineEventType.POSEIDON_WEIGHT_CHANGED,
    TimelineEventType.POSEIDON_TARE,
}


def _movement_details(movement: MovementResource) -> dict[str, Any]:
    """Build the payload for a single door movement entry."""
    return {
        "device_id": movement.device_id,
        "direction": movement.direction.name
        if movement.direction is not None
        else None,
        "side": movement.side.name if movement.side is not None else None,
    }


def _weight_details(weight: WeightResource) -> dict[str, Any]:
    """Build the payload for a single feeder/fountain weight reading."""
    return {
        "device_id": weight.device_id,
        "duration": weight.duration,
        "frames": [
            {
                "index": frame.index,
                "current_weight": frame.current_weight,
                "change": frame.change,
            }
            for frame in weight.frames
        ],
    }


def _base_event_payload(household_id: int, event: TimelineEvent) -> dict[str, Any]:
    """Build the fields common to every timeline event, regardless of type."""
    return {
        "household_id": household_id,
        "id": event.id,
        "type": event.event_type.name if event.event_type is not None else None,
        "created_at": event.created_at.isoformat()
        if event.created_at is not None
        else None,
        "pets": [pet.id for pet in event.pets],
        "devices": [device.id for device in event.devices],
        "users": [user.id for user in event.users],
    }


def build_event_payload(household_id: int, event: TimelineEvent) -> dict[str, Any]:
    """Build the EVENT_TIMELINE payload for one event, by event category."""
    payload = _base_event_payload(household_id, event)
    if event.event_type in _MOVEMENT_EVENT_TYPES:
        payload["movements"] = [_movement_details(m) for m in event.movements]
    elif (
        event.event_type in _FEEDING_EVENT_TYPES
        or event.event_type in _DRINKING_EVENT_TYPES
    ):
        payload["weights"] = [_weight_details(w) for w in event.weights]
    return payload
