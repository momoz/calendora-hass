"""Sensor platform for Calendora.

Per member: **when their next event starts**, and **when they have to leave for
the next one with a drive time.** Both `device_class: timestamp`, so a dashboard
renders "in 20 minutes" and an automation can compare without parsing.

Per household: **tonight's dinner**, the string every Calendora surface shows.

**`leave_by` is the event's drive, not a route from where the person is.**
This file used to decline the sensor on exactly that ground. What changed is
that Calendora now says where the drive is from (`travelFrom`, §4) and defines
the leave time itself — `leaveAt` is `start` minus `travelMinutes` (§4,
`GET /events/{id}/leave-by`) — so the number is Calendora's, worked out the way
Calendora works it out, and `travel_from` says what it assumes. It is still not
live traffic and never claims to be.

The time is computed from the occurrence, so the state never waits on a second
request; `/leave-by` is asked only for `words`, the sentence the Today card
shows. See `CalendoraDataUpdateCoordinator._async_leave_by`.

**`chores_due`** counts the items Calendora calls chores — `repeats: true` —
that are due today or earlier in the key owner's zone (§6, GAP-019).

**A `busy` binary sensor.** A calendar entity's own state is already `on` while
an event is running, so a `binary_sensor.<member>_busy` would duplicate
`calendar.<household>_<member>` exactly — and give people two things to write
automations against that can disagree with each other. Two sources of one truth
is worse than one, especially when the second is derived and can lag. Use the
calendar entity's state.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import CalendoraConfigEntry
from .calendar import _belongs_to_member, _tag_names, next_driven_occurrence
from .const import DOMAIN
from .coordinator import CalendoraDataUpdateCoordinator, member_attributes

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CalendoraConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one next-event sensor per member, including members added later."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new_members() -> None:
        new: list[SensorEntity] = []
        for member in coordinator.data.members:
            member_id = member.get("id")
            if not member_id or member_id in known:
                continue
            known.add(member_id)
            new.append(CalendoraNextEventSensor(coordinator, member))
            new.append(CalendoraLeaveBySensor(coordinator, member))
        # Only once the key can read meals: a dinner sensor that is permanently
        # unknown would read as "nothing planned", which is a different fact.
        if "chores" not in known:
            known.add("chores")
            new.append(CalendoraChoresDueSensor(coordinator))
        if coordinator.data.dinner is not None and "dinner" not in known:
            known.add("dinner")
            new.append(CalendoraDinnerSensor(coordinator))
        if new:
            async_add_entities(new)

    _add_new_members()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_members))


class CalendoraNextEventSensor(
    CoordinatorEntity[CalendoraDataUpdateCoordinator], SensorEntity
):
    """When this member's next event starts."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "next_event"

    def __init__(
        self, coordinator: CalendoraDataUpdateCoordinator, member: dict[str, Any]
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._member_id: str = member["id"]
        self._member_name: str = member.get("name") or "Unknown"
        self._attr_translation_placeholders = {"member": self._member_name}
        self._attr_unique_id = (
            f"{coordinator.data.household_id}-next-event-{self._member_id}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.data.household_id)},
            entry_type=DeviceEntryType.SERVICE,
            name=coordinator.data.household_name,
            manufacturer="Calendora",
        )

    @property
    def available(self) -> bool:
        """Unavailable once the member is gone from the household."""
        return super().available and any(
            member.get("id") == self._member_id
            for member in self.coordinator.data.members
        )

    def _next_occurrence(self) -> dict[str, Any] | None:
        """Return this member's next occurrence that has not started yet.

        "Next" means the next one to *start*, not the next one that is relevant:
        an event already under way is not upcoming, and reporting its start time
        as the next event would make a countdown card count up.

        §4a promises occurrences arrive sorted by `start`, so the first future
        one wins and there is nothing to sort here.
        """
        now = dt_util.now()
        for occurrence in self.coordinator.data.occurrences:
            if not _belongs_to_member(occurrence, self._member_id):
                continue
            start = occurrence.get("start")
            if not start:
                continue
            parsed = dt_util.parse_datetime(start)
            if parsed is not None and parsed > now:
                return occurrence
        return None

    @property
    def native_value(self) -> datetime | None:
        """Return the start of the next event, or None when nothing is coming.

        The raw instant from the API is used rather than the calendar entity's
        converted value. A timestamp sensor needs an instant, and an all-day
        event's `date` has none — going through the date conversion and back
        would invent a midnight that nobody chose.
        """
        occurrence = self._next_occurrence()
        if occurrence is None:
            return None
        return dt_util.parse_datetime(occurrence["start"])

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose enough to render a card without a second lookup.

        Kept small on purpose: attributes are written to the state machine on
        every update and recorded in the database, so this is not the place for
        the whole event.
        """
        attributes = member_attributes(self.coordinator, self._member_id)
        occurrence = self._next_occurrence()
        if occurrence is None:
            return attributes
        return {
            **attributes,
            "summary": occurrence.get("title") or "",
            "location": occurrence.get("location"),
            "all_day": bool(occurrence.get("isAllDay")),
            "shared_with_household": not occurrence.get("attendeeIds"),
            "tags": _tag_names(occurrence),
        }


class CalendoraLeaveBySensor(CalendoraNextEventSensor):
    """When this member has to leave for their next event with a drive time."""

    _attr_translation_key = "leave_by"

    def __init__(
        self, coordinator: CalendoraDataUpdateCoordinator, member: dict[str, Any]
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, member)
        self._attr_unique_id = (
            f"{coordinator.data.household_id}-leave-by-{self._member_id}"
        )

    def _next_occurrence(self) -> dict[str, Any] | None:
        """See `next_driven_occurrence` for what counts."""
        return next_driven_occurrence(
            self.coordinator.data.occurrences, self._member_id, dt_util.now()
        )

    @property
    def native_value(self) -> datetime | None:
        """`start` minus `travelMinutes` — §4's definition of `leaveAt`."""
        occurrence = self._next_occurrence()
        if occurrence is None:
            return None
        start = dt_util.parse_datetime(occurrence["start"])
        return start - timedelta(minutes=occurrence["travelMinutes"])

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Which event, how long, and from where Calendora assumed."""
        attributes = member_attributes(self.coordinator, self._member_id)
        occurrence = self._next_occurrence()
        if occurrence is None:
            return attributes
        return {
            **attributes,
            "summary": occurrence.get("title") or "",
            "event_start": dt_util.parse_datetime(occurrence["start"]),
            "travel_minutes": occurrence["travelMinutes"],
            # "home", an address, or None for a number somebody typed. Passed
            # through as given; parsing it is what §4 says not to do.
            "travel_from": occurrence.get("travelFrom"),
            "event_id": occurrence.get("id"),
            # Calendora's own sentence, for a speaker or a notification. None
            # when `/leave-by` did not answer — the time above still stands.
            "words": (
                self.coordinator.data.leave_by.get(occurrence.get("id")) or {}
            ).get("words"),
        }


def _serve_instant(day: str | None, serve_at: str | None, tz: str | None) -> datetime | None:
    """§6a: `serveAt` is a wall time — read it in `serveTz`, on that `day`."""
    if not day or not serve_at or not tz:
        return None
    try:
        zone = ZoneInfo(tz)
        return datetime.fromisoformat(f"{day}T{serve_at}").replace(tzinfo=zone)
    except (ValueError, ZoneInfoNotFoundError):
        return None


class CalendoraDinnerSensor(
    CoordinatorEntity[CalendoraDataUpdateCoordinator], SensorEntity
):
    """Tonight's dinner, as the Today card says it."""

    _attr_has_entity_name = True
    _attr_translation_key = "tonights_dinner"

    def __init__(self, coordinator: CalendoraDataUpdateCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.data.household_id}-tonights-dinner"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.data.household_id)},
            entry_type=DeviceEntryType.SERVICE,
            name=coordinator.data.household_name,
            manufacturer="Calendora",
        )

    @property
    def available(self) -> bool:
        """Unavailable if the key loses `meals:read` after set-up."""
        return super().available and self.coordinator.data.dinner is not None

    @property
    def native_value(self) -> str | None:
        """§6a: `headline` is the sensor's state — `"Not planned"` when nothing is.

        Used as given rather than rebuilt from the meals. Every Calendora
        surface shows this exact string, and a second rendering here would be
        the one place in the house that words dinner differently.
        """
        dinner = self.coordinator.data.dinner or {}
        headline = dinner.get("headline")
        # A state longer than 255 characters is refused by Home Assistant, and
        # a refused state is an entity that stops updating.
        return headline[:255] if isinstance(headline, str) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Enough to announce it or start the oven, without a second lookup."""
        dinner = self.coordinator.data.dinner
        if not dinner:
            return None
        day = dinner.get("day")
        meals = [
            {
                "headline": meal.get("headline"),
                "kind": meal.get("kind"),
                "who": meal.get("ownerPhrase"),
                "diners": (meal.get("diners") or {}).get("names"),
                "serve_at": _serve_instant(day, meal.get("serveAt"), meal.get("serveTz")),
                "place": meal.get("placeText"),
                # §6a: the sentence "for a voice answer". The one to hand a
                # TTS action, rather than the headline with its middots.
                "sentence": meal.get("sentence"),
            }
            for meal in dinner.get("meals") or []
            if isinstance(meal, dict)
        ]
        return {
            "day": day,
            "status": dinner.get("state"),
            "serve_at": next((m["serve_at"] for m in meals if m["serve_at"]), None),
            "meals": meals,
        }


def _due_day(due: Any, zone: ZoneInfo) -> date | None:
    """§6: `due` is a day or an instant, and the form is the meaning."""
    if not isinstance(due, str):
        return None
    if len(due) == 10:
        try:
            return date.fromisoformat(due)
        except ValueError:
            return None
    instant = dt_util.parse_datetime(due)
    return instant.astimezone(zone).date() if instant else None


class CalendoraChoresDueSensor(
    CoordinatorEntity[CalendoraDataUpdateCoordinator], SensorEntity
):
    """How many chores are due today or overdue, with the chores themselves."""

    _attr_has_entity_name = True
    _attr_translation_key = "chores_due"

    def __init__(self, coordinator: CalendoraDataUpdateCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.data.household_id}-chores-due"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.data.household_id)},
            entry_type=DeviceEntryType.SERVICE,
            name=coordinator.data.household_name,
            manufacturer="Calendora",
        )

    def _items(self) -> list[dict[str, Any]] | None:
        """The open chores due by today, or None when Calendora cannot say.

        **None, not zero, when an item has no `repeats` at all.** The field
        reached the extract before it reached production (web v2610.0453 lacks
        it), and §9 says a documented field is always present on a read — so
        its absence means a server that cannot tell a chore from a to-do. A
        count of 0 there would be a confident wrong answer: "nothing to do"
        on a day the bins go out.

        Today is the key owner's, as §6 defines it — the zone Home Assistant
        is in can differ, and a chore due "today" in Calendora must be due
        today here too.
        """
        try:
            zone = ZoneInfo(self.coordinator.data.key_owner_timezone)
        except (ValueError, ZoneInfoNotFoundError):
            zone = ZoneInfo("UTC")
        today = dt_util.now().astimezone(zone).date()
        due: list[dict[str, Any]] = []
        for held in self.coordinator.data.lists.values():
            for item in held["items"]:
                if "repeats" not in item:
                    return None
                if not item["repeats"] or item.get("isChecked"):
                    continue
                day = _due_day(item.get("due"), zone)
                if day is not None and day <= today:
                    due.append(
                        {
                            "summary": item.get("text") or "",
                            "due": item.get("due"),
                            "list": held["list"].get("name"),
                            "assignee": item.get("assigneeName"),
                        }
                    )
        return due

    @property
    def native_value(self) -> int | None:
        """The count; unknown when the server cannot tell chores apart."""
        items = self._items()
        return None if items is None else len(items)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """The chores, so a card or an announcement can name them."""
        items = self._items()
        return None if items is None else {"items": items}
