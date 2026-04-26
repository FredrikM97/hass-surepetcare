"""Support for Sure Petcare Button."""

from dataclasses import dataclass
import logging
from surepcio.enums import ProductId, HubPairMode
from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.entity import EntityCategory
from custom_components.surepcha.method_field import ButtonMethodField


from .coordinator import SurePetCareDeviceDataUpdateCoordinator, SurePetcareConfigEntry
from .entity import (
    SurePetCareBaseEntity,
    SurePetCareBaseEntityDescription,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SurePetCareButtonEntityDescription(
    SurePetCareBaseEntityDescription, ButtonEntityDescription
):
    """Describes SurePetCare button entity."""


BUTTONS: dict[str, tuple[SurePetCareButtonEntityDescription, ...]] = {
    ProductId.HUB: (
        SurePetCareButtonEntityDescription(
            key="pairing_mode",
            translation_key="pairing_mode",
            field=ButtonMethodField(path="control.pairing_mode", on=HubPairMode.ON),
            entity_category=EntityCategory.CONFIG,
        ),
    )
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SurePetcareConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up SurePetCare sensors for each matching device."""
    coordinators = entry.runtime_data

    entities = [
        SurePetCareButton(
            coordinator,
            description=description,
        )
        for coordinator in coordinators
        for description in BUTTONS.get(coordinator.product_id, ())
    ]
    async_add_entities(entities)


class SurePetCareButton(SurePetCareBaseEntity, ButtonEntity):
    """The platform class required by Home Assistant."""

    entity_description: SurePetCareButtonEntityDescription

    def __init__(
        self,
        coordinator: SurePetCareDeviceDataUpdateCoordinator,
        description: SurePetCareButtonEntityDescription,
    ) -> None:
        """Initialize a Surepetcare sensor."""
        super().__init__(
            coordinator=coordinator,
        )
        self.entity_description = description
        self._attr_unique_id = f"{coordinator._device.id}-{description.key}"

    async def async_press(self) -> None:
        """Press the button."""
        await self.send_command(True)
