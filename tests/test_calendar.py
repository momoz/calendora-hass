"""Tests for the Calendora calendar entity.

Built on synthetic responses shaped by `docs/API-SURFACE.md` §4a. The weight is
on the all-day conversion, because §4a hands over instants even for all-day
events and says the day must be derived in the *event's* timezone. Getting that
wrong moves a birthday by a day for half the planet, and it is invisible from
whichever timezone the author happens to live in.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEntityFeature,
    CalendarEvent,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_component import DATA_INSTANCES
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)

from custom_components.calendora.calendar import _as_calendar_event
from custom_components.calendora.const import API_BASE_URL, CONF_API_KEY, DOMAIN

from .const import API_KEY, load_fixture

ENTITY_ID = "calendar.test_household"

HOUSEHOLD_URL = f"{API_BASE_URL}/api/v1/household"
MEMBERS_URL = f"{API_BASE_URL}/api/v1/members"
EVENTS_URL = f"{API_BASE_URL}/api/v1/events"
STREAM_URL = f"{API_BASE_URL}/api/v1/stream"

AMSTERDAM = ZoneInfo("Europe/Amsterdam")
NEW_YORK = ZoneInfo("America/New_York")


@pytest.fixture(name="setup_calendar")
async def setup_calendar_fixture(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> MockConfigEntry:
    """Load the integration against the synthetic household."""
    aioclient_mock.get(HOUSEHOLD_URL, json=load_fixture("household.json"))
    aioclient_mock.get(MEMBERS_URL, json=load_fixture("members.json"))
    aioclient_mock.get(EVENTS_URL, json=load_fixture("events.json"))
    aioclient_mock.get(STREAM_URL, text="", headers={"Content-Type": "text/event-stream"})

    entry = MockConfigEntry(
        domain=DOMAIN, title="Calendora", data={CONF_API_KEY: API_KEY}, version=2
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _events(
    hass: HomeAssistant, start: datetime, end: datetime
) -> list[CalendarEvent]:
    """Real `CalendarEvent` objects — not the service, which stringifies them."""
    entity: CalendarEntity = hass.data[DATA_INSTANCES]["calendar"].get_entity(ENTITY_ID)
    assert entity is not None
    return await entity.async_get_events(hass, start, end)


def _is_plain_date(value: object) -> bool:
    """True for a `date` that is not also a `datetime` — the all-day contract."""
    return isinstance(value, date) and not isinstance(value, datetime)


def _one(events: list[CalendarEvent], uid: str) -> CalendarEvent:
    matches = [event for event in events if event.uid == uid]
    assert len(matches) == 1, f"expected one {uid}, got {len(matches)}"
    return matches[0]


async def test_entity_uses_the_household_id(
    hass: HomeAssistant, setup_calendar: MockConfigEntry
) -> None:
    """§4a: `household.id` is the identity, not the key and not the entry id."""
    entity_entry = er.async_get(hass).async_get(ENTITY_ID)

    assert entity_entry is not None
    assert entity_entry.unique_id == "hh-test-0001-calendar"
    assert API_KEY not in entity_entry.unique_id


async def test_declares_no_write_features(
    hass: HomeAssistant, setup_calendar: MockConfigEntry
) -> None:
    """No write routes exist yet (§7), so no capability may be claimed."""
    state = hass.states.get(ENTITY_ID)
    supported = state.attributes.get("supported_features", 0)

    assert supported == 0
    for feature in CalendarEntityFeature:
        assert not supported & feature


async def test_all_day_event_becomes_a_date(
    hass: HomeAssistant, setup_calendar: MockConfigEntry
) -> None:
    """An all-day instant pair becomes plain dates, resolved in the event's zone.

    The fixture's event is 2026-08-10 in Europe/Amsterdam, which on the wire is
    2026-08-09T22:00Z. Read in UTC it is the 9th; read correctly it is the 10th.
    """
    events = await _events(
        hass,
        datetime(2026, 8, 1, tzinfo=dt_util.UTC),
        datetime(2026, 8, 12, tzinfo=dt_util.UTC),
    )

    event = _one(events, "evt-allday:2026-08-10")
    assert _is_plain_date(event.start)
    assert _is_plain_date(event.end)
    assert event.start == date(2026, 8, 10)
    assert event.end == date(2026, 8, 11)


@pytest.mark.parametrize(
    "time_zone",
    [
        "UTC",
        "Pacific/Kiritimati",
        "Pacific/Midway",
        "Australia/Sydney",
        "America/Los_Angeles",
        "Europe/Amsterdam",
    ],
)
async def test_all_day_date_is_the_events_zone_not_the_viewers(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, time_zone: str
) -> None:
    """The date must not move with the viewer.

    Kiritimati (UTC+14) and Midway (UTC-11) are 25 hours apart. If the
    conversion ever uses the viewer's zone — or UTC — one of these shifts, and
    the person who notices is a stranger whose child's birthday moved.
    """
    await hass.config.async_set_time_zone(time_zone)

    aioclient_mock.get(HOUSEHOLD_URL, json=load_fixture("household.json"))
    aioclient_mock.get(MEMBERS_URL, json=load_fixture("members.json"))
    aioclient_mock.get(EVENTS_URL, json=load_fixture("events.json"))
    aioclient_mock.get(STREAM_URL, text="", headers={"Content-Type": "text/event-stream"})
    entry = MockConfigEntry(
        domain=DOMAIN, title="Calendora", data={CONF_API_KEY: API_KEY}, version=2
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    local = dt_util.get_time_zone(time_zone)
    events = await _events(
        hass,
        datetime(2026, 8, 1, tzinfo=local),
        datetime(2026, 8, 20, tzinfo=local),
    )

    single = _one(events, "evt-allday:2026-08-10")
    assert single.start == date(2026, 8, 10), f"shifted in {time_zone}"
    assert _is_plain_date(single.start), f"became an instant in {time_zone}"

    camping = _one(events, "evt-camping:2026-08-14")
    assert camping.start == date(2026, 8, 14), f"shifted in {time_zone}"
    assert camping.end == date(2026, 8, 17), f"multi-day end wrong in {time_zone}"


async def test_timed_event_keeps_its_instant(
    hass: HomeAssistant, setup_calendar: MockConfigEntry
) -> None:
    """A timed event is a moment, and a moment is the same moment everywhere."""
    events = await _events(
        hass,
        datetime(2026, 11, 1, tzinfo=dt_util.UTC),
        datetime(2026, 11, 8, tzinfo=dt_util.UTC),
    )

    piano = _one(events, "evt-piano:2026-11-04")
    assert isinstance(piano.start, datetime)
    assert piano.start.tzinfo is not None
    # 14:00Z on 4 November is 09:00 in New York, which is where it was authored
    # — after US DST ended on the 1st, so the offset is -05:00.
    assert piano.start.astimezone(NEW_YORK).hour == 9
    assert piano.start.astimezone(NEW_YORK).utcoffset() == timedelta(hours=-5)


async def test_start_and_end_types_always_match(
    hass: HomeAssistant, setup_calendar: MockConfigEntry
) -> None:
    """Both dates or both datetimes, and tz-aware. Home Assistant raises otherwise."""
    events = await _events(
        hass,
        datetime(2026, 8, 1, tzinfo=dt_util.UTC),
        datetime(2026, 12, 1, tzinfo=dt_util.UTC),
    )
    assert events

    for event in events:
        assert _is_plain_date(event.start) == _is_plain_date(event.end), (
            f"mixed types in {event.uid}"
        )
        if not _is_plain_date(event.start):
            assert event.start.tzinfo is not None
            assert event.end.tzinfo is not None


async def test_window_is_requested_as_days_in_the_key_owner_zone(
    hass: HomeAssistant, setup_calendar: MockConfigEntry, aioclient_mock
) -> None:
    """§4: `from`/`to` are days, and the day depends on whose zone resolves it."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(EVENTS_URL, json={"occurrences": []})

    # 23:30 UTC on the 9th is already the 10th in Amsterdam, which is the key
    # owner's zone in the fixture.
    await _events(
        hass,
        datetime(2026, 8, 9, 23, 30, tzinfo=dt_util.UTC),
        datetime(2026, 8, 10, 23, 30, tzinfo=dt_util.UTC),
    )

    query = aioclient_mock.mock_calls[0][1].query
    assert query["from"] == "2026-08-10"
    assert "T" not in query["from"]


async def test_unusable_occurrence_does_not_break_the_calendar() -> None:
    """One malformed occurrence must not take out the whole calendar."""
    assert _as_calendar_event({"id": "x", "isAllDay": False}) is None
    assert _as_calendar_event({"id": "x", "start": "not a date", "end": "also not"}) is None


def test_unknown_event_timezone_falls_back_to_the_written_offset() -> None:
    """An unrecognised zone must not silently become the viewer's.

    tzdata varies between machines. If a zone name cannot be resolved, the
    offset written into the timestamp is still the authoring side's intent —
    the viewer's zone is the one answer guaranteed to be wrong.
    """
    event = _as_calendar_event(
        {
            "id": "evt-x:1",
            "title": "Somewhere odd",
            "isAllDay": True,
            "start": "2026-08-09T22:00:00.000Z",
            "end": "2026-08-10T22:00:00.000Z",
            "timezone": "Mars/Olympus_Mons",
        }
    )

    assert event is not None
    # Resolved with the written offset (UTC here), so the 9th — not whatever
    # the machine running the test happens to be set to.
    assert event.start == date(2026, 8, 9)


async def test_empty_window_returns_nothing(
    hass: HomeAssistant, setup_calendar: MockConfigEntry, aioclient_mock
) -> None:
    """A quiet week is empty, not an error."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(EVENTS_URL, json={"occurrences": []})

    assert (
        await _events(
            hass,
            datetime(2027, 6, 1, tzinfo=dt_util.UTC),
            datetime(2027, 6, 8, tzinfo=dt_util.UTC),
        )
        == []
    )


async def test_window_cache_is_keyed_on_the_range_not_on_being_in_flight(
    hass: HomeAssistant, setup_calendar: MockConfigEntry, aioclient_mock
) -> None:
    """Two entities asking for *different* months must not share one answer.

    Collapsing four identical requests into one is the point of the cache.
    Collapsing two *different* ranges into one would serve the second entity the
    first one's month, and it would look entirely plausible — a calendar showing
    the wrong month's events with no error anywhere. Keyed on the range, so it
    cannot happen; asserted here so a refactor cannot make it possible.
    """
    coordinator = setup_calendar.runtime_data
    aioclient_mock.clear_requests()

    august = {"occurrences": [{"id": "aug:1", "start": "2026-08-05T09:00:00.000Z",
                               "end": "2026-08-05T10:00:00.000Z", "title": "August"}]}
    september = {"occurrences": [{"id": "sep:1", "start": "2026-09-05T09:00:00.000Z",
                                  "end": "2026-09-05T10:00:00.000Z", "title": "September"}]}

    async def _by_range(method, url, data):
        return AiohttpClientMockResponse(
            method, url, json=august if url.query["from"].startswith("2026-08") else september
        )

    aioclient_mock.get(EVENTS_URL, side_effect=_by_range)

    first = await coordinator.async_fetch_window(date(2026, 8, 1), date(2026, 8, 31))
    second = await coordinator.async_fetch_window(date(2026, 9, 1), date(2026, 9, 30))

    assert [o["id"] for o in first] == ["aug:1"]
    assert [o["id"] for o in second] == ["sep:1"], "served another range's window"
    assert len(aioclient_mock.mock_calls) == 2, "different ranges must not collapse"


async def test_identical_ranges_do_collapse(
    hass: HomeAssistant, setup_calendar: MockConfigEntry, aioclient_mock
) -> None:
    """The case the cache exists for: one dashboard render, one request."""
    coordinator = setup_calendar.runtime_data
    aioclient_mock.clear_requests()
    aioclient_mock.get(EVENTS_URL, json={"occurrences": []})

    window = (date(2026, 8, 1), date(2026, 8, 31))
    for _ in range(4):
        await coordinator.async_fetch_window(*window)

    assert len(aioclient_mock.mock_calls) == 1


async def test_a_stream_change_invalidates_the_cache(
    hass: HomeAssistant, setup_calendar: MockConfigEntry, aioclient_mock
) -> None:
    """A push that arrives and changes nothing on screen is worse than a poll."""
    coordinator = setup_calendar.runtime_data
    aioclient_mock.clear_requests()
    aioclient_mock.get(EVENTS_URL, json={"occurrences": []})

    window = (date(2026, 8, 1), date(2026, 8, 31))
    await coordinator.async_fetch_window(*window)
    coordinator._window_cache.clear()  # what the stream's `changed` handler does
    await coordinator.async_fetch_window(*window)

    assert len(aioclient_mock.mock_calls) == 2
