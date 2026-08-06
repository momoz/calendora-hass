"""Calendar platform for Calendora.

Phase 0 wires the platform up and adds nothing. Phase 1 fills it in: one
`CalendarEntity` per member plus one for the household, built from the ICS the
coordinator already fetches.

Two things Phase 1 must get right, recorded here so they are read before the code
is written rather than after the bug report:

- `async_get_events` must return **expanded recurrence instances**. The feed
  carries `RRULE`s; Home Assistant wants occurrences.
- `CalendarEvent.start` and `.end` must be the same type — both `date` or both
  `datetime`, and datetimes tz-aware. An all-day event that becomes an instant
  shifts a birthday by a day in half the world's timezones.

No `CalendarEntityFeature` flag is set, and none may be until there is a write
path. The feed is read-only and always will be (`docs/API-SURFACE.md` §2);
claiming a capability we do not have is worse than not having it, because the UI
and the service field filters both key off these flags.
"""

from __future__ import annotations

from homeassistant.components.calendar import CalendarEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import CalendoraConfigEntry

# The coordinator owns the single fetch; entities never talk to the network.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CalendoraConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Calendora calendar entities."""
    entities: list[CalendarEntity] = []
    async_add_entities(entities)
