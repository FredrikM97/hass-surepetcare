from homeassistant import core


async def async_setup_entry(hass: core.HomeAssistant, entry):
    """Set up SurePetCare from a config entry."""

    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "sensor")
    )


    return True
