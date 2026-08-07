"""Calendar platform for Calendora.

**Read-only. No `CalendarEntityFeature` flag is set**, because `/api/v1` has no
write routes yet (`docs/API-SURFACE.md` §7). Those flags are not decoration — the
UI and the service field filters key off them, so claiming `CREATE_EVENT` would
hand the user an edit dialog that fails on save.

Occurrences arrive **pre-expanded** (§4). The server owns recurrence; there is no
RRULE on the wire and nothing here re-derives one. That is the entire reason this
integration went straight to `/api/v1` instead of parsing ICS.

The one genuinely delicate conversion lives in `_as_calendar_event`, and §4a is
explicit about why: `start` and `end` are **always instants, even when
`isAllDay` is true**, and the all-day day must be derived in the *event's own*
timezone. Doing it in the viewer's zone, or in UTC, is exactly how a birthday
moves a day for everyone on the wrong side of a meridian.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import CalendoraConfigEntry
from .api import CalendoraError
from .const import DOMAIN, LOGGER, MAX_EVENT_RANGE_DAYS
from .coordinator import CalendoraDataUpdateCoordinator

# The coordinator owns the fetching; entities never poll.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CalendoraConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Calendora calendar entities.

    One entity, the household. Per-member calendars would use `?member=`, and
    §4a notes that an occurrence with empty `attendeeIds` belongs to the whole
    household and is never filtered by it — so a per-member calendar would
    silently omit every household-wide event unless that rule is implemented
    deliberately. That is a feature to design, not a loop to add here.
    """
    async_add_entities([CalendoraHouseholdCalendar(entry.runtime_data)])


def _event_timezone(occurrence: dict[str, Any], fallback: datetime) -> Any:
    """Return the event's authored zone, or the offset it was written with.

    §4a requires the all-day date be derived in the event's own timezone. If that
    zone name is one this machine's tzdata has never heard of, the next best
    thing is the offset carried in the timestamp itself — still the authoring
    side's intent. Falling back to the *viewer's* zone is the one option that is
    always wrong, so it is not offered.
    """
    name = occurrence.get("timezone")
    if name:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            LOGGER.debug("Unknown event timezone %s; using its written offset", name)
    return fallback.tzinfo


def _as_calendar_event(occurrence: dict[str, Any]) -> CalendarEvent | None:
    """Convert one occurrence into Home Assistant's shape.

    Returns `None` for anything unusable rather than raising: one malformed
    occurrence must not take out the whole calendar.
    """
    start_raw = occurrence.get("start")
    end_raw = occurrence.get("end")
    if not start_raw or not end_raw:
        return None

    start_dt = dt_util.parse_datetime(start_raw)
    end_dt = dt_util.parse_datetime(end_raw)
    if start_dt is None or end_dt is None:
        LOGGER.debug("Skipping occurrence %s: unparseable times", occurrence.get("id"))
        return None

    if occurrence.get("isAllDay"):
        # Both instants resolved in the event's own zone, per §4a.
        tzinfo = _event_timezone(occurrence, start_dt)
        start: date | datetime = start_dt.astimezone(tzinfo).date()
        end: date | datetime = end_dt.astimezone(tzinfo).date()
        if end <= start:
            # Home Assistant requires end > start, and treats an all-day end as
            # exclusive. An API end that lands on the same day is therefore an
            # inclusive one; a single day becomes start..start+1.
            end = start + timedelta(days=1)
    else:
        # Same instants, rendered in the viewer's zone — which is correct here,
        # because a timed event is a moment and a moment is the same moment
        # everywhere.
        start = dt_util.as_local(start_dt)
        end = dt_util.as_local(end_dt)

    return CalendarEvent(
        summary=occurrence.get("title") or "",
        start=start,
        end=end,
        description=occurrence.get("description"),
        location=occurrence.get("location"),
        uid=occurrence.get("id"),
    )


class CalendoraHouseholdCalendar(
    CoordinatorEntity[CalendoraDataUpdateCoordinator], CalendarEntity
):
    """The household's calendar, read-only."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, coordinator: CalendoraDataUpdateCoordinator) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        household_id = coordinator.data.household_id
        self._attr_unique_id = f"{household_id}-calendar"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, household_id)},
            entry_type=DeviceEntryType.SERVICE,
            name=coordinator.data.household_name,
            manufacturer="Calendora",
        )

    @property
    def event(self) -> CalendarEvent | None:
        """Return the event happening now, or the next one.

        Served from the coordinator's window rather than a fresh request: this is
        read on every state update, and §4a promises occurrences arrive sorted by
        `start`, so the first one that has not finished is the answer.
        """
        now = dt_util.now()
        for occurrence in self.coordinator.data.occurrences:
            event = _as_calendar_event(occurrence)
            if event is None:
                continue
            if _ends_after(event, now):
                return event
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return occurrences overlapping an arbitrary window.

        Asked directly of the API rather than served from the coordinator's
        window, because the UI can browse to any month and answering "nothing
        there" for a month we simply had not loaded is worse than a request.

        The window is converted to **days in the key owner's timezone** — §4
        rejects an instant outright, since the same instant is a different day
        depending on where it was written.
        """
        try:
            owner_zone = ZoneInfo(self.coordinator.data.key_owner_timezone)
        except (ZoneInfoNotFoundError, ValueError):
            owner_zone = dt_util.UTC

        date_from = start_date.astimezone(owner_zone).date()
        date_to = end_date.astimezone(owner_zone).date()

        if (date_to - date_from).days > MAX_EVENT_RANGE_DAYS:
            # §4 rejects an over-long range rather than truncating it, so a
            # clamp here would answer a five-year question with one year of
            # events and look like an empty calendar. Refusing is honest.
            LOGGER.warning(
                "Calendora was asked for %s days of calendar; the API allows %s",
                (date_to - date_from).days,
                MAX_EVENT_RANGE_DAYS,
            )
            date_to = date_from + timedelta(days=MAX_EVENT_RANGE_DAYS)

        try:
            payload = await self.coordinator.client.async_get_events(date_from, date_to)
        except CalendoraError as err:
            LOGGER.debug("Could not fetch events for the requested window: %s", err)
            return []

        events = [
            event
            for occurrence in payload.get("occurrences", [])
            if (event := _as_calendar_event(occurrence)) is not None
        ]
        # The API answers in whole days in someone else's zone, so trim to what
        # was actually asked for.
        return [event for event in events if _overlaps(event, start_date, end_date)]


def _boundaries(event: CalendarEvent) -> tuple[datetime, datetime]:
    """Return an event's start and end as instants, for comparison only.

    An all-day event has no instant of its own — this resolves it in the
    viewer's zone purely so it can be compared against a requested window. The
    values are never handed back to Home Assistant; the `date` objects are.
    """
    if isinstance(event.start, datetime):
        return event.start, event.end

    zone = dt_util.get_default_time_zone()
    return (
        datetime.combine(event.start, datetime.min.time(), tzinfo=zone),
        datetime.combine(event.end, datetime.min.time(), tzinfo=zone),
    )


def _overlaps(event: CalendarEvent, window_start: datetime, window_end: datetime) -> bool:
    """True when any part of the event falls inside the window."""
    start, end = _boundaries(event)
    return start < window_end and end > window_start


def _ends_after(event: CalendarEvent, moment: datetime) -> bool:
    """True when the event has not finished yet."""
    return _boundaries(event)[1] > moment
