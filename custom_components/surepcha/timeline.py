"""Household timeline event-payload building."""

import json
from datetime import datetime
from enum import Enum
from typing import Any

from surepcio.timeline import TimelineEvent


def _serialize_event_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {key: _serialize_event_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize_event_value(item) for item in value]
    return value


def build_event_payload(household_id: int, event: TimelineEvent) -> dict[str, Any]:
    """Build a compact Home Assistant payload with structured event data."""
    payload = _serialize_event_value(
        event.model_dump(
            mode="python", by_alias=True, exclude_defaults=True, exclude_none=True
        )
    )
    if (data := payload.get("data")) is not None:
        try:
            payload["data"] = json.loads(data)
        except json.JSONDecodeError:
            payload["data"] = {"raw": data}
    if payload.get("data") is None:
        payload.pop("data", None)
    payload["household_id"] = household_id
    return payload
