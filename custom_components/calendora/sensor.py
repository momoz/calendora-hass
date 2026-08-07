"""Sensor platform for Calendora.

One sensor per member: **when their next event starts.** `device_class:
timestamp`, so a dashboard renders it as "in 20 minutes" and an automation can
compare it directly instead of parsing a string.

`leave_by` is deliberately absent. `GET /api/v1/events/{id}/leave-by` is listed
under §7 as not built, and there is no honest way to derive a leave time here:
`travelMinutes` is a property of the event, not a route from wherever the person
currently is, and subtracting it would produce a number that looks authoritative
and is not.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
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
        occurrence = self._next_occurrence()
        if occurrence is None:
            return None
        return {
            "summary": occurrence.get("title") or "",
            "location": occurrence.get("location"),
            "all_day": bool(occurrence.get("isAllDay")),
            "shared_with_household": not occurrence.get("attendeeIds"),
        }
