"""Test component setup."""
from homeassistant.setup import async_setup_component

from custom_components.surepetcare.const import DOMAIN


async def test_async__entry_setup(hass):
    """Test the component gets setup."""
    assert await async_setup_component(hass, DOMAIN, {}) is True
