"""Tests for the clash sensor.

The definition is the whole design here: what counts as a clash decides whether
a family trusts the alert or turns it off in a week.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.calendora.binary_sensor import _first_clash, _timed_events_today
from custom_components.calendora.const import API_BASE_URL, CONF_API_KEY, DOMAIN

from .const import API_KEY, load_fixture

HOUSEHOLD_URL = f"{API_BASE_URL}/api/v1/household"
MEMBERS_URL = f"{API_BASE_URL}/api/v1/members"
EVENTS_URL = f"{API_BASE_URL}/api/v1/events"
LISTS_URL = f"{API_BASE_URL}/api/v1/lists"
STREAM_URL = f"{API_BASE_URL}/api/v1/stream"

ALEX = "binary_sensor.test_household_alex_has_a_clash_today"


def _occ(uid, start, end, attendees, all_day=False, title="x"):
    return {
        "id": uid, "eventId": uid.split(":")[0], "title": title,
        "isAllDay": all_day, "start": start, "end": end,
        "timezone": "Europe/Amsterdam", "attendeeIds": attendees,
    }


async def _setup(hass, aioclient_mock, occurrences):
    aioclient_mock.get(HOUSEHOLD_URL, json=load_fixture("household.json"))
    aioclient_mock.get(MEMBERS_URL, json=load_fixture("members.json"))
    aioclient_mock.get(EVENTS_URL, json={"occurrences": occurrences})
    aioclient_mock.get(LISTS_URL, json={"lists": []})
    aioclient_mock.get(STREAM_URL, text="", headers={"Content-Type": "text/event-stream"})
    entry = MockConfigEntry(
        domain=DOMAIN, title="Calendora", data={CONF_API_KEY: API_KEY}, version=2
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture(name="today")
def today_fixture(freezer: FrozenDateTimeFactory) -> None:
    """Freeze mid-morning, so "today" is not whatever day the suite happens to run."""
    freezer.move_to(datetime(2026, 9, 10, 8, 0, tzinfo=dt_util.UTC))


async def test_off_when_nothing_overlaps(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, today: None
) -> None:
    """A normal day is off, not unknown."""
    await _setup(hass, aioclient_mock, [
        _occ("a:1", "2026-09-10T08:00:00.000Z", "2026-09-10T09:00:00.000Z", ["mem-1"]),
        _occ("b:1", "2026-09-10T10:00:00.000Z", "2026-09-10T11:00:00.000Z", ["mem-1"]),
    ])

    assert hass.states.get(ALEX).state == STATE_OFF


async def test_on_when_two_events_overlap(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, today: None
) -> None:
    """Both sides are named, so a notification can say which."""
    await _setup(hass, aioclient_mock, [
        _occ("a:1", "2026-09-10T09:00:00.000Z", "2026-09-10T10:30:00.000Z", ["mem-1"], title="Swimming"),
        _occ("b:1", "2026-09-10T10:00:00.000Z", "2026-09-10T11:00:00.000Z", ["mem-1"], title="Dentist"),
    ])

    state = hass.states.get(ALEX)
    assert state.state == STATE_ON
    assert state.attributes["first"] == "Swimming"
    assert state.attributes["second"] == "Dentist"


async def test_back_to_back_is_not_a_clash(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, today: None
) -> None:
    """An ordinary day is one thing after another; firing on that is noise."""
    await _setup(hass, aioclient_mock, [
        _occ("a:1", "2026-09-10T09:00:00.000Z", "2026-09-10T10:00:00.000Z", ["mem-1"]),
        _occ("b:1", "2026-09-10T10:00:00.000Z", "2026-09-10T11:00:00.000Z", ["mem-1"]),
    ])

    assert hass.states.get(ALEX).state == STATE_OFF


async def test_all_day_events_do_not_clash(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, today: None
) -> None:
    """"School holidays" is not a commitment to be somewhere at 10am.

    A sensor that treats it as one is on every day of the summer, and a family
    turns it off within a week.
    """
    await _setup(hass, aioclient_mock, [
        _occ("a:1", "2026-09-09T22:00:00.000Z", "2026-09-10T22:00:00.000Z", ["mem-1"], all_day=True),
        _occ("b:1", "2026-09-10T09:00:00.000Z", "2026-09-10T10:00:00.000Z", ["mem-1"]),
    ])

    assert hass.states.get(ALEX).state == STATE_OFF


async def test_other_peoples_clashes_do_not_count(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, today: None
) -> None:
    """Robin double-booked is not Alex's problem."""
    await _setup(hass, aioclient_mock, [
        _occ("a:1", "2026-09-10T09:00:00.000Z", "2026-09-10T10:30:00.000Z", ["mem-2"]),
        _occ("b:1", "2026-09-10T10:00:00.000Z", "2026-09-10T11:00:00.000Z", ["mem-2"]),
    ])

    assert hass.states.get(ALEX).state == STATE_OFF
    assert hass.states.get("binary_sensor.test_household_robin_has_a_clash_today").state == STATE_ON


async def test_a_household_event_can_clash_with_a_personal_one(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, today: None
) -> None:
    """The attendee rule again: an event naming nobody is on everyone's day."""
    await _setup(hass, aioclient_mock, [
        _occ("a:1", "2026-09-10T09:00:00.000Z", "2026-09-10T10:30:00.000Z", [], title="Family lunch"),
        _occ("b:1", "2026-09-10T10:00:00.000Z", "2026-09-10T11:00:00.000Z", ["mem-1"], title="Dentist"),
    ])

    assert hass.states.get(ALEX).state == STATE_ON


async def test_tomorrows_clash_is_not_todays(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, today: None
) -> None:
    """Only today. A clash next Tuesday is not something to alert about now."""
    await _setup(hass, aioclient_mock, [
        _occ("a:1", "2026-09-11T09:00:00.000Z", "2026-09-11T10:30:00.000Z", ["mem-1"]),
        _occ("b:1", "2026-09-11T10:00:00.000Z", "2026-09-11T11:00:00.000Z", ["mem-1"]),
    ])

    assert hass.states.get(ALEX).state == STATE_OFF


def test_a_long_event_clashes_with_a_later_short_one() -> None:
    """Adjacent-pair comparison is not enough on its own.

    9–12, 9:30–10, 10:30–11: sorted by start, the second and third do not
    overlap each other, but both sit inside the first. Comparing only
    neighbours would miss the third.
    """
    events = _timed_events_today(
        [
            _occ("a:1", "2026-09-10T09:00:00.000Z", "2026-09-10T12:00:00.000Z", ["m"], title="Long"),
            _occ("b:1", "2026-09-10T09:30:00.000Z", "2026-09-10T10:00:00.000Z", ["m"], title="Short"),
            _occ("c:1", "2026-09-10T10:30:00.000Z", "2026-09-10T11:00:00.000Z", ["m"], title="Later"),
        ],
        "m",
        __import__("datetime").date(2026, 9, 10),
    )

    assert _first_clash(events) == ("Long", "Short")
    # Drop the middle one: the long event must still clash with the later one.
    assert _first_clash([events[0], events[2]]) == ("Long", "Later")
