"""Tags, leave-by and tonight's dinner, against Calendora's own fixtures.

The real integration is set up against mocked HTTP whose every response body
is a pair from `fixtures/`, unedited (`tests/producer.py`), and assertions are
made on Home Assistant state and on the requests that went out — never on a
service spy or a hand-published state. That is the 0.4.7 lesson: the shop
blueprint passed every test for three releases against a shape no producer
ever emitted.

Where the producer has not generated a case — a tagged event, an event with a
drive time — the test skips and names the gap rather than inventing the value.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import re

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.calendora.const import API_BASE_URL, CONF_API_KEY, DOMAIN

from .conftest import DinnerFixture
from .const import API_KEY
from .producer import body, pair, require

CALENDAR = "calendar.the_olsens"
MIKE_LEAVE_BY = "sensor.the_olsens_mike_leave_by"
DONNA_LEAVE_BY = "sensor.the_olsens_donna_leave_by"
DINNER = "sensor.the_olsens_tonights_dinner"
CHORES = "sensor.the_olsens_chores_due"
LEAVE_BY_ROUTE = re.compile(r"/api/v1/events/[^/]+/leave-by$")

TAGS_GAP = "no tagged occurrence in `events` (filed with this change)"
TRAVEL_GAP = "no occurrence with `travelMinutes` in `events` (filed with this change)"

# Every GET of the dinner card the producer has generated.
DINNER_READS = sorted(
    name
    for name in (
        "dinner-cook",
        "dinner-leftovers",
        "dinner-out",
        "dinner-quick",
        "dinner-skip",
        "dinner-takeout",
        "dinner-unplanned",
        "dinner-words-only",
    )
)


def _mock_reads(aioclient_mock: AiohttpClientMocker) -> None:
    """Answer each set-up read with the producer pair for that exact path."""
    for name in ("household", "members", "events", "lists", "list-items"):
        request = pair(name)["request"]
        # Mocked without the query: the window the coordinator asks for moves
        # with the clock, and the producer's `events` is one fixed month.
        path = request["path"].split("?", 1)[0]
        aioclient_mock.get(f"{API_BASE_URL}{path}", json=body(name))
    aioclient_mock.get(
        f"{API_BASE_URL}/api/v1/stream",
        text="",
        headers={"Content-Type": "text/event-stream"},
    )


async def _setup(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    leave_by: str = "event-leave-by",
) -> None:
    response = pair(leave_by)["response"]
    aioclient_mock.get(LEAVE_BY_ROUTE, status=response["status"], json=response["body"])
    _mock_reads(aioclient_mock)
    entry = MockConfigEntry(
        domain=DOMAIN, title="Calendora", data={CONF_API_KEY: API_KEY}, version=2
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.fixture(autouse=True)
def _before_the_fixture_month(freezer: FrozenDateTimeFactory) -> None:
    """The producer's `events` is March 2027; start just before it."""
    freezer.move_to(datetime(2027, 3, 1, 8, 0, tzinfo=dt_util.UTC))


def _occurrences() -> list[dict]:
    return body("events")["occurrences"]


# --- tags -----------------------------------------------------------------


async def test_the_calendar_carries_the_current_events_tags_as_a_list(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """§4: `[]` is a statement, so the attribute is present and empty."""
    await _setup(hass, aioclient_mock)

    state = hass.states.get(CALENDAR)
    assert state.attributes["message"] == _occurrences()[0]["title"]
    assert state.attributes["tags"] == [
        tag["name"] for tag in _occurrences()[0]["tags"]
    ]


async def test_a_calendar_trigger_hands_the_automation_the_tags(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Run a real automation off a real calendar trigger and read what it got.

    This is the only test that can tell the tags really reach
    `trigger.calendar_event`: that rests on Home Assistant serialising our
    `CalendarEvent` subclass field by field, which is its behaviour in
    2026.10.4 rather than a promise. If a release changes it, this fails here
    instead of in somebody's automation.
    """
    await _setup(hass, aioclient_mock)
    seen = async_capture_events(hass, "calendora_test_tags")
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": {
                "trigger": {
                    "platform": "calendar",
                    "event": "start",
                    "entity_id": CALENDAR,
                },
                "action": {
                    "event": "calendora_test_tags",
                    "event_data": {
                        "summary": "{{ trigger.calendar_event.summary }}",
                        "tags": "{{ trigger.calendar_event.tags }}",
                        # An absent key also renders as "", so presence is
                        # asserted on its own or an empty tag list proves nothing.
                        "has_tags": "{{ 'tags' in trigger.calendar_event }}",
                    },
                },
            }
        },
    )
    await hass.async_block_till_done()

    # Walked rather than jumped: the trigger re-reads the calendar every 15
    # minutes and schedules the start from what it read, so a single 23-hour
    # jump skips the read that would have found the event.
    first = _occurrences()[0]
    until = dt_util.parse_datetime(first["start"]) + timedelta(seconds=1)
    while dt_util.utcnow() < until:
        freezer.move_to(min(dt_util.utcnow() + timedelta(minutes=5), until))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()

    assert [event.data for event in seen] == [
        {
            "summary": first["title"],
            "tags": ", ".join(tag["name"] for tag in first["tags"]),
            "has_tags": True,
        }
    ]

    # Detaches the trigger's 15-minute re-read, which otherwise outlives the
    # test and fails it at teardown.
    await hass.services.async_call(
        "automation", "turn_off", {"entity_id": "all"}, blocking=True
    )


async def test_a_tagged_event_names_its_tags(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The case that matters, once the producer generates it."""
    tagged = require([o for o in _occurrences() if o["tags"]], TAGS_GAP)[0]
    await _setup(hass, aioclient_mock)

    entity = hass.data["entity_components"]["calendar"].get_entity(CALENDAR)
    events = await entity.async_get_events(
        hass,
        dt_util.parse_datetime(tagged["start"]) - timedelta(minutes=1),
        dt_util.parse_datetime(tagged["end"]),
    )
    match = next(event for event in events if event.uid == tagged["id"])
    assert match.tags == ", ".join(tag["name"] for tag in tagged["tags"])


# --- leave by -------------------------------------------------------------


async def test_an_event_without_a_drive_is_skipped_for_the_next_with_one(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """§4: no `travelMinutes` is no leave time, so it is not the answer.

    Mike's next event is the household-wide "Contested", which has no drive;
    the one after with a drive is the household gym session. Answering with
    "Contested" would be an `unknown` on a morning he does have to set off.
    """
    occurrences = _occurrences()
    mikes = [o for o in occurrences if not o["attendeeIds"] or "fx-member-mike" in o["attendeeIds"]]
    assert mikes[0]["travelMinutes"] is None, "the producer's order changed; re-read this test"
    driven = next(o for o in mikes if o["travelMinutes"] is not None and not o["isAllDay"])
    await _setup(hass, aioclient_mock)

    state = hass.states.get(MIKE_LEAVE_BY)
    assert state.attributes["event_id"] == driven["id"]
    assert dt_util.parse_datetime(state.state) == dt_util.parse_datetime(
        driven["start"]
    ) - timedelta(minutes=driven["travelMinutes"])


async def test_the_words_are_calendoras_and_asked_for_by_occurrence(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """`words` is passed through from `/leave-by`, which is asked per occurrence.

    The producer's `event-leave-by` is for a 2029 gym session rather than the
    March 2027 one these events hold, so this pins the route and the
    pass-through, not that the words describe this exact morning.
    """
    await _setup(hass, aioclient_mock)

    asked = sorted(
        call[1].path for call in aioclient_mock.mock_calls if LEAVE_BY_ROUTE.search(call[1].path)
    )
    expected = sorted(
        f"/api/v1/events/{hass.states.get(entity_id).attributes['event_id']}/leave-by"
        for entity_id in (MIKE_LEAVE_BY, DONNA_LEAVE_BY)
    )
    assert asked == expected
    assert hass.states.get(DONNA_LEAVE_BY).attributes["words"] == body("event-leave-by")["words"]


async def test_a_failed_leave_by_read_costs_the_words_not_the_time(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A refused `/leave-by` must not take the sensor, or the refresh, with it."""
    await _setup(hass, aioclient_mock, leave_by="error-patch-missing-event")

    state = hass.states.get(DONNA_LEAVE_BY)
    assert state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE)
    assert state.attributes["words"] is None
    assert hass.states.get(CALENDAR).state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)


async def test_leave_by_is_start_minus_the_drive(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """§4's `leaveAt`, once the producer generates an event with a drive."""
    driven = require(
        [o for o in _occurrences() if o["travelMinutes"] is not None and not o["isAllDay"]],
        TRAVEL_GAP,
    )[0]
    await _setup(hass, aioclient_mock)

    entity_id = (
        DONNA_LEAVE_BY if "fx-member-donna" in driven["attendeeIds"] else MIKE_LEAVE_BY
    )
    state = hass.states.get(entity_id)
    expected = dt_util.parse_datetime(driven["start"]) - timedelta(
        minutes=driven["travelMinutes"]
    )
    assert dt_util.parse_datetime(state.state) == expected
    assert state.attributes["travel_from"] == driven["travelFrom"]


# --- tonight's dinner -----------------------------------------------------


@pytest.mark.parametrize("name", DINNER_READS)
async def test_the_dinner_sensor_says_what_the_today_card_says(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    dinner: DinnerFixture,
    name: str,
) -> None:
    """§6a: `headline` is the sensor's state. Every generated card, unedited."""
    dinner.name = name
    card = body(name)["dinner"]
    await _setup(hass, aioclient_mock)

    state = hass.states.get(DINNER)
    assert state.state == card["headline"]
    assert state.attributes["day"] == card["day"]
    assert state.attributes["status"] == card["state"]
    assert [m["headline"] for m in state.attributes["meals"]] == [
        m["headline"] for m in card["meals"]
    ]
    assert [m["sentence"] for m in state.attributes["meals"]] == [
        m["sentence"] for m in card["meals"]
    ]


async def test_serve_at_is_the_wall_time_read_in_its_own_zone(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, dinner: DinnerFixture
) -> None:
    """§6a: `serveAt` is `"18:30"`, not an instant — read it in `serveTz`."""
    dinner.name = "dinner-cook"
    card = body("dinner-cook")["dinner"]
    meal = card["meals"][0]
    await _setup(hass, aioclient_mock)

    expected = datetime.fromisoformat(f"{card['day']}T{meal['serveAt']}").replace(
        tzinfo=ZoneInfo(meal["serveTz"])
    )
    state = hass.states.get(DINNER)
    assert state.attributes["serve_at"] == expected
    assert state.attributes["meals"][0]["serve_at"] == expected


async def test_dinner_is_asked_for_today_by_the_server_not_by_us(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """No `day` goes out: §6a defaults it to today in the key owner's zone."""
    await _setup(hass, aioclient_mock)

    dinner_reads = [
        call for call in aioclient_mock.mock_calls if call[1].path == "/api/v1/dinner"
    ]
    assert dinner_reads
    assert all(call[0] == "GET" and not call[1].query for call in dinner_reads)


async def test_a_key_without_meals_has_no_dinner_and_keeps_its_calendar(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, dinner: DinnerFixture
) -> None:
    """The producer's 403 for a key without `meals:read`.

    The fixture is for `GET /meals`; the scope and the refusal are the same
    for `GET /dinner` (§6a puts both under `meals:read`). What matters is that
    the rest of the integration does not go down with it.
    """
    dinner.name = "error-meals-scope"
    await _setup(hass, aioclient_mock)

    assert hass.states.get(DINNER) is None
    assert hass.states.get(CALENDAR).state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)


async def test_losing_meals_after_set_up_makes_dinner_unavailable(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, dinner: DinnerFixture
) -> None:
    """Not "Not planned": that is a fact about dinner, and this is not one."""
    await _setup(hass, aioclient_mock)
    assert hass.states.get(DINNER).state == body("dinner-unplanned")["dinner"]["headline"]

    dinner.name = "error-meals-scope"
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(DINNER).state == STATE_UNAVAILABLE


# --- chores due -----------------------------------------------------------


def _items() -> list[dict]:
    return body("list-items")["items"]


@pytest.mark.parametrize(
    ("utc", "expect_due"),
    [
        # 03:00 UTC on the 11th is 03:00 in London — the key owner's zone —
        # and still the 10th in Home Assistant's test zone (US/Pacific). Due.
        (datetime(2027, 3, 11, 3, 0, tzinfo=dt_util.UTC), True),
        # 23:30 UTC on the 10th is still the 10th in London. Not yet.
        (datetime(2027, 3, 10, 23, 30, tzinfo=dt_util.UTC), False),
    ],
)
async def test_chores_due_is_repeating_items_due_by_today_in_the_owners_zone(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
    utc: datetime,
    expect_due: bool,
) -> None:
    """GAP-019's rule: `repeats: true`, `due` on or before today, owner's zone.

    The producer's `list-items` has "Bins out" (repeats) and "Return the
    school form" (one-off) due the same day; only `repeats` separates them,
    so a sensor counting both is caught here.
    """
    freezer.move_to(utc)
    chores = [i for i in _items() if i["repeats"] and not i["isChecked"] and i["due"]]
    assert chores and any(not i["repeats"] and i["due"] for i in _items())
    await _setup(hass, aioclient_mock)

    state = hass.states.get(CHORES)
    names = [item["summary"] for item in state.attributes["items"]]
    if expect_due:
        assert int(state.state) == len(chores)
        assert names == [i["text"] for i in chores]
    else:
        assert state.state == "0"
        assert names == []
