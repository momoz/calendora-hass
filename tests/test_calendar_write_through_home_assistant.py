"""Calendar writes driven the way the outside world drives them.

`test_calendar_write.py` calls `entity.async_create_event(...)` and friends in
Python. That proves the entity does the right thing when it is called correctly.
It cannot prove anybody can call it, because **nothing outside this repository
reaches those methods directly**:

- `calendar.create_event` is a *service*, registered with
  `required_features=[CalendarEntityFeature.CREATE_EVENT]`. Drop that flag from
  `_attr_supported_features` and every direct-call test still passes while Home
  Assistant refuses the service.
- Updating and deleting are not services at all. They are **websocket commands**
  — `calendar/event/update` and `calendar/event/delete` — with their own schemas,
  and they are how the Home Assistant frontend and anything speaking to it get
  at an event.

Between a caller and the entity sit a feature gate, a voluptuous schema and a
field-name mapping, and a direct call skips all three. That is the same shape as
the blueprint bug found on 2026-08-09: the thing under test was fine, and the
layer that decides whether anyone can use it was never exercised.

The `scope` translation is the part that matters most here. Home Assistant asks
"this event, or this and all following?" and sends the answer as
`recurrence_range` over the websocket. Getting it wrong does not raise — it
edits the wrong number of days.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.calendora.const import API_BASE_URL, CONF_API_KEY, DOMAIN

from .const import API_KEY, load_fixture

HOUSEHOLD_URL = f"{API_BASE_URL}/api/v1/household"
MEMBERS_URL = f"{API_BASE_URL}/api/v1/members"
EVENTS_URL = f"{API_BASE_URL}/api/v1/events"
LISTS_URL = f"{API_BASE_URL}/api/v1/lists"
STREAM_URL = f"{API_BASE_URL}/api/v1/stream"

ENTITY_ID = "calendar.test_household"
OCCURRENCE = "evt-piano:2026-11-04"


def _mock_reads(aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(HOUSEHOLD_URL, json=load_fixture("household.json"))
    aioclient_mock.get(MEMBERS_URL, json=load_fixture("members.json"))
    aioclient_mock.get(EVENTS_URL, json=load_fixture("events.json"))
    aioclient_mock.get(LISTS_URL, json={"lists": []})
    aioclient_mock.get(STREAM_URL, text="", headers={"Content-Type": "text/event-stream"})


@pytest.fixture(name="setup_calendar")
async def setup_calendar_fixture(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> MockConfigEntry:
    _mock_reads(aioclient_mock)
    entry = MockConfigEntry(
        domain=DOMAIN, title="Calendora", data={CONF_API_KEY: API_KEY}, version=2
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _bodies(aioclient_mock: AiohttpClientMocker, method: str) -> list[dict]:
    """`mock_calls` records the method upper-cased. Getting that wrong reads as
    "the request never happened", which is indistinguishable from the bug these
    tests exist to find — so it is spelled once, here."""
    return [call[2] for call in aioclient_mock.mock_calls if call[0] == method.upper()]


async def test_the_create_event_service_reaches_the_api(
    hass: HomeAssistant,
    setup_calendar: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Through the service, with the service's own field names.

    `calendar.create_event` takes `summary`, `start_date_time` and
    `end_date_time`; the entity reads `dtstart` and `dtend`, which Home
    Assistant maps on the way through. A direct-call test supplies the entity's
    names and so can never catch a mapping that has come apart.
    """
    aioclient_mock.clear_requests()
    # 201, not 200: `async_create_event` passes `expect=HTTPStatus.CREATED`
    # and the API contract says Created. A 200 here is a mock that disagrees
    # with the fixtures, and it fails exactly as a server regression would.
    aioclient_mock.post(EVENTS_URL, status=201, json={"id": "evt-new"})
    _mock_reads(aioclient_mock)

    await hass.services.async_call(
        "calendar",
        "create_event",
        {
            "entity_id": ENTITY_ID,
            "summary": "Dentist",
            "start_date_time": "2027-08-11 09:00:00",
            "end_date_time": "2027-08-11 09:30:00",
            "location": "High Street",
        },
        blocking=True,
    )

    posted = _bodies(aioclient_mock, "post")
    assert len(posted) == 1, "the service call never reached the API"
    body = posted[0]
    assert body["title"] == "Dentist"
    assert body["location"] == "High Street"
    assert body["start"].startswith("2027-08-11T")
    assert "timezone" in body


async def test_the_create_event_service_is_offered_at_all(
    hass: HomeAssistant, setup_calendar: MockConfigEntry
) -> None:
    """The feature flag is the gate, and it is invisible to a direct call.

    `calendar.create_event` is registered with
    `required_features=[CalendarEntityFeature.CREATE_EVENT]`. If the flag were
    dropped from the entity, Home Assistant would reject the service for it
    while `async_create_event` still existed and every direct-call test still
    passed.
    """
    from homeassistant.components.calendar import CalendarEntityFeature

    state = hass.states.get(ENTITY_ID)
    assert state is not None, "the household calendar is missing"
    features = CalendarEntityFeature(state.attributes["supported_features"])
    assert CalendarEntityFeature.CREATE_EVENT in features
    assert CalendarEntityFeature.UPDATE_EVENT in features
    assert CalendarEntityFeature.DELETE_EVENT in features


async def test_editing_one_occurrence_over_the_websocket_sends_scope_this(
    hass: HomeAssistant,
    setup_calendar: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """This Tuesday, not every Tuesday — asked the way the frontend asks it.

    An empty `recurrence_range` is Home Assistant's "this event only". The
    websocket schema passes it through `_empty_as_none`, so what the entity
    receives is not what the caller sent; that conversion is only observable
    from this side of it.
    """
    aioclient_mock.clear_requests()
    aioclient_mock.patch(
        f"{EVENTS_URL}/{OCCURRENCE}",
        json={"id": "new-standalone-id", "scope": "this", "result": "ok"},
    )
    _mock_reads(aioclient_mock)

    client = await hass_ws_client()
    await client.send_json_auto_id(
        {
            "type": "calendar/event/update",
            "entity_id": ENTITY_ID,
            "uid": OCCURRENCE,
            "recurrence_id": "2026-11-04",
            "recurrence_range": "",
            "event": {
                "summary": "Piano",
                "dtstart": "2026-11-04 17:00:00",
                "dtend": "2026-11-04 17:45:00",
            },
        }
    )
    response = await client.receive_json()
    assert response["success"], response

    patched = _bodies(aioclient_mock, "patch")
    assert len(patched) == 1, "the websocket update never reached the API"
    assert patched[0]["scope"] == "this", (
        f"a single occurrence was sent as scope {patched[0]['scope']!r} — that "
        f"edits days the user never touched"
    )


async def test_editing_this_and_following_over_the_websocket_sends_scope_following(
    hass: HomeAssistant,
    setup_calendar: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """The other answer to the same question, and the one with more at stake."""
    aioclient_mock.clear_requests()
    aioclient_mock.patch(
        f"{EVENTS_URL}/{OCCURRENCE}",
        json={"id": "new-series-id", "scope": "following", "result": "ok"},
    )
    _mock_reads(aioclient_mock)

    client = await hass_ws_client()
    await client.send_json_auto_id(
        {
            "type": "calendar/event/update",
            "entity_id": ENTITY_ID,
            "uid": OCCURRENCE,
            "recurrence_id": "2026-11-04",
            "recurrence_range": "THISANDFUTURE",
            "event": {
                "summary": "Piano",
                "dtstart": "2026-11-04 18:00:00",
                "dtend": "2026-11-04 18:45:00",
            },
        }
    )
    response = await client.receive_json()
    assert response["success"], response

    patched = _bodies(aioclient_mock, "patch")
    assert patched[0]["scope"] == "following"


async def test_deleting_over_the_websocket_reaches_the_api(
    hass: HomeAssistant,
    setup_calendar: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Delete has no service at all — this command is the only way in."""
    aioclient_mock.clear_requests()
    aioclient_mock.delete(f"{EVENTS_URL}/evt-solo", json={"deleted": True})
    _mock_reads(aioclient_mock)

    client = await hass_ws_client()
    await client.send_json_auto_id(
        {
            "type": "calendar/event/delete",
            "entity_id": ENTITY_ID,
            "uid": "evt-solo",
        }
    )
    response = await client.receive_json()
    assert response["success"], response

    assert [c for c in aioclient_mock.mock_calls if c[0] == "DELETE"], (
        "the websocket delete never reached the API"
    )


async def test_a_refusal_from_the_server_comes_back_over_the_websocket(
    hass: HomeAssistant,
    setup_calendar: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """The API refuses to delete a repeating series, and says why.

    That refusal has to survive the trip back out through the websocket layer,
    because a caller that gets `success: true` for a delete that did not happen
    will show the event gone and then watch it return on the next refresh.
    """
    aioclient_mock.clear_requests()
    aioclient_mock.delete(
        f"{EVENTS_URL}/evt-piano",
        status=400,
        json={"error": "Deleting a repeating event is not supported",
              "code": "bad_request"},
    )
    _mock_reads(aioclient_mock)

    client = await hass_ws_client()
    await client.send_json_auto_id(
        {
            "type": "calendar/event/delete",
            "entity_id": ENTITY_ID,
            "uid": "evt-piano",
        }
    )
    response = await client.receive_json()
    assert not response["success"], (
        "a refused delete reported success — the caller will show the event gone"
    )


async def test_a_conflict_is_retried_on_the_path_the_frontend_uses(
    hass: HomeAssistant,
    setup_calendar: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """#115's claim, asked over the websocket rather than in Python.

    Two clients editing one household is the ordinary case, not the edge one,
    and the retry existing at the client layer says nothing about whether it
    survives the layer a person's edit actually arrives through.
    """
    aioclient_mock.clear_requests()
    attempts: list[str] = []

    async def _conflict_then_ok(method, url, data):
        from pytest_homeassistant_custom_component.test_util.aiohttp import (
            AiohttpClientMockResponse,
        )

        attempts.append(url.path)
        if len(attempts) == 1:
            return AiohttpClientMockResponse(
                method, url, status=409,
                json={"error": "changed underneath you", "code": "conflict"},
            )
        return AiohttpClientMockResponse(
            method, url, status=200, json={"id": "evt-piano", "scope": "this"}
        )

    aioclient_mock.patch(f"{EVENTS_URL}/{OCCURRENCE}", side_effect=_conflict_then_ok)
    _mock_reads(aioclient_mock)

    client = await hass_ws_client()
    await client.send_json_auto_id(
        {
            "type": "calendar/event/update",
            "entity_id": ENTITY_ID,
            "uid": OCCURRENCE,
            "recurrence_id": "2026-11-04",
            "recurrence_range": "",
            "event": {
                "summary": "Piano",
                "dtstart": "2026-11-04 17:00:00",
                "dtend": "2026-11-04 17:45:00",
            },
        }
    )
    response = await client.receive_json()

    assert len(attempts) == 2, f"the conflict was not retried: {len(attempts)} attempt(s)"
    assert response["success"], "the retry succeeded but the caller was told it failed"
