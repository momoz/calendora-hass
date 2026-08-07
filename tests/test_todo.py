"""Tests for the Calendora to-do lists.

The centre of gravity is `test_ticking_a_checkbox_sends_only_the_checkbox` and
its neighbours. Home Assistant hands the integration a complete `TodoItem` on
every update, so the difference between a correct client and a destructive one
is entirely in what it chooses *not* to send.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from homeassistant.components.todo import TodoItem, TodoItemStatus, TodoListEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_component import DATA_INSTANCES
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)

from custom_components.calendora.const import API_BASE_URL, CONF_API_KEY, DOMAIN
from custom_components.calendora.todo import _changed_fields

from .const import API_KEY, load_fixture

HOUSEHOLD_URL = f"{API_BASE_URL}/api/v1/household"
MEMBERS_URL = f"{API_BASE_URL}/api/v1/members"
EVENTS_URL = f"{API_BASE_URL}/api/v1/events"
LISTS_URL = f"{API_BASE_URL}/api/v1/lists"
STREAM_URL = f"{API_BASE_URL}/api/v1/stream"
ITEMS_1 = f"{LISTS_URL}/lst-1/items"
ITEMS_2 = f"{LISTS_URL}/lst-2/items"

SHOPPING = "todo.test_household_shopping"


def _mock_all(aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(HOUSEHOLD_URL, json=load_fixture("household.json"))
    aioclient_mock.get(MEMBERS_URL, json=load_fixture("members.json"))
    aioclient_mock.get(EVENTS_URL, json=load_fixture("events.json"))
    aioclient_mock.get(LISTS_URL, json=load_fixture("lists.json"))
    aioclient_mock.get(ITEMS_1, json=load_fixture("list_items.json"))
    aioclient_mock.get(ITEMS_2, json={"listId": "lst-2", "sections": [], "items": []})
    aioclient_mock.get(STREAM_URL, text="", headers={"Content-Type": "text/event-stream"})


@pytest.fixture(name="setup_todo")
async def setup_todo_fixture(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> MockConfigEntry:
    _mock_all(aioclient_mock)
    entry = MockConfigEntry(
        domain=DOMAIN, title="Calendora", data={CONF_API_KEY: API_KEY}, version=2
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entity(hass: HomeAssistant, entity_id: str = SHOPPING):
    entity = hass.data[DATA_INSTANCES]["todo"].get_entity(entity_id)
    assert entity is not None, f"{entity_id} does not exist"
    return entity


def _last_body(aioclient_mock: AiohttpClientMocker) -> dict:
    return aioclient_mock.mock_calls[-1][2]


# --- shape ------------------------------------------------------------------


async def test_one_entity_per_active_list(
    hass: HomeAssistant, setup_todo: MockConfigEntry
) -> None:
    """Archived lists are not surfaced — they are archived."""
    entities = set(hass.states.async_entity_ids("todo"))

    assert entities == {SHOPPING, "todo.test_household_packing"}
    assert "todo.test_household_last_year" not in entities


async def test_declares_exactly_the_features_it_can_honour(
    hass: HomeAssistant, setup_todo: MockConfigEntry
) -> None:
    """MOVE_TODO_ITEM is absent by decision (§9), not by omission.

    There is no move endpoint, `position` is rejected in a write body, and
    Calendora's sections are shops — a drag would silently change which shop an
    item is bought at, or snap back.
    """
    supported = hass.states.get(SHOPPING).attributes["supported_features"]

    assert supported & TodoListEntityFeature.CREATE_TODO_ITEM
    assert supported & TodoListEntityFeature.UPDATE_TODO_ITEM
    assert supported & TodoListEntityFeature.DELETE_TODO_ITEM
    assert supported & TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
    assert supported & TodoListEntityFeature.SET_DUE_DATE_ON_ITEM
    assert supported & TodoListEntityFeature.SET_DUE_DATETIME_ON_ITEM
    assert not supported & TodoListEntityFeature.MOVE_TODO_ITEM


async def test_items_are_rendered_in_the_order_given(
    hass: HomeAssistant, setup_todo: MockConfigEntry
) -> None:
    """§9: order arrives sorted by a fractional index. Render it, do not compute."""
    items = _entity(hass).todo_items

    assert [i.summary for i in items] == ["Apples", "Toothpaste", "Collect prescription"]
    assert [i.status for i in items] == [
        TodoItemStatus.NEEDS_ACTION,
        TodoItemStatus.COMPLETED,
        TodoItemStatus.NEEDS_ACTION,
    ]


async def test_due_preserves_day_versus_moment(
    hass: HomeAssistant, setup_todo: MockConfigEntry
) -> None:
    """§5: the form is the meaning. A day is a `date`; a moment is a `datetime`."""
    by_uid = {i.uid: i for i in _entity(hass).todo_items}

    day = by_uid["itm-2"].due
    assert isinstance(day, date) and not isinstance(day, datetime)
    assert day == date(2026, 9, 3)

    moment = by_uid["itm-3"].due
    assert isinstance(moment, datetime)
    assert moment.tzinfo is not None
    assert moment == dt_util.parse_datetime("2026-09-04T14:30:00+00:00")


async def test_unique_id_is_household_and_list(
    hass: HomeAssistant, setup_todo: MockConfigEntry
) -> None:
    entry = er.async_get(hass).async_get(SHOPPING)

    assert entry.unique_id == "hh-test-0001-list-lst-1"
    assert API_KEY not in entry.unique_id


# --- the merge-patch discipline ---------------------------------------------


def test_changed_fields_sends_only_what_changed() -> None:
    """The unit at the heart of it."""
    previous = {"text": "Apples", "notes": None, "isChecked": False, "due": None,
                "quantity": "6", "sectionId": "sec-1", "assignedMembershipId": "mem-1"}

    ticked = TodoItem(uid="itm-1", summary="Apples", status=TodoItemStatus.COMPLETED)
    assert _changed_fields(ticked, previous) == {"isChecked": True}

    renamed = TodoItem(uid="itm-1", summary="Green apples", status=TodoItemStatus.NEEDS_ACTION)
    assert _changed_fields(renamed, previous) == {"text": "Green apples"}

    unchanged = TodoItem(uid="itm-1", summary="Apples", status=TodoItemStatus.NEEDS_ACTION)
    assert _changed_fields(unchanged, previous) == {}


def test_changed_fields_sends_an_explicit_null_to_clear() -> None:
    """§6: `null` clears, absent leaves alone. Clearing a note is legitimate."""
    previous = {"text": "Toothpaste", "notes": "the mint one", "isChecked": True,
                "due": "2026-09-03"}

    cleared = TodoItem(
        uid="itm-2", summary="Toothpaste", status=TodoItemStatus.COMPLETED,
        description=None, due=date(2026, 9, 3),
    )
    assert _changed_fields(cleared, previous) == {"notes": None}


def test_changed_fields_never_mentions_fields_home_assistant_cannot_see() -> None:
    """The whole GAP-003 hazard, asserted.

    `quantity`, `sectionId` and `assignedMembershipId` are absent from Home
    Assistant's model. If they ever appear in a patch body they can only be
    carrying a guess, and under merge-patch a guess overwrites.
    """
    previous = {"text": "Apples", "notes": None, "isChecked": False, "due": None,
                "quantity": "6", "sectionId": "sec-1", "assignedMembershipId": "mem-1"}
    item = TodoItem(uid="itm-1", summary="Apples", status=TodoItemStatus.COMPLETED)

    changes = _changed_fields(item, previous)

    for invisible in ("quantity", "sectionId", "assignedMembershipId", "position", "id"):
        assert invisible not in changes


async def test_ticking_a_checkbox_sends_only_the_checkbox(
    hass: HomeAssistant, setup_todo: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """End to end: the commonest write in the whole integration.

    A shopping list item carries a quantity, a section and an assignee that Home
    Assistant knows nothing about. Ticking it must not disturb any of them.
    """
    aioclient_mock.clear_requests()
    aioclient_mock.patch(f"{ITEMS_1}/itm-1", json={"id": "itm-1"})
    _mock_all(aioclient_mock)

    await hass.services.async_call(
        "todo",
        "update_item",
        {"entity_id": SHOPPING, "item": "Apples", "status": "completed"},
        blocking=True,
    )

    patches = [c for c in aioclient_mock.mock_calls if c[0] == "PATCH"]
    assert len(patches) == 1
    assert patches[0][2] == {"isChecked": True}


async def test_renaming_does_not_resend_the_checkbox(
    hass: HomeAssistant, setup_todo: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Echoing an unchanged field makes this client authoritative over it.

    Under merge-patch that is not destructive, but it does mean a concurrent
    edit from somebody's phone loses for no reason at all.
    """
    aioclient_mock.clear_requests()
    aioclient_mock.patch(f"{ITEMS_1}/itm-2", json={"id": "itm-2"})
    _mock_all(aioclient_mock)

    await hass.services.async_call(
        "todo",
        "update_item",
        {"entity_id": SHOPPING, "item": "Toothpaste", "rename": "Toothpaste (mint)"},
        blocking=True,
    )

    body = [c for c in aioclient_mock.mock_calls if c[0] == "PATCH"][0][2]
    assert body == {"text": "Toothpaste (mint)"}
    assert "isChecked" not in body
    assert "due" not in body


async def test_an_update_that_changes_nothing_makes_no_request(
    hass: HomeAssistant, setup_todo: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """§6: an empty PATCH body is a 400. Sending one would be a self-inflicted error."""
    aioclient_mock.clear_requests()
    _mock_all(aioclient_mock)

    await hass.services.async_call(
        "todo",
        "update_item",
        {"entity_id": SHOPPING, "item": "Apples", "status": "needs_action"},
        blocking=True,
    )

    assert not [c for c in aioclient_mock.mock_calls if c[0] == "PATCH"]


# --- create and delete ------------------------------------------------------


async def test_adding_an_item_sends_a_client_chosen_id(
    hass: HomeAssistant, setup_todo: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """§7: a retry without an id creates the item twice.

    A timed-out request is indistinguishable from a lost reply, so the id is
    chosen here and the retry becomes idempotent — no duplicate "milk".
    """
    aioclient_mock.clear_requests()
    aioclient_mock.post(ITEMS_1, json={"id": "whatever"}, status=201)
    _mock_all(aioclient_mock)

    await hass.services.async_call(
        "todo", "add_item", {"entity_id": SHOPPING, "item": "Milk"}, blocking=True
    )

    body = [c for c in aioclient_mock.mock_calls if c[0] == "POST"][0][2]
    assert body["text"] == "Milk"
    assert isinstance(body["id"], str) and body["id"]
    # position is computed server-side and rejected if sent (§7).
    assert "position" not in body
    # Nothing the user did not supply.
    assert "notes" not in body and "due" not in body


async def test_adding_with_a_due_day_sends_a_date_not_an_instant(
    hass: HomeAssistant, setup_todo: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """"Due Thursday" must not become a moment on Wednesday evening somewhere."""
    aioclient_mock.clear_requests()
    aioclient_mock.post(ITEMS_1, json={"id": "x"}, status=201)
    _mock_all(aioclient_mock)

    await hass.services.async_call(
        "todo",
        "add_item",
        {"entity_id": SHOPPING, "item": "Bread", "due_date": "2026-09-10"},
        blocking=True,
    )

    body = [c for c in aioclient_mock.mock_calls if c[0] == "POST"][0][2]
    assert body["due"] == "2026-09-10"
    assert "T" not in body["due"]


async def test_adding_with_a_due_time_sends_an_instant(
    hass: HomeAssistant, setup_todo: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """And a moment stays a moment — which is why both flags are honourable."""
    aioclient_mock.clear_requests()
    aioclient_mock.post(ITEMS_1, json={"id": "x"}, status=201)
    _mock_all(aioclient_mock)

    await hass.services.async_call(
        "todo",
        "add_item",
        {"entity_id": SHOPPING, "item": "Call the vet",
         "due_datetime": "2026-09-10 14:30:00"},
        blocking=True,
    )

    body = [c for c in aioclient_mock.mock_calls if c[0] == "POST"][0][2]
    assert "T" in body["due"]
    assert body["due"].endswith("Z")


async def test_removing_completed_items_deletes_each_one(
    hass: HomeAssistant, setup_todo: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Only the completed one, and by id."""
    aioclient_mock.clear_requests()
    aioclient_mock.delete(f"{ITEMS_1}/itm-2", json={"id": "itm-2", "deleted": True})
    _mock_all(aioclient_mock)

    await hass.services.async_call(
        "todo", "remove_completed_items", {"entity_id": SHOPPING}, blocking=True
    )

    deletes = [c for c in aioclient_mock.mock_calls if c[0] == "DELETE"]
    assert len(deletes) == 1
    assert str(deletes[0][1]).endswith("/itm-2")


# --- failure ----------------------------------------------------------------


async def test_a_rejected_write_surfaces_as_an_error(
    hass: HomeAssistant, setup_todo: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """A failed write must not look like a successful one."""
    aioclient_mock.clear_requests()
    aioclient_mock.patch(
        f"{ITEMS_1}/itm-1", status=400,
        json={"error": "unknown field: sparkle", "code": "bad_request"},
    )
    _mock_all(aioclient_mock)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "todo",
            "update_item",
            {"entity_id": SHOPPING, "item": "Apples", "status": "completed"},
            blocking=True,
        )


async def test_a_revoked_key_during_a_write_starts_reauth(
    hass: HomeAssistant, setup_todo: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """§3: never retry a 401, never fail silently — ask for a new key."""
    aioclient_mock.clear_requests()
    aioclient_mock.patch(
        f"{ITEMS_1}/itm-1", status=401,
        json={"error": "no", "code": "unauthenticated"},
    )
    _mock_all(aioclient_mock)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "todo",
            "update_item",
            {"entity_id": SHOPPING, "item": "Apples", "status": "completed"},
            blocking=True,
        )
    await hass.async_block_till_done()

    assert any(
        flow["context"]["source"] == "reauth"
        for flow in hass.config_entries.flow.async_progress()
    )


async def test_a_write_never_leaks_the_key(
    hass: HomeAssistant,
    setup_todo: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Same guarantee as everywhere else, on the newest code path."""
    aioclient_mock.clear_requests()
    aioclient_mock.patch(
        f"{ITEMS_1}/itm-1", status=500, json={"error": "boom", "code": "server_error"}
    )
    _mock_all(aioclient_mock)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "todo",
            "update_item",
            {"entity_id": SHOPPING, "item": "Apples", "status": "completed"},
            blocking=True,
        )

    assert API_KEY not in caplog.text


@pytest.mark.parametrize(
    "due",
    [date(2026, 9, 3), datetime(2026, 9, 4, 14, 30, tzinfo=dt_util.UTC), None],
    ids=["a-day", "a-moment", "nothing"],
)
def test_due_round_trips_through_the_wire(due) -> None:
    """Both due forms survive the round trip, which is what licenses both flags.

    `SET_DUE_DATE_ON_ITEM` and `SET_DUE_DATETIME_ON_ITEM` are separate
    capabilities, and declaring one you cannot honour means the UI offers a
    field that quietly loses information. §5 makes the form the meaning, so this
    checks the form survives out and back — a `date` must not come home as a
    `datetime` at midnight, which is how "due Thursday" becomes "due Wednesday
    evening" for anyone west of the authoring timezone.
    """
    from custom_components.calendora.todo import _due_from_wire, _due_to_wire

    returned = _due_from_wire(_due_to_wire(due))

    assert returned == due
    assert type(returned) is type(due)


async def test_a_write_refreshes_immediately_not_on_a_debounce(
    hass: HomeAssistant, setup_todo: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """A write must be visible before the user's next action.

    `async_request_refresh` is debounced by up to ten seconds — correct for a
    stream event, wrong for something the user just did. With it, adding an item
    and then ticking it fails with "unable to find to-do list item", because the
    item is not in `todo_items` yet. Found by installing into a real Home
    Assistant; no unit test sees a debouncer, so this one asserts the effect
    instead: the list is re-read before the service call returns.
    """
    aioclient_mock.clear_requests()
    aioclient_mock.post(ITEMS_1, json={"id": "new"}, status=201)
    _mock_all(aioclient_mock)

    await hass.services.async_call(
        "todo", "add_item", {"entity_id": SHOPPING, "item": "Milk"}, blocking=True
    )

    # The re-read happened as part of the call, not on a timer afterwards.
    assert [c for c in aioclient_mock.mock_calls if "lists/lst-1/items" in str(c[1])
            and c[0] == "GET"], "the list was not re-read before the call returned"


async def test_a_conflict_is_retried_once_with_a_fresh_diff(
    hass: HomeAssistant, setup_todo: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """§2: `conflict` is the only retryable code, and retrying is correct.

    A 409 means the request was right and somebody else got there first, with
    nothing applied. Treating it like a 400 would tell the user to stop when
    they should try again — which is exactly what this client did before the
    code existed, because 409 fell through to a generic "unexpected response".
    """
    aioclient_mock.clear_requests()
    attempts: list[dict] = []

    async def _conflict_then_ok(method, url, data):
        attempts.append(data)
        if len(attempts) == 1:
            return AiohttpClientMockResponse(
                method, url, status=409,
                json={"error": "somebody else changed this a moment ago", "code": "conflict"},
            )
        return AiohttpClientMockResponse(method, url, status=200, json={"id": "itm-1"})

    aioclient_mock.patch(f"{ITEMS_1}/itm-1", side_effect=_conflict_then_ok)
    _mock_all(aioclient_mock)

    await hass.services.async_call(
        "todo", "update_item",
        {"entity_id": SHOPPING, "item": "Apples", "status": "completed"},
        blocking=True,
    )

    assert len(attempts) == 2, "a conflict should be retried exactly once"
    assert attempts[0] == attempts[1] == {"isChecked": True}


async def test_a_second_conflict_is_reported_rather_than_looped(
    hass: HomeAssistant, setup_todo: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Retry once, not forever. A contested row must not spin."""
    aioclient_mock.clear_requests()
    aioclient_mock.patch(
        f"{ITEMS_1}/itm-1", status=409,
        json={"error": "somebody else changed this a moment ago", "code": "conflict"},
    )
    _mock_all(aioclient_mock)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "todo", "update_item",
            {"entity_id": SHOPPING, "item": "Apples", "status": "completed"},
            blocking=True,
        )

    assert len([c for c in aioclient_mock.mock_calls if c[0] == "PATCH"]) == 2


async def test_the_list_id_is_readable_by_an_automation(
    hass: HomeAssistant, setup_todo: MockConfigEntry
) -> None:
    """A blueprint needs the Calendora list id to build the deep link.

    It is otherwise only inside `unique_id`, which an automation cannot read —
    and the deep link is the iPhone's primary action, not a convenience.
    """
    attributes = hass.states.get(SHOPPING).attributes

    assert attributes["list_id"] == "lst-1"
    assert attributes["list_type"] == "shopping"
    assert attributes["section_count"] == 2
