"""Tests for calendar write-back.

`_scope_for` carries the weight. Home Assistant asks the user "this event, or
this and all following?"; Calendora needs that as a required `scope`. Getting
the translation wrong does not raise — it silently edits the wrong number of
days, which the user discovers weeks later when a Tuesday they never touched
has moved.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.calendora.calendar import _scope_for, _wire_times
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
    return [c[2] for c in aioclient_mock.mock_calls if c[0] == method]


# --- the translation --------------------------------------------------------


def test_scope_maps_home_assistants_two_answers() -> None:
    """`""` means this one; `THISANDFUTURE` means this and the rest."""
    assert _scope_for("2026-11-04", "") == "this"
    assert _scope_for("2026-11-04", None) == "this"
    assert _scope_for("2026-11-04", "THISANDFUTURE") == "following"


def test_a_one_off_still_carries_a_scope() -> None:
    """§7: required even on an event that does not repeat.

    All three mean the same thing there, so `all` is the honest one — nothing
    is being singled out — and the same code keeps working the day somebody
    makes the event repeat.
    """
    assert _scope_for(None, None) == "all"


def test_all_is_never_chosen_for_an_occurrence() -> None:
    """The API accepts `all`; Home Assistant has no way to ask for it.

    A user who chose "this one" has not asked to change the Tuesdays that have
    already happened, and there is no third answer to map from.
    """
    for recurrence_range in ("", None, "THISANDFUTURE"):
        assert _scope_for("2026-11-04", recurrence_range) != "all"


def test_times_are_rendered_in_the_form_that_says_what_they_mean() -> None:
    """§7: a date is a day, an instant is a moment, and mixing them is a 400."""
    all_day = _wire_times({"dtstart": date(2027, 8, 11), "dtend": date(2027, 8, 12)})
    assert all_day == {"start": "2027-08-11", "end": "2027-08-12"}
    assert "T" not in all_day["start"]

    timed = _wire_times({
        "dtstart": datetime(2027, 8, 11, 7, 0, tzinfo=dt_util.UTC),
        "dtend": datetime(2027, 8, 11, 7, 15, tzinfo=dt_util.UTC),
    })
    assert timed["start"].endswith("Z") and "T" in timed["start"]


# --- end to end -------------------------------------------------------------


async def test_editing_one_occurrence_sends_scope_this(
    hass: HomeAssistant, setup_calendar: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """The whole point of the fix: this Tuesday, not every Tuesday."""
    aioclient_mock.clear_requests()
    aioclient_mock.patch(
        f"{EVENTS_URL}/{OCCURRENCE}",
        json={"id": "new-standalone-id", "scope": "this",
              "result": "this one was taken out of the repeat and changed on its own"},
    )
    _mock_reads(aioclient_mock)

    entity = hass.data["entity_components"]["calendar"].get_entity(ENTITY_ID)
    await entity.async_update_event(
        OCCURRENCE,
        {"summary": "Piano (moved)",
         "dtstart": datetime(2026, 11, 4, 15, 0, tzinfo=dt_util.UTC),
         "dtend": datetime(2026, 11, 4, 16, 0, tzinfo=dt_util.UTC)},
        recurrence_id="2026-11-04",
        recurrence_range="",
    )

    body = _bodies(aioclient_mock, "PATCH")[0]
    assert body["scope"] == "this"
    assert body["title"] == "Piano (moved)"


async def test_this_and_future_sends_scope_following(
    hass: HomeAssistant, setup_calendar: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """The other answer Home Assistant can give."""
    aioclient_mock.clear_requests()
    aioclient_mock.patch(f"{EVENTS_URL}/{OCCURRENCE}", json={
        "id": "new-series-id", "scope": "following",
        "result": "the repeat was ended and a new one started from this occurrence"})
    _mock_reads(aioclient_mock)

    entity = hass.data["entity_components"]["calendar"].get_entity(ENTITY_ID)
    await entity.async_update_event(
        OCCURRENCE,
        {"summary": "Piano (evenings)",
         "dtstart": datetime(2026, 11, 4, 18, 0, tzinfo=dt_util.UTC),
         "dtend": datetime(2026, 11, 4, 19, 0, tzinfo=dt_util.UTC)},
        recurrence_id="2026-11-04",
        recurrence_range="THISANDFUTURE",
    )

    assert _bodies(aioclient_mock, "PATCH")[0]["scope"] == "following"


async def test_scope_is_always_present(
    hass: HomeAssistant, setup_calendar: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Omitting it is a 400 naming `scope`, so it must never be omitted."""
    aioclient_mock.clear_requests()
    aioclient_mock.patch(f"{EVENTS_URL}/evt-allday:2026-08-10",
                         json={"id": "x", "scope": "all", "result": "the whole series was changed"})
    _mock_reads(aioclient_mock)

    entity = hass.data["entity_components"]["calendar"].get_entity(ENTITY_ID)
    await entity.async_update_event(
        "evt-allday:2026-08-10",
        {"summary": "Photo day", "dtstart": date(2026, 8, 10), "dtend": date(2026, 8, 11)},
    )

    assert "scope" in _bodies(aioclient_mock, "PATCH")[0]


async def test_creating_sends_a_client_chosen_id_and_no_is_all_day(
    hass: HomeAssistant, setup_calendar: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """The form carries the meaning, so `isAllDay` is not restated.

    Sending one that disagrees with the form is a 400, and there is nothing to
    gain by saying the same thing twice.
    """
    aioclient_mock.clear_requests()
    aioclient_mock.post(EVENTS_URL, json={"id": "whatever"}, status=201)
    _mock_reads(aioclient_mock)

    entity = hass.data["entity_components"]["calendar"].get_entity(ENTITY_ID)
    await entity.async_create_event(
        summary="Bin day", dtstart=date(2027, 8, 11), dtend=date(2027, 8, 12)
    )

    body = _bodies(aioclient_mock, "POST")[0]
    assert body["id"] and isinstance(body["id"], str)
    assert body["start"] == "2027-08-11"
    assert "isAllDay" not in body
    assert "position" not in body


async def test_deleting_a_repeating_event_surfaces_calendoras_own_words(
    hass: HomeAssistant, setup_calendar: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """The refusal explains itself and tells the user what to do instead.

    Replacing it with "delete failed" would throw away the only sentence that
    helps.
    """
    aioclient_mock.clear_requests()
    aioclient_mock.delete(f"{EVENTS_URL}/evt-piano", status=400, json={
        "error": "this event repeats, and a repeating series cannot be removed"
                 " through this API — Remove it in Calendora instead.",
        "code": "bad_request"})
    _mock_reads(aioclient_mock)

    entity = hass.data["entity_components"]["calendar"].get_entity(ENTITY_ID)
    with pytest.raises(HomeAssistantError) as err:
        await entity.async_delete_event("evt-piano")

    assert "Calendora" in str(err.value) or "repeats" in str(err.value)


async def test_a_write_never_leaks_the_key(
    hass: HomeAssistant,
    setup_calendar: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Same guarantee as every other path, on the newest one."""
    aioclient_mock.clear_requests()
    aioclient_mock.patch(f"{EVENTS_URL}/{OCCURRENCE}", status=500,
                         json={"error": "boom", "code": "server_error"})
    _mock_reads(aioclient_mock)

    entity = hass.data["entity_components"]["calendar"].get_entity(ENTITY_ID)
    with pytest.raises(HomeAssistantError):
        await entity.async_update_event(
            OCCURRENCE,
            {"summary": "x", "dtstart": datetime(2026, 11, 4, 15, tzinfo=dt_util.UTC),
             "dtend": datetime(2026, 11, 4, 16, tzinfo=dt_util.UTC)},
            recurrence_id="2026-11-04", recurrence_range="")

    assert API_KEY not in caplog.text


async def test_a_member_calendar_does_not_offer_to_create(
    hass: HomeAssistant, setup_calendar: MockConfigEntry
) -> None:
    """Creating on a person's calendar would create it for everybody.

    `POST /events` has no attendee field, so an event created from Robin's
    calendar arrives with nobody on it — which means the whole household. The
    user asked for one person's event and got everyone's, with no error and no
    clue beyond seeing it repeated across the dashboard.

    Reported from a real household before this test existed.
    """
    from homeassistant.components.calendar import CalendarEntityFeature

    member = hass.states.get("calendar.test_household_robin")
    household = hass.states.get("calendar.test_household")

    assert not member.attributes["supported_features"] & CalendarEntityFeature.CREATE_EVENT
    assert household.attributes["supported_features"] & CalendarEntityFeature.CREATE_EVENT

    # Editing and removing still work: they act on an event that already exists
    # and do not have to say whose it is.
    assert member.attributes["supported_features"] & CalendarEntityFeature.UPDATE_EVENT
    assert member.attributes["supported_features"] & CalendarEntityFeature.DELETE_EVENT


async def test_an_event_created_from_home_assistant_belongs_to_everybody(
    hass: HomeAssistant, setup_calendar: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """An end-to-end assertion about who OWNS the result, not about the request.

    The request was always well-formed, which is why nothing caught this. What
    matters is the outcome: `POST /events` has no attendee field — the server
    enumerates what it accepts and no attendee appears — so anything created
    from Home Assistant arrives with nobody on it, and §4a defines that as the
    whole household.

    Asserted here by checking the created event shows up on *every* member's
    calendar, which is what a real household saw and reported.
    """
    aioclient_mock.clear_requests()
    created = {
        "id": "evt-new:2026-12-01", "eventId": "evt-new",
        "occurrenceKey": "2026-12-01", "title": "Dentist",
        "isAllDay": True, "start": "2026-11-30T23:00:00.000Z",
        "end": "2026-12-01T23:00:00.000Z", "timezone": "Europe/Amsterdam",
        # What the server stores when nobody can be named:
        "attendeeIds": [],
    }
    aioclient_mock.post(EVENTS_URL, json={"id": "evt-new"}, status=201)
    aioclient_mock.get(HOUSEHOLD_URL, json=load_fixture("household.json"))
    aioclient_mock.get(MEMBERS_URL, json=load_fixture("members.json"))
    aioclient_mock.get(EVENTS_URL, json={"occurrences": [created]})
    aioclient_mock.get(LISTS_URL, json={"lists": []})
    aioclient_mock.get(STREAM_URL, text="", headers={"Content-Type": "text/event-stream"})

    household = hass.data["entity_components"]["calendar"].get_entity(ENTITY_ID)
    await household.async_create_event(
        summary="Dentist", dtstart=date(2026, 12, 1), dtend=date(2026, 12, 2)
    )
    await hass.async_block_till_done()

    # The request could not name anybody — the server rejects the field.
    body = _bodies(aioclient_mock, "POST")[0]
    assert "attendeeIds" not in body
    assert "attendees" not in body

    # And the outcome: it is on every single member's calendar.
    window = (
        datetime(2026, 11, 25, tzinfo=dt_util.UTC),
        datetime(2026, 12, 5, tzinfo=dt_util.UTC),
    )
    for entity_id in (
        "calendar.test_household",
        "calendar.test_household_alex",
        "calendar.test_household_robin",
        "calendar.test_household_biscuit",
    ):
        entity = hass.data["entity_components"]["calendar"].get_entity(entity_id)
        uids = {e.uid for e in await entity.async_get_events(hass, *window)}
        assert "evt-new:2026-12-01" in uids, f"{entity_id} should show a household event"
