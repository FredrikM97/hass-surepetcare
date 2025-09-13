"""Select platform for SurePetCare integration."""

from __future__ import annotations
from dataclasses import dataclass
from surepcio.enums import ProductId, CloseDelay, FeederTrainingMode
from config.custom_components.surepetcare.config_flow import SurePetcareClient
from config.custom_components.surepetcare.coordinator import (
    SurePetCareDeviceDataUpdateCoordinator,
)
from config.custom_components.surepetcare.entity import (
    SurePetCareBaseEntity,
    SurePetCareBaseEntityDescription,
)
from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import COORDINATOR, COORDINATOR_DICT, DOMAIN, KEY_API


@dataclass(frozen=True, kw_only=True)
class SurePetCareSelectEntityDescription(
    SurePetCareBaseEntityDescription, SelectEntityDescription
):
    """Describes SurePetCare select entity."""

    enum_class: type | None = None


SELECTS: dict[str, tuple[SurePetCareSelectEntityDescription, ...]] = {
    ProductId.FEEDER_CONNECT: (
        SurePetCareSelectEntityDescription(
            key="lid",
            field="control.lid.close_delay",
            options=[e.name for e in CloseDelay],
            enum_class=CloseDelay,
        ),
        SurePetCareSelectEntityDescription(
            key="training_mode",
            field="control.training_mode",
            options=[e.name for e in FeederTrainingMode],
            enum_class=FeederTrainingMode,
        ),
    )
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SurePetCare select for each matching device."""
    coordinator_data = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]
    client = coordinator_data[KEY_API]

    entities = []
    for device_id, device_coordinator in coordinator_data[COORDINATOR_DICT].items():
        descriptions = SELECTS.get(device_coordinator.product_id, ())
        for description in descriptions:
            entities.append(
                SurePetCareSelect(
                    device_coordinator,
                    client,
                    description=description,
                )
            )
    async_add_entities(entities, update_before_add=True)


class SurePetCareSelect(SurePetCareBaseEntity, SelectEntity):
    """The platform class required by Home Assistant."""

    entity_description: SurePetCareSelectEntityDescription

    def __init__(
        self,
        device_coordinator: SurePetCareDeviceDataUpdateCoordinator,
        client: SurePetcareClient,
        description: SurePetCareSelectEntityDescription,
    ) -> None:
        """Initialize a Surepetcare sensor."""
        super().__init__(
            device_coordinator=device_coordinator,
            client=client,
        )
        self.entity_description = description
        self._attr_unique_id = f"{self._attr_unique_id}-{description.key}"
        self._attr_options = self.entity_description.options

    @property
    def current_option(self) -> str | None:
        return self.native_value

    async def async_select_option(self, option: str) -> None:
        if self.entity_description.enum_class is not None:
            option = self.entity_description.enum_class[option]

        await self.coordinator.client.api(
            self._device.set_control(
                **build_nested_dict(self.entity_description.field, option)
            )
        )
        await self.coordinator.async_request_refresh()


def build_nested_dict(field_path: str, value: str) -> dict:
    # Temporarly until better solution
    parts = field_path.split(".")
    d = value
    for part in reversed(parts[1:]):  # Skip 'control'
        d = {part: d}
    return d
