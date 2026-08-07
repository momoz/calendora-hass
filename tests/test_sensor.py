"""Tests for the per-member next-event sensors."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.calendora.const import API_BASE_URL, CONF_API_KEY, DOMAIN

from .const import API_KEY, load_fixture

HOUSEHOLD_URL = f"{API_BASE_URL}/api/v1/household"
MEMBERS_URL = f"{API_BASE_URL}/api/v1/members"
EVENTS_URL = f"{API_BASE_URL}/api/v1/events"
STREAM_URL = f"{API_BASE_URL}/api/v1/stream"

ALEX = "sensor.test_household_alex_next_event"
ROBIN = "sensor.test_household_robin_next_event"
BISCUIT = "sensor.test_household_biscuit_next_event"


def _mock_all(aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(HOUSEHOLD_URL, json=load_fixture("household.json"))
    aioclient_mock.get(MEMBERS_URL, json=load_fixture("members.json"))
    aioclient_mock.get(EVENTS_URL, json=load_fixture("events.json"))
    aioclient_mock.get(STREAM_URL, text="", headers={"Content-Type": "text/event-stream"})


async def _setup(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> MockConfigEntry:
    _mock_all(aioclient_mock)
    entry = MockConfigEntry(
        domain=DOMAIN, title="Calendora", data={CONF_API_KEY: API_KEY}, version=2
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture(name="before_everything")
def before_everything_fixture(freezer: FrozenDateTimeFactory) -> None:
    """Freeze well before the fixture's first event.

    Without a frozen clock these tests would start passing and failing depending
    on the date they are run, which is worse than no test at all.
    """
    freezer.move_to(datetime(2026, 8, 1, 9, 0, tzinfo=dt_util.UTC))


async def test_one_sensor_per_member(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, before_everything: None
) -> None:
    """Every member gets a next-event sensor, pets included."""
    await _setup(hass, aioclient_mock)

    assert set(hass.states.async_entity_ids("sensor")) == {ALEX, ROBIN, BISCUIT}


async def test_device_class_is_timestamp(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, before_everything: None
) -> None:
    """A timestamp renders as "in 20 minutes" and compares without parsing."""
    await _setup(hass, aioclient_mock)

    state = hass.states.get(ALEX)
    assert state.attributes["device_class"] == SensorDeviceClass.TIMESTAMP
    # The state must parse as an instant, which is what device_class promises.
    assert datetime.fromisoformat(state.state).tzinfo is not None


async def test_reports_the_next_event_start(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, before_everything: None
) -> None:
    """The fixture's first event is the all-day one on 10 August."""
    await _setup(hass, aioclient_mock)

    assert datetime.fromisoformat(hass.states.get(ALEX).state) == datetime(
        2026, 8, 9, 22, 0, tzinfo=dt_util.UTC
    )


async def test_household_wide_events_count_for_everyone(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, before_everything: None
) -> None:
    """Biscuit is named on nothing, and still has a next event.

    Same trap as the member calendars: under a membership-only filter this
    sensor reads "unknown" forever while the household is going camping.
    """
    await _setup(hass, aioclient_mock)

    assert hass.states.get(BISCUIT).state != STATE_UNKNOWN
    assert hass.states.get(BISCUIT).attributes["shared_with_household"] is True


async def test_members_see_different_next_events(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    """After the shared events pass, Alex and Robin diverge.

    On 1 September the camping trip and the ferry are done. Alex has nothing of
    his own left; Robin still has the piano lesson in November.
    """
    freezer.move_to(datetime(2026, 9, 1, tzinfo=dt_util.UTC))
    await _setup(hass, aioclient_mock)

    assert hass.states.get(ROBIN).state == datetime(
        2026, 11, 4, 14, 0, tzinfo=dt_util.UTC
    ).isoformat()
    assert hass.states.get(ALEX).state == STATE_UNKNOWN


async def test_an_event_already_under_way_is_not_the_next_one(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    """A countdown must not count up.

    Mid-ferry, the next event is whatever comes after it — not the ferry's own
    start time, which is in the past.
    """
    freezer.move_to(datetime(2026, 8, 21, 12, 0, tzinfo=dt_util.UTC))
    await _setup(hass, aioclient_mock)

    state = hass.states.get(ROBIN).state
    assert state != STATE_UNKNOWN
    assert datetime.fromisoformat(state) > dt_util.utcnow()


async def test_unknown_when_nothing_is_coming(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    """An empty future is unknown, not an error and not a stale value."""
    freezer.move_to(datetime(2027, 1, 1, tzinfo=dt_util.UTC))
    await _setup(hass, aioclient_mock)

    assert hass.states.get(ALEX).state == STATE_UNKNOWN


async def test_attributes_are_small_and_useful(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, before_everything: None
) -> None:
    """Enough to render a card; not the whole event, which gets recorded."""
    await _setup(hass, aioclient_mock)

    attributes = hass.states.get(ALEX).attributes
    assert attributes["summary"] == "School photo day"
    assert attributes["all_day"] is True
    assert set(attributes) >= {"summary", "location", "all_day", "shared_with_household"}


async def test_unique_id_is_keyed_on_household_and_member(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, before_everything: None
) -> None:
    """Stable identity, and never the API key."""
    await _setup(hass, aioclient_mock)

    entry = er.async_get(hass).async_get(ALEX)
    assert entry.unique_id == "hh-test-0001-next-event-mem-1"
    assert API_KEY not in entry.unique_id


async def test_removed_member_sensor_goes_unavailable(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, before_everything: None
) -> None:
    """Matches the calendar behaviour: say it is broken, do not vanish."""
    entry = await _setup(hass, aioclient_mock)

    aioclient_mock.clear_requests()
    aioclient_mock.get(HOUSEHOLD_URL, json=load_fixture("household.json"))
    aioclient_mock.get(
        MEMBERS_URL, json={"members": load_fixture("members.json")["members"][:2]}
    )
    aioclient_mock.get(EVENTS_URL, json=load_fixture("events.json"))
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(BISCUIT).state == STATE_UNAVAILABLE


async def test_no_busy_binary_sensor_is_created(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, before_everything: None
) -> None:
    """A busy sensor would duplicate the calendar entity's own state.

    `calendar.<household>_<member>` is already `on` while an event is running.
    A second entity saying the same thing is two sources for one truth that can
    disagree, and the derived one is the one that will be wrong.
    """
    await _setup(hass, aioclient_mock)

    assert not hass.states.async_entity_ids("binary_sensor")
    assert hass.states.get("calendar.test_household_alex") is not None


async def test_no_leave_by_sensor_is_created(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, before_everything: None
) -> None:
    """§7: `/api/v1/events/{id}/leave-by` is not built.

    `travelMinutes` is on the event and looks like enough to derive one, but it
    is a property of the event rather than a route from wherever the person
    actually is. Subtracting it would produce a number that looks authoritative
    and is not, so no such entity exists.
    """
    await _setup(hass, aioclient_mock)

    assert not [
        entity_id
        for entity_id in hass.states.async_entity_ids("sensor")
        if "leave" in entity_id
    ]
