"""The Calendora integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .blueprint_check import async_check_blueprint_is_imported
from .const import CONF_API_KEY, LOGGER
from .push_budget import async_register_push_budget
from .coordinator import CalendoraDataUpdateCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CALENDAR,
    Platform.SENSOR,
    Platform.TODO,
]

# State lives on the entry, not in hass.data[DOMAIN].
type CalendoraConfigEntry = ConfigEntry[CalendoraDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: CalendoraConfigEntry) -> bool:
    """Set up Calendora from a config entry."""
    coordinator = CalendoraDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # The stream is the update path. Registered as a background task on the
    # entry so Home Assistant cancels it on unload and on shutdown — an
    # un-owned task outlives the entry it belongs to and then talks to a
    # torn-down coordinator, which is the classic custom-integration leak.
    entry.async_create_background_task(
        hass, coordinator.async_run_stream(), name="calendora stream"
    )

    # Installing this integration does not install its blueprint, and until
    # 2026-08-10 nothing said so anywhere — which is why three releases shipped
    # a blueprint that had never been imported into any household and therefore
    # could not have been noticed to be broken. See `blueprint_check`.
    await async_check_blueprint_is_imported(hass)

    # §6's push cap. Registered here rather than per-entry — it is one service
    # for the instance, and `async_register_push_budget` is idempotent.
    await async_register_push_budget(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: CalendoraConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate a 0.0.1 entry, which held a calendar feed URL and no API key.

    The feed is now a prohibited surface, so there is nothing to migrate *to* —
    the stored URL is not convertible into a key. Rather than let such an entry
    fail with a confusing error about a missing field, this rewrites it to a
    keyless v2 entry, which fails cleanly into the reauth flow and asks the user
    for a key. Losing the feed URL is the point: it must not linger in storage.
    """
    if entry.version == 1:
        data = {key: value for key, value in entry.data.items() if key == CONF_API_KEY}
        hass.config_entries.async_update_entry(entry, data=data, version=2)
        LOGGER.info(
            "Migrated the Calendora entry from the calendar feed to the API."
            " You will be asked for an API key"
        )
    return True
