"""The Calendora integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import CalendoraDataUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.CALENDAR]

# State lives on the entry, not in hass.data[DOMAIN] — the runtime object is
# typed onto the entry so every platform gets it without a lookup or a cast.
type CalendoraConfigEntry = ConfigEntry[CalendoraDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: CalendoraConfigEntry) -> bool:
    """Set up Calendora from a config entry."""
    coordinator = CalendoraDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CalendoraConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
