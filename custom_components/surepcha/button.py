"""Present library action interactions."""

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from surepcio.enums import HubPairMode, ProductId

from .coordinator import SurePetcareConfigEntry
from .entity import SurePetCareBaseEntity
from .fields import SurePetCareDescriptionMixin


@dataclass(frozen=True, kw_only=True)
class SurePetCareButtonEntityDescription(
    ButtonEntityDescription, SurePetCareDescriptionMixin
):
    """Native button metadata and SurePetCare API behavior."""


BUTTON_FIELDS: dict[ProductId, tuple[SurePetCareButtonEntityDescription, ...]] = {
    ProductId.HUB: (
        SurePetCareButtonEntityDescription(
            key="pairing_mode",
            translation_key="pairing_mode",
            entity_category=EntityCategory.CONFIG,
            command=lambda entity, _value: entity.device.set_pairing_mode(
                HubPairMode.ON
            ),
        ),
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SurePetcareConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        SurePetCareButton(coordinator, device, description)
        for device in coordinator.devices.values()
        for description in BUTTON_FIELDS.get(device.product, ())
    )


class SurePetCareButton(SurePetCareBaseEntity, ButtonEntity):
    """A library-provided action."""

    entity_description: SurePetCareButtonEntityDescription

    async def async_press(self) -> None:
        await self.send_command(True)
