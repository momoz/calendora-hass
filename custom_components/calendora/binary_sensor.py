"""Binary sensor platform for Calendora.

One sensor per member: **do two of their events overlap today?**

This is the thing a family calendar exists to catch, and the thing nobody
notices until the morning of. It is on when the same person is expected in two
places at once, and its attributes name both so a notification can say which.

What "clash" means here, precisely, because a looser definition produces an
alert nobody trusts:

- **Timed events only.** An all-day event is not a commitment to be somewhere at
  a moment, so "school holidays" overlapping "dentist at 10" is not a clash. A
  sensor that fires on that is one a family turns off within a week.
- **Touching is not overlapping.** An event ending at 10:00 and the next
  starting at 10:00 is a normal day, not a conflict.
- **Today in the household's own timezone**, not the viewer's — the same
  reasoning as everywhere else in this integration.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import CalendoraConfigEntry
from .calendar import _belongs_to_member
from .const import DOMAIN
from .coordinator import CalendoraDataUpdateCoordinator

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CalendoraConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one clash sensor per member, including members added later."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new_members() -> None:
        new = [
            CalendoraClashSensor(coordinator, member)
            for member in coordinator.data.members
            if (member_id := member.get("id"))
            and member_id not in known
            and not known.add(member_id)
        ]
        if new:
            async_add_entities(new)

    _add_new_members()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_members))


def _timed_events_today(
    occurrences: list[dict[str, Any]], member_id: str, today: date
) -> list[tuple[datetime, datetime, str]]:
    """Return this member's timed events that touch today, sorted by start."""
    found: list[tuple[datetime, datetime, str]] = []

    for occurrence in occurrences:
        if occurrence.get("isAllDay"):
            continue
        if not _belongs_to_member(occurrence, member_id):
            continue

        start = dt_util.parse_datetime(occurrence.get("start") or "")
        end = dt_util.parse_datetime(occurrence.get("end") or "")
        if start is None or end is None:
            continue

        # Resolved in the event's own zone, so an evening event does not slide
        # into tomorrow for a household that lives east of UTC.
        try:
            zone = ZoneInfo(occurrence.get("timezone") or "")
        except (ZoneInfoNotFoundError, ValueError):
            zone = start.tzinfo

        if start.astimezone(zone).date() == today or end.astimezone(zone).date() == today:
            found.append((start, end, occurrence.get("title") or ""))

    return sorted(found)


def _first_clash(
    events: list[tuple[datetime, datetime, str]],
) -> tuple[str, str] | None:
    """Return the first overlapping pair, or None.

    Sorted by start, so only adjacent pairs need comparing against the furthest
    end seen so far — an earlier long event can overlap a later short one.
    `>` rather than `>=` because back-to-back is not a clash.
    """
    latest_end: datetime | None = None
    latest_title = ""

    for start, end, title in events:
        if latest_end is not None and latest_end > start:
            return latest_title, title
        if latest_end is None or end > latest_end:
            latest_end, latest_title = end, title

    return None


class CalendoraClashSensor(
    CoordinatorEntity[CalendoraDataUpdateCoordinator], BinarySensorEntity
):
    """On when this member is expected in two places at once today."""

    _attr_has_entity_name = True
    _attr_translation_key = "conflict_today"

    def __init__(
        self, coordinator: CalendoraDataUpdateCoordinator, member: dict[str, Any]
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._member_id: str = member["id"]
        self._attr_translation_placeholders = {"member": member.get("name") or "Unknown"}
        self._attr_unique_id = (
            f"{coordinator.data.household_id}-conflict-{self._member_id}"
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

    def _today(self) -> date:
        try:
            zone = ZoneInfo(self.coordinator.data.key_owner_timezone)
        except (ZoneInfoNotFoundError, ValueError):
            zone = dt_util.get_default_time_zone()
        return dt_util.now().astimezone(zone).date()

    def _clash(self) -> tuple[str, str] | None:
        return _first_clash(
            _timed_events_today(
                self.coordinator.data.occurrences, self._member_id, self._today()
            )
        )

    @property
    def is_on(self) -> bool:
        """True when two of today's timed events overlap."""
        return self._clash() is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Name both sides of the clash, so a notification can be specific.

        "Robin has a clash today" sends someone to open the app. "Swimming
        overlaps the dentist" does not.
        """
        clash = self._clash()
        if clash is None:
            return None
        return {"first": clash[0], "second": clash[1]}
