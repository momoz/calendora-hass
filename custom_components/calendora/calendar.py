"""Calendar platform for Calendora.

Writable, as of the API accepting the occurrence id it was already handing out.
Before that, "move this Tuesday" could only be expressed as "move every
Tuesday", so no editing capability was declared at all.

**`scope` is the whole difficulty** (`docs/API-SURFACE.md` §7). Home Assistant
asks the user "this event, or this and all following?" and hands the answer
down as `recurrence_range`; Calendora wants that as a required body field with
three values. `_scope_for` is that translation, and getting it wrong does not
error — it silently edits the wrong number of days.

**The reply carries a new id.** `this` and `following` create a row, so the id
that comes back is not the one that was sent. Nothing here keeps the old one.

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
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from homeassistant.components.calendar import (
    EVENT_END,
    EVENT_START,
    EVENT_SUMMARY,
    CalendarEntity,
    CalendarEntityFeature,
    CalendarEvent,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import CalendoraConfigEntry
from .api import CalendoraAuthError, CalendoraConflictError, CalendoraError
from .const import DOMAIN, LOGGER, MAX_EVENT_RANGE_DAYS
from .coordinator import CalendoraDataUpdateCoordinator, member_attributes

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

    Worth knowing how thin the evidence for this would be if you went looking:
    in a live household of 220 occurrences, exactly **one** had an empty
    `attendeeIds`. The naive version would have been wrong about a single event
    and right about 219, which is precisely the ratio at which a bug survives
    casual testing, ships, and is eventually reported as "the family holiday
    doesn't show up on my calendar" months later.
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
            # exclusive. Calendora now stores all-day events that way too
            # (exclusive next midnight), so this is a **fallback**, not the
            # normal path: it catches older imported rows written under the
            # previous convention, which stored 00:00:00 to 23:59:59 on the same
            # day. Verified against live data — every current all-day occurrence
            # arrives already exclusive and does not reach this branch.
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


def _scope_for(recurrence_id: str | None, recurrence_range: str | None) -> str:
    """Translate Home Assistant's answer into Calendora's `scope`.

    Home Assistant offers a user two choices on a repeating event and encodes
    them in `recurrence_range`: `""` for this one, `"THISANDFUTURE"` for this
    and everything after. There is no third value — it has no way to say "the
    whole series including the past".

    So `all` is never emitted from here, even though the API accepts it. It is
    not ours to choose: a user who asked to change one Tuesday has not asked to
    change the ones already gone.

    A one-off carries no `recurrence_id`. `scope` is still required there, and
    all three values mean the same thing, so `all` is the honest one — nothing
    is being singled out.
    """
    if recurrence_id is None:
        return "all"
    if recurrence_range == "THISANDFUTURE":
        return "following"
    return "this"


def _wire_times(event: CalendarEvent | dict[str, Any]) -> dict[str, Any]:
    """Render start and end in the form that says what they mean.

    §7: a date is a day and an instant is a moment, and the two may not be
    mixed. Home Assistant already keeps that distinction in the type, so this is
    a straight rendering rather than a decision — which is why `isAllDay` is not
    sent at all. Sending one that disagrees with the form is a 400, and the form
    is not something to restate.
    """
    start = event[EVENT_START] if isinstance(event, dict) else event.start
    end = event[EVENT_END] if isinstance(event, dict) else event.end

    def render(value: date | datetime) -> str:
        if isinstance(value, datetime):
            return dt_util.as_utc(value).isoformat().replace("+00:00", "Z")
        return value.isoformat()

    return {"start": render(start), "end": render(end)}


class CalendoraCalendar(
    CoordinatorEntity[CalendoraDataUpdateCoordinator], CalendarEntity
):
    """Shared behaviour for every Calendora calendar.

    Subclasses differ only in which occurrences they keep, which is the one thing
    that distinguishes a household calendar from a person's.
    """

    _attr_has_entity_name = True
    _attr_supported_features = (
        CalendarEntityFeature.CREATE_EVENT
        | CalendarEntityFeature.UPDATE_EVENT
        | CalendarEntityFeature.DELETE_EVENT
    )

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

    async def _async_write(self, make_request: Any) -> Any:
        """Run one write, surface its failure, then reconcile.

        Calendora's rejections are written for the person reading them — "this
        event repeats, and a repeating series cannot be removed through this
        API … Remove it in Calendora instead" is more use than anything this
        integration could invent, so it is passed through rather than replaced.
        """
        try:
            try:
                result = await make_request()
            except CalendoraConflictError:
                # §2: the only retryable code, and safe because nothing was
                # applied — the server refuses a half-applied detach rather than
                # leaving the day showing twice.
                LOGGER.debug("Calendora reported a conflict; retrying once")
                await self.coordinator.async_refresh()
                result = await make_request()
        except CalendoraAuthError as err:
            self.coordinator.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="invalid_auth"
            ) from err
        except CalendoraError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="calendar_write_failed",
                translation_placeholders={"detail": str(err)},
            ) from err

        # `async_request_refresh` is debounced by up to ten seconds. That is
        # right for a stream event and wrong for a write the user just made:
        # add an item and it would not appear until the debounce expired, so
        # the next thing they do — tick it — fails with "unable to find item".
        # Found by installing this into a real Home Assistant; no unit test
        # sees a debouncer.
        await self.coordinator.async_refresh()
        return result

    def _attendees_for_new_event(self) -> list[str] | None:
        """Who a new event belongs to, or None to leave it to the household.

        §7 distinguishes three things and they are not interchangeable:
        omitting `attendeeIds` leaves the event with the household, `[]` says
        "everybody" deliberately, and a list names people. The household
        calendar omits; a member calendar names one person.
        """
        return None

    async def async_create_event(self, **kwargs: Any) -> None:
        """Add an event.

        The id is chosen here so a retry after a timeout lands on the same row
        rather than creating the thing twice.
        """
        fields: dict[str, Any] = {
            "title": kwargs[EVENT_SUMMARY],
            **_wire_times(kwargs),
            "timezone": str(dt_util.get_default_time_zone()),
        }
        if (attendees := self._attendees_for_new_event()) is not None:
            fields["attendeeIds"] = attendees
        for key in ("description", "location"):
            if (value := kwargs.get(key)) is not None:
                fields[key] = value

        event_id = uuid4().hex
        await self._async_write(
            lambda: self.coordinator.client.async_create_event(event_id, fields)
        )

    async def async_update_event(
        self,
        uid: str,
        event: dict[str, Any],
        recurrence_id: str | None = None,
        recurrence_range: str | None = None,
    ) -> None:
        """Change an event, or one occurrence of it.

        `uid` is the id `GET` handed out — for an occurrence, the
        `{eventId}:{occurrenceKey}` form the API now accepts back.

        The reply's `id` is deliberately not stored: `this` and `following`
        create a row, and the refresh that follows re-reads every id from the
        server rather than trusting one held here.
        """
        # `attendeeIds` is deliberately absent. §7: omitting it leaves the
        # roster alone, and this edit is about a time or a title. Sending it
        # would assert a roster nobody asked to change — and on a recurring
        # event `scope` decides how far that assertion reaches, so a
        # per-occurrence edit could quietly rewrite who is on the series.
        changes: dict[str, Any] = {
            "title": event[EVENT_SUMMARY],
            **_wire_times(event),
        }
        for key in ("description", "location"):
            if key in event:
                changes[key] = event[key]

        scope = _scope_for(recurrence_id, recurrence_range)
        await self._async_write(
            lambda: self.coordinator.client.async_update_event(uid, scope, changes)
        )

    async def async_delete_event(
        self,
        uid: str,
        recurrence_id: str | None = None,
        recurrence_range: str | None = None,
    ) -> None:
        """Remove an event.

        A repeating series is refused by the API on purpose, and the refusal
        explains itself. It reaches the user unchanged.
        """
        await self._async_write(
            lambda: self.coordinator.client.async_delete_event(uid)
        )

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
    """One person's calendar: what they are on, plus what everyone is on.

    An event created here names this member, so it lands on their calendar and
    not on everybody's. That was not possible until `attendeeIds` was accepted
    on write: before it, adding "dentist" to one person's calendar put it on all
    six, silently, and the only clue was seeing it repeated on a dashboard.
    """

    def _attendees_for_new_event(self) -> list[str]:
        """A new event here belongs to this member.

        This is what `attendeeIds` on `POST /events` bought. Before it existed,
        an event created from somebody's calendar arrived with nobody on it,
        which means the whole household — a real family added one thing to one
        person's calendar and watched it appear on all six.
        """
        return [self._member_id]

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

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Carry the member id and the shop-notification opt-in.

        This is how a blueprint identifies the person and checks their consent
        without anybody typing an identifier.
        """
        return member_attributes(self.coordinator, self._member_id)

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
