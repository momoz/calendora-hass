"""Calendar platform for Calendora.

**Read-only. No `CalendarEntityFeature` flag is set**, because `/api/v1` has no
write routes yet (`docs/API-SURFACE.md` §7). Those flags are not decoration — the
UI and the service field filters key off them, so claiming `CREATE_EVENT` would
hand the user an edit dialog that fails on save.

Occurrences arrive **pre-expanded** (§4). The server owns recurrence; there is no
RRULE on the wire and nothing here re-derives one.

Two conversions in this file are delicate, and both are places where the obvious
implementation is quietly wrong:

- **All-day dates** (`_as_calendar_event`). §4a hands over instants even when
  `isAllDay` is true, and the day must be derived in the *event's own* timezone.
  The viewer's zone, or UTC, moves a birthday by a day for everyone on the wrong
  side of a meridian.
- **Who an event belongs to** (`_belongs_to_member`). See the note there; the
  naive version silently empties every person's calendar of everything the
  household does together.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant, callback
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


def _belongs_to_member(occurrence: dict[str, Any], member_id: str) -> bool:
    """Decide whether one occurrence belongs on one member's calendar.

    **This is the function that makes per-member calendars worth having, and the
    obvious version of it is wrong.**

    `attendeeIds in occurrence` looks like the whole rule. It is not: §4a states
    that an occurrence with an **empty** `attendeeIds` belongs to the whole
    household. Filtering on membership alone therefore removes every
    household-wide event — the school holidays, the bin collection, the family
    dinner — from *every* person's calendar, leaving only the things they do
    alone. Nobody reports that as a bug, because each calendar still has events
    in it and looks plausible. It is simply, quietly, missing the half of family
    life that is shared.

    The rule, in full: an occurrence is on a member's calendar if it names them,
    **or if it names nobody at all.**
    """
    attendee_ids = occurrence.get("attendeeIds")
    if not attendee_ids:
        return True
    return member_id in attendee_ids


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CalendoraConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the household calendar and one calendar per member.

    Members are added as they appear rather than only at startup: a family that
    adds a child to Calendora should not have to restart Home Assistant to see
    their calendar. Removal is deliberately *not* handled here — an entity whose
    member has gone becomes unavailable, and deleting it is the user's call
    through the entity registry, because it may be carrying automations.
    """
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new_members() -> None:
        new: list[CalendarEntity] = []
        for member in coordinator.data.members:
            member_id = member.get("id")
            if not member_id or member_id in known:
                continue
            known.add(member_id)
            new.append(CalendoraMemberCalendar(coordinator, member))
        if new:
            async_add_entities(new)

    async_add_entities([CalendoraHouseholdCalendar(coordinator)])
    _add_new_members()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_members))


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
            # Home Assistant requires end > start and treats an all-day end as
            # exclusive. Calendora's editor stores an all-day event as 00:00:00
            # to 23:59:59 on the same day, so this branch is the normal case for
            # app-created events, not an edge case.
            end = start + timedelta(days=1)
    else:
        # Same instants, rendered in the viewer's zone — correct here, because a
        # timed event is a moment and a moment is the same moment everywhere.
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


class CalendoraCalendar(
    CoordinatorEntity[CalendoraDataUpdateCoordinator], CalendarEntity
):
    """Shared behaviour for every Calendora calendar.

    Subclasses differ only in which occurrences they keep, which is the one thing
    that distinguishes a household calendar from a person's.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: CalendoraDataUpdateCoordinator) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.data.household_id)},
            entry_type=DeviceEntryType.SERVICE,
            name=coordinator.data.household_name,
            manufacturer="Calendora",
        )

    def _keep(self, occurrence: dict[str, Any]) -> bool:
        """Return True when this occurrence belongs on this calendar."""
        raise NotImplementedError

    @property
    def event(self) -> CalendarEvent | None:
        """Return the event happening now, or the next one.

        Served from the coordinator's window rather than a fresh request: this is
        read on every state update, and §4a promises occurrences arrive sorted by
        `start`, so the first one that has not finished is the answer.
        """
        now = dt_util.now()
        for occurrence in self.coordinator.data.occurrences:
            if not self._keep(occurrence):
                continue
            event = _as_calendar_event(occurrence)
            if event is not None and _ends_after(event, now):
                return event
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return occurrences overlapping an arbitrary window.

        Asked of the API rather than served from the coordinator's window,
        because the UI can browse to any month, and answering "nothing there" for
        a month we merely had not loaded is worse than making a request. The
        coordinator collapses the identical requests that several calendars make
        when one dashboard renders.

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
            # §4 rejects an over-long range rather than truncating it, so asking
            # anyway would fail the whole request. Trimming and saying so beats
            # answering a five-year question with an error.
            LOGGER.warning(
                "Calendora was asked for %s days of calendar; the API allows %s,"
                " so the window was trimmed",
                (date_to - date_from).days,
                MAX_EVENT_RANGE_DAYS,
            )
            date_to = date_from + timedelta(days=MAX_EVENT_RANGE_DAYS)

        try:
            occurrences = await self.coordinator.async_fetch_window(date_from, date_to)
        except CalendoraError as err:
            LOGGER.debug("Could not fetch events for the requested window: %s", err)
            return []

        events = [
            event
            for occurrence in occurrences
            if self._keep(occurrence)
            and (event := _as_calendar_event(occurrence)) is not None
        ]
        # The API answers in whole days in someone else's zone, so trim to what
        # was actually asked for.
        return [event for event in events if _overlaps(event, start_date, end_date)]


class CalendoraHouseholdCalendar(CalendoraCalendar):
    """Everything the household has on."""

    _attr_name = None

    def __init__(self, coordinator: CalendoraDataUpdateCoordinator) -> None:
        """Initialise the household calendar."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.data.household_id}-calendar"

    def _keep(self, occurrence: dict[str, Any]) -> bool:
        """Keep everything — this is the whole household's calendar."""
        return True


class CalendoraMemberCalendar(CalendoraCalendar):
    """One person's calendar: what they are on, plus what everyone is on."""

    def __init__(
        self, coordinator: CalendoraDataUpdateCoordinator, member: dict[str, Any]
    ) -> None:
        """Initialise a member's calendar."""
        super().__init__(coordinator)
        self._member_id: str = member["id"]
        # §4a: `name` is already resolved server-side, including any display-name
        # override. Re-deriving it from /people would undo the user's choice.
        self._attr_name = member.get("name") or "Unknown"
        self._attr_unique_id = (
            f"{coordinator.data.household_id}-calendar-{self._member_id}"
        )

    @property
    def available(self) -> bool:
        """Unavailable once the member is gone from the household.

        The entity is kept rather than removed, because it may be named in
        automations the user still wants; making it unavailable says so plainly
        instead of silently reporting an empty calendar forever.
        """
        return super().available and any(
            member.get("id") == self._member_id
            for member in self.coordinator.data.members
        )

    def _keep(self, occurrence: dict[str, Any]) -> bool:
        """Keep what names this member, and what names nobody."""
        return _belongs_to_member(occurrence, self._member_id)


def _boundaries(event: CalendarEvent) -> tuple[datetime, datetime]:
    """Return an event's start and end as instants, for comparison only.

    An all-day event has no instant of its own — this resolves it in the viewer's
    zone purely so it can be compared against a requested window. These values
    are never handed back to Home Assistant; the `date` objects are.
    """
    if isinstance(event.start, datetime):
        return event.start, event.end

    zone = dt_util.get_default_time_zone()
    return (
        datetime.combine(event.start, datetime.min.time(), tzinfo=zone),
        datetime.combine(event.end, datetime.min.time(), tzinfo=zone),
    )


def _overlaps(
    event: CalendarEvent, window_start: datetime, window_end: datetime
) -> bool:
    """True when any part of the event falls inside the window."""
    start, end = _boundaries(event)
    return start < window_end and end > window_start


def _ends_after(event: CalendarEvent, moment: datetime) -> bool:
    """True when the event has not finished yet."""
    return _boundaries(event)[1] > moment
