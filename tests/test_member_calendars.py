"""Tests for per-member calendars.

The rule under test is small and easy to get wrong: an occurrence belongs on a
member's calendar if it names them **or if it names nobody at all**, because §4a
says an empty `attendeeIds` means the whole household.

The naive implementation — keep an occurrence only when `attendeeIds` contains
the member — passes a superficial look at any of these calendars, because each
one still has events on it. What it silently removes is everything the family
does together. Several tests here are written specifically so that they fail
under that version; `test_naive_membership_filter_would_fail_these` states the
trap outright so a future reader cannot "simplify" it back.

Fixture membership:
  fixture-allday   attendeeIds []        -> household-wide
  fixture-ferry    attendeeIds []        -> household-wide
  fixture-camping  attendeeIds [mem-1]   -> Alex only
  fixture-piano    attendeeIds [mem-2]   -> Robin only
"""

from __future__ import annotations

from datetime import datetime

import pytest
from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_component import DATA_INSTANCES
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.calendora.calendar import _belongs_to_member
from custom_components.calendora.const import API_BASE_URL, CONF_API_KEY, DOMAIN

from .const import API_KEY, load_fixture

HOUSEHOLD_URL = f"{API_BASE_URL}/api/v1/household"
MEMBERS_URL = f"{API_BASE_URL}/api/v1/members"
EVENTS_URL = f"{API_BASE_URL}/api/v1/events"
STREAM_URL = f"{API_BASE_URL}/api/v1/stream"

HOUSEHOLD_CALENDAR = "calendar.test_household"
ALEX = "calendar.test_household_alex"
ROBIN = "calendar.test_household_robin"
BISCUIT = "calendar.test_household_biscuit"

WINDOW = (
    datetime(2026, 8, 1, tzinfo=dt_util.UTC),
    datetime(2026, 12, 1, tzinfo=dt_util.UTC),
)


def _mock_all(aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(HOUSEHOLD_URL, json=load_fixture("household.json"))
    aioclient_mock.get(MEMBERS_URL, json=load_fixture("members.json"))
    aioclient_mock.get(EVENTS_URL, json=load_fixture("events.json"))
    aioclient_mock.get(STREAM_URL, text="", headers={"Content-Type": "text/event-stream"})


@pytest.fixture(name="setup_members")
async def setup_members_fixture(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> MockConfigEntry:
    """Load the integration with three members."""
    _mock_all(aioclient_mock)
    entry = MockConfigEntry(
        domain=DOMAIN, title="Calendora", data={CONF_API_KEY: API_KEY}, version=2
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _uids(hass: HomeAssistant, entity_id: str) -> set[str]:
    entity: CalendarEntity = hass.data[DATA_INSTANCES]["calendar"].get_entity(entity_id)
    assert entity is not None, f"{entity_id} does not exist"
    events: list[CalendarEvent] = await entity.async_get_events(hass, *WINDOW)
    return {event.uid for event in events}


async def test_one_calendar_per_member_plus_the_household(
    hass: HomeAssistant, setup_members: MockConfigEntry
) -> None:
    """Three members and a household calendar, pets included."""
    calendars = set(hass.states.async_entity_ids("calendar"))

    assert calendars == {HOUSEHOLD_CALENDAR, ALEX, ROBIN, BISCUIT}


async def test_member_calendar_has_their_events_and_the_shared_ones(
    hass: HomeAssistant, setup_members: MockConfigEntry
) -> None:
    """Alex gets the camping trip *and* everything the household does."""
    assert await _uids(hass, ALEX) == {
        "evt-camping:2026-08-14",
        "evt-allday:2026-08-10",
        "evt-ferry:2026-08-20",
    }


async def test_member_calendar_excludes_other_peoples_events(
    hass: HomeAssistant, setup_members: MockConfigEntry
) -> None:
    """Robin's piano lesson is not on Alex's calendar."""
    assert "evt-piano:2026-11-04" not in await _uids(hass, ALEX)
    assert "evt-camping:2026-08-14" not in await _uids(hass, ROBIN)


async def test_member_with_no_events_of_their_own_still_sees_shared_ones(
    hass: HomeAssistant, setup_members: MockConfigEntry
) -> None:
    """**This is the test the naive implementation fails.**

    Biscuit is named on nothing. Under a membership-only filter his calendar is
    empty and looks perfectly reasonable — a pet with no appointments. In fact
    the household is going camping and taking a ferry, and he should see both.
    """
    assert await _uids(hass, BISCUIT) == {
        "evt-allday:2026-08-10",
        "evt-ferry:2026-08-20",
    }


async def test_household_wide_events_appear_on_every_calendar(
    hass: HomeAssistant, setup_members: MockConfigEntry
) -> None:
    """The half of family life that is shared is on everybody's calendar."""
    shared = {"evt-allday:2026-08-10", "evt-ferry:2026-08-20"}

    for entity_id in (ALEX, ROBIN, BISCUIT):
        assert shared <= await _uids(hass, entity_id), f"{entity_id} lost shared events"


async def test_household_calendar_keeps_everything(
    hass: HomeAssistant, setup_members: MockConfigEntry
) -> None:
    """No filtering at all on the household calendar."""
    assert await _uids(hass, HOUSEHOLD_CALENDAR) == {
        "evt-allday:2026-08-10",
        "evt-camping:2026-08-14",
        "evt-piano:2026-11-04",
        "evt-ferry:2026-08-20",
    }


def test_naive_membership_filter_would_fail_these() -> None:
    """State the trap directly, so nobody "simplifies" the rule back.

    `member_id in attendeeIds` is the obvious implementation and it is wrong:
    it drops every household-wide occurrence from every member's calendar.
    """
    household_wide = {"id": "x", "attendeeIds": []}
    alexs_own = {"id": "y", "attendeeIds": ["mem-1"]}

    # The correct rule.
    assert _belongs_to_member(household_wide, "mem-1")
    assert _belongs_to_member(household_wide, "mem-3")
    assert _belongs_to_member(alexs_own, "mem-1")
    assert not _belongs_to_member(alexs_own, "mem-3")

    # The naive rule, shown failing on the case that matters.
    naive = lambda occ, mid: mid in (occ.get("attendeeIds") or [])
    assert not naive(household_wide, "mem-1")
    assert _belongs_to_member(household_wide, "mem-1") != naive(household_wide, "mem-1")


async def test_missing_attendee_ids_is_treated_as_household_wide(
    hass: HomeAssistant, setup_members: MockConfigEntry
) -> None:
    """An absent key is not a different meaning from an empty list."""
    assert _belongs_to_member({"id": "x"}, "mem-1")
    assert _belongs_to_member({"id": "x", "attendeeIds": None}, "mem-1")


async def test_member_names_come_from_the_api_not_from_people(
    hass: HomeAssistant, setup_members: MockConfigEntry
) -> None:
    """§4a: `name` is already resolved, including a display-name override."""
    state = hass.states.get(ALEX)

    assert state is not None
    assert state.attributes["friendly_name"] == "Test Household Alex"


async def test_member_calendars_are_keyed_on_membership_id(
    hass: HomeAssistant, setup_members: MockConfigEntry
) -> None:
    """Stable identity, and never the API key."""
    registry = er.async_get(hass)

    entry = registry.async_get(ALEX)
    assert entry is not None
    assert entry.unique_id == "hh-test-0001-calendar-mem-1"
    assert API_KEY not in entry.unique_id


async def test_a_member_added_later_gets_a_calendar(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A new child in Calendora should not need a Home Assistant restart."""
    aioclient_mock.get(HOUSEHOLD_URL, json=load_fixture("household.json"))
    aioclient_mock.get(MEMBERS_URL, json={"members": load_fixture("members.json")["members"][:1]})
    aioclient_mock.get(EVENTS_URL, json=load_fixture("events.json"))
    aioclient_mock.get(STREAM_URL, text="", headers={"Content-Type": "text/event-stream"})

    entry = MockConfigEntry(
        domain=DOMAIN, title="Calendora", data={CONF_API_KEY: API_KEY}, version=2
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert set(hass.states.async_entity_ids("calendar")) == {HOUSEHOLD_CALENDAR, ALEX}

    aioclient_mock.clear_requests()
    _mock_all(aioclient_mock)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert set(hass.states.async_entity_ids("calendar")) == {
        HOUSEHOLD_CALENDAR,
        ALEX,
        ROBIN,
        BISCUIT,
    }


async def test_a_removed_member_goes_unavailable_rather_than_vanishing(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, setup_members
) -> None:
    """An entity named in an automation should say it is broken, not disappear."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(HOUSEHOLD_URL, json=load_fixture("household.json"))
    aioclient_mock.get(MEMBERS_URL, json={"members": load_fixture("members.json")["members"][:2]})
    aioclient_mock.get(EVENTS_URL, json=load_fixture("events.json"))

    await setup_members.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(BISCUIT).state == "unavailable"
    assert hass.states.get(ALEX).state != "unavailable"
