"""Support for Sure Petcare Button."""

from dataclasses import dataclass
import logging
from typing import Any
from surepcio.enums import ProductId, HubPairMode
from surepcio import SurePetcareClient
from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.entity import EntityCategory
from custom_components.surepetcare.helper import MethodField, should_add_entity


from .const import (
    COORDINATOR,
    COORDINATOR_DICT,
    DOMAIN,
    KEY_API,
)
from .coordinator import SurePetCareDeviceDataUpdateCoordinator
from .entity import (
    SurePetCareBaseEntity,
    SurePetCareBaseEntityDescription,
)

logger = logging.getLogger(__name__)

@dataclass(frozen=True, slots=True)
class ButtonMethodField(MethodField):
    """MethodField for button-like entities, supporting on mapping."""

    on: Any = True
    def set(self, device: object, config: dict, value: Any) -> Any:
        if value is True and self.on:
            value = self.on
        return MethodField.set(self, device, config, value)



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
            field=ButtonMethodField(
                path="control.pairing_mode", on=HubPairMode.ON
            ),
            entity_category=EntityCategory.CONFIG,
        ),
    )
    
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up SurePetCare sensors for each matching device."""
    coordinator_data = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]
    client = coordinator_data[KEY_API]

    entities = []
    for device_coordinator in coordinator_data[COORDINATOR_DICT].values():
        descriptions = BUTTONS.get(device_coordinator.product_id, ())
        entities.extend(
            [
                SurePetCareButton(
                    device_coordinator,
                    client,
                    description=description,
                )
                for description in descriptions
                if should_add_entity(
                    description, device_coordinator.data, config_entry.options
                )
            ]
        )
    async_add_entities(entities, update_before_add=True)


class SurePetCareButton(SurePetCareBaseEntity, ButtonEntity):
    """The platform class required by Home Assistant."""

    entity_description: SurePetCareButtonEntityDescription

    def __init__(
        self,
        device_coordinator: SurePetCareDeviceDataUpdateCoordinator,
        client: SurePetcareClient,
        description: SurePetCareButtonEntityDescription,
    ) -> None:
        """Initialize a Surepetcare sensor."""
        super().__init__(
            device_coordinator=device_coordinator,
            client=client,
        )
        self.entity_description = description
        self._attr_unique_id = f"{self._attr_unique_id}-{description.key}"

    async def async_press(self) -> None:
        """Press the button."""
        await self.send_command(1)
