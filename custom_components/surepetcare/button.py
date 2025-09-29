"""Support for Sure Petcare Button."""

from dataclasses import dataclass
import logging
from surepcio.enums import ProductId
from surepcio import SurePetcareClient
from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

from custom_components.surepetcare.entity import build_nested_dict

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


@dataclass(frozen=True, kw_only=True)
class SurePetCareButtonEntityDescription(
    SurePetCareBaseEntityDescription, ButtonEntityDescription
):
    """Describes SurePetCare button entity."""


BUTTONS: dict[str, tuple[SurePetCareButtonEntityDescription, ...]] = {
    ProductId.FEEDER_CONNECT: (
        SurePetCareButtonEntityDescription(
            key="tare",
            translation_key="tare",
            field_fn=lambda device, r: device.control.tare,
            icon="mdi:scale",
            EntityCategory.CONFIG
        ),
    ),
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
    for device_id, device_coordinator in coordinator_data[COORDINATOR_DICT].items():
        descriptions = BUTTONS.get(device_coordinator.product_id, ())
        for description in descriptions:
            entities.append(
                SurePetCareButton(
                    device_coordinator,
                    client,
                    description=description,
                )
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
        if self.entity_description.field is None:
            return
        await self.coordinator.client.api(
            self._device.set_control(
                **build_nested_dict(self.entity_description.field, 1)
            )
        )
        await self.coordinator.async_request_refresh()
