"""Helpers for scoping entities/devices to their household's config subentry."""

from collections import defaultdict
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from .const import HOUSEHOLD_ID

if TYPE_CHECKING:
    from homeassistant.helpers.entity import Entity

    from .coordinator import SurePetcareConfigEntry


def subentry_id_for_household(
    entry: "SurePetcareConfigEntry", household_id: int | None
) -> str | None:
    """Return the subentry_id whose data references this household_id, if any."""
    if household_id is None:
        return None
    return next(
        (
            subentry_id
            for subentry_id, subentry in entry.subentries.items()
            if subentry.data.get(HOUSEHOLD_ID) == household_id
        ),
        None,
    )


def add_entities_by_household(
    async_add_entities: Callable[..., Any],
    entry: "SurePetcareConfigEntry",
    entities: "Sequence[Entity]",
) -> None:
    """Group entities by their household and add each group under its subentry."""
    grouped: dict[str | None, list[Entity]] = defaultdict(list)
    for entity in entities:
        household_id = getattr(entity, "_household_id", None)
        grouped[subentry_id_for_household(entry, household_id)].append(entity)
    for subentry_id, group in grouped.items():
        async_add_entities(group, config_subentry_id=subentry_id)
