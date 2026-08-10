"""Run the shopping blueprint, rather than reading it.

`test_shop_blueprint.py` asserts things about the YAML: which sends exist, that
the replacement is the arrival card and not a copy, that no second Android
channel appears. All of that is true of a file that Home Assistant would refuse
to run, or would run differently from how it reads.

These tests build the automation from the blueprint inside a real Home Assistant,
fire the events a phone fires, and look at what came out. Two things are only
observable here:

- **The tap loop actually closes.** §6's "the tap dismissed the card; something
  has to come back" is a claim about runtime behaviour, and until now nothing in
  this repository had ever executed it.
- **The replacement is built by subtraction, not by re-reading the list.** The
  todo service is mocked, so the list entity does *not* change when items are
  ticked. A blueprint that re-read the entity would send back the card the
  shopper just cleared, and these tests would catch it. That is a deliberate
  choice of fake: the real race — the entity not having settled yet — is exactly
  this, held still.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import async_mock_service

BLUEPRINT = (
    Path(__file__).resolve().parents[1]
    / "blueprints"
    / "automation"
    / "calendora"
    / "shopping_list_on_arrival.yaml"
)

NOTIFY_SERVICE = "notify.mobile_app_test_iphone"
TODO_ENTITY = "todo.shopping"
TAG = "calendora_shop_test"

ITEMS = [
    {"uid": "i1", "summary": "Milk", "status": "needs_action"},
    {"uid": "i2", "summary": "Bread", "status": "needs_action"},
    {"uid": "i3", "summary": "Eggs", "status": "needs_action"},
    {"uid": "i4", "summary": "Butter", "status": "needs_action"},
    {"uid": "i5", "summary": "Coffee", "status": "needs_action"},
]


@pytest.fixture
def notifications(hass: HomeAssistant) -> list[ServiceCall]:
    return async_mock_service(hass, "notify", NOTIFY_SERVICE.split(".", 1)[1])


@pytest.fixture
def ticked(hass: HomeAssistant) -> list[ServiceCall]:
    return async_mock_service(hass, "todo", "update_item")


async def _setup(hass: HomeAssistant, *, completion_card: bool = False) -> None:
    """Install the blueprint and build an automation from it.

    The blueprint is copied into the config directory rather than pointed at,
    because that is where Home Assistant looks for it and a test that reads it
    from anywhere else is not testing the file that ships.
    """
    target = Path(hass.config.path("blueprints/automation/calendora"))
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy(BLUEPRINT, target / BLUEPRINT.name)

    hass.states.async_set("person.test", "not_home")
    hass.states.async_set("zone.the_shop", 0, {"friendly_name": "Tesco"})
    hass.states.async_set(
        "sensor.calendora_member_test", "ok", {"shop_notifications": True}
    )
    hass.states.async_set(
        TODO_ENTITY,
        len(ITEMS),
        {"friendly_name": "Shopping", "list_id": "list-123", "items": ITEMS},
    )

    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": {
                "use_blueprint": {
                    "path": "calendora/shopping_list_on_arrival.yaml",
                    "input": {
                        "person": "person.test",
                        "calendora_member": "sensor.calendora_member_test",
                        "shop_zone": "zone.the_shop",
                        "todo_entity": TODO_ENTITY,
                        "notify_service": NOTIFY_SERVICE,
                        "send_completion_card": completion_card,
                    },
                }
            }
        },
    )
    await hass.async_block_till_done()


async def _tap(
    hass: HomeAssistant, action: str, item_ids: list[str] | None = None, *, tag: str = TAG
) -> None:
    data: dict = {"action": action, "tag": tag}
    if item_ids is not None:
        data["action_data"] = {"item_ids": item_ids}
    hass.bus.async_fire("mobile_app_notification_action", data)
    await hass.async_block_till_done()


async def test_a_tap_ticks_the_items_and_the_card_comes_back(
    hass: HomeAssistant, notifications: list[ServiceCall], ticked: list[ServiceCall]
) -> None:
    """§6, the row with no debounce and no cap.

    This is the whole of #112: before it, a tap ended at `todo.update_item` and
    the shopper got silence from a card their tap had just dismissed.
    """
    await _setup(hass)
    await _tap(hass, "CALENDORA_SHOP_GOT_BATCH", ["i1", "i2"])

    assert [call.data["item"] for call in ticked] == ["i1", "i2"]
    assert len(notifications) == 1, "the tap produced no replacement card"

    card = notifications[0].data
    assert "3 things" in card["title"], f"wrong count in the title: {card['title']!r}"
    assert card["message"].startswith("Eggs, Butter, Coffee"), (
        f"the replacement should list what is left, not what was ticked: "
        f"{card['message']!r}"
    )
    assert "Milk" not in card["message"] and "Bread" not in card["message"]


async def test_the_replacement_carries_the_same_four_buttons(
    hass: HomeAssistant, notifications: list[ServiceCall], ticked: list[ServiceCall]
) -> None:
    """The anchor's payoff, observed at runtime rather than in the YAML.

    A shopper mid-trip is looking at the second card, not the first. If the two
    ever come apart, this is where a person notices.
    """
    await _setup(hass)
    await _tap(hass, "CALENDORA_SHOP_GOT_BATCH", ["i1"])

    card = notifications[0].data["data"]
    assert [action["action"] for action in card["actions"]] == [
        "CALENDORA_SHOP_GOT_BATCH",
        "CALENDORA_SHOP_GOT_ALL",
        "CALENDORA_SHOP_STOP",
        "CALENDORA_SHOP_OPEN",
    ]
    assert card["tag"] == TAG, "the replacement must replace the card, not stack beside it"
    assert card["push"]["interruption-level"] == "active"
    assert card["action_data"]["item_ids"] == ["i2", "i3", "i4", "i5"], (
        "the replacement's buttons must carry the items it is showing, not the "
        "ones the last card showed"
    )


async def test_the_replacement_is_not_read_back_from_the_list_entity(
    hass: HomeAssistant, notifications: list[ServiceCall], ticked: list[ServiceCall]
) -> None:
    """The todo service is mocked, so the entity still holds all five items.

    A blueprint that re-read the entity would send back a card identical to the
    one the shopper just cleared. That is not a hypothetical: `todo.update_item`
    returning does not mean the entity has settled, and the failure would be
    intermittent in a real house and absent in every unit test that does not
    hold the state still like this.
    """
    await _setup(hass)
    await _tap(hass, "CALENDORA_SHOP_GOT_BATCH", ["i1", "i2"])

    assert len(hass.states.get(TODO_ENTITY).attributes["items"]) == 5
    assert "5 things" not in notifications[0].data["title"]


async def test_got_the_rest_ends_the_trip_without_a_replacement(
    hass: HomeAssistant, notifications: list[ServiceCall], ticked: list[ServiceCall]
) -> None:
    """Nothing is left, so there is no card to come back with.

    With the completion card off — the default — the correct behaviour is
    silence, not an empty list card.
    """
    await _setup(hass, completion_card=False)
    await _tap(hass, "CALENDORA_SHOP_GOT_ALL")

    assert [call.data["item"] for call in ticked] == ["i1", "i2", "i3", "i4", "i5"]
    assert notifications == [], (
        "an empty list must not produce a list card — and the completion card is off"
    )


async def test_the_completion_card_replaces_the_trip_card_when_switched_on(
    hass: HomeAssistant, notifications: list[ServiceCall], ticked: list[ServiceCall]
) -> None:
    """§6: "list cleared → one card, no buttons, silent."."""
    await _setup(hass, completion_card=True)
    await _tap(hass, "CALENDORA_SHOP_GOT_ALL")

    assert len(notifications) == 1
    card = notifications[0].data
    assert "that's the lot" in card["title"]
    assert card["data"]["push"]["interruption-level"] == "passive"
    assert "actions" not in card["data"]
    assert card["data"]["tag"] == TAG


async def test_another_households_tap_is_ignored(
    hass: HomeAssistant, notifications: list[ServiceCall], ticked: list[ServiceCall]
) -> None:
    """Home Assistant does not route the action event to the automation that sent
    the notification — every automation on the instance sees every tap. The tag
    check is the only thing standing between two households' shopping lists.
    """
    await _setup(hass)
    await _tap(hass, "CALENDORA_SHOP_GOT_BATCH", ["i1"], tag="calendora_shop_someone_else")

    assert ticked == [] and notifications == []


async def test_a_tap_with_no_action_data_falls_back_to_the_batch_it_showed(
    hass: HomeAssistant, notifications: list[ServiceCall], ticked: list[ServiceCall]
) -> None:
    """The `action_data` device test (#67) is still unanswered.

    If the platform does not return per-action data, the tick falls back to the
    slice the card was built from. That fallback is correct while one message
    carries the whole list, and this pins the behaviour either way so the
    device test has something to confirm or contradict rather than a guess.
    """
    await _setup(hass)
    await _tap(hass, "CALENDORA_SHOP_GOT_BATCH")

    assert [call.data["item"] for call in ticked] == ["i1", "i2", "i3", "i4", "i5"]
    assert notifications == [], "a five-item list and a five-item batch leaves nothing"


async def test_arriving_at_the_shop_and_staying_sends_the_list(
    hass: HomeAssistant,
    notifications: list[ServiceCall],
    ticked: list[ServiceCall],
    freezer,
) -> None:
    """The dwell trigger, which had never been executed by anything.

    This is the regression guard for the bug that made the whole automation
    unloadable: `for` on the `zone.entered` trigger is validated with
    `cv.positive_time_period`, which takes a duration and no template, and the
    blueprint passed it `"{{ dwell_minutes }}"`. Home Assistant rejected the
    generated automation at config validation and logged one line, so the
    symptom was not "the dwell is wrong" but "nothing ever happens" — which
    looks exactly like nobody having gone to the shop yet.

    Time is frozen rather than left to the clock: the blueprint refuses to send
    outside 07:00–21:30, so an unfrozen version of this test would pass all day
    and fail in the evening.
    """
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    await hass.config.async_set_time_zone("UTC")
    freezer.move_to("2026-08-09 10:00:00+00:00")

    assert await async_setup_component(
        hass,
        "zone",
        {
            "zone": {
                "name": "The shop",
                "latitude": 32.880837,
                "longitude": -117.237561,
                "radius": 250,
            }
        },
    )
    await hass.async_block_till_done()

    hass.states.async_set(
        "sensor.calendora_member_test", "ok", {"shop_notifications": True}
    )
    hass.states.async_set(
        TODO_ENTITY,
        len(ITEMS),
        {"friendly_name": "Shopping", "list_id": "list-123", "items": ITEMS},
    )
    # `in_zones` is what the trigger actually reads. `zone.entered` does not do
    # geometry against the person's coordinates — it asks the person entity
    # which zones it considers itself in, an attribute only `person` and
    # `device_tracker` publish. A test that sets only latitude and longitude
    # sits inside the zone on paper and never triggers.
    hass.states.async_set(
        "person.test",
        "not_home",
        {"latitude": 40.0, "longitude": -80.0, "in_zones": []},
    )
    await hass.async_block_till_done()

    target = Path(hass.config.path("blueprints/automation/calendora"))
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy(BLUEPRINT, target / BLUEPRINT.name)
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": {
                "use_blueprint": {
                    "path": "calendora/shopping_list_on_arrival.yaml",
                    "input": {
                        "person": "person.test",
                        "calendora_member": "sensor.calendora_member_test",
                        "shop_zone": "zone.the_shop",
                        "todo_entity": TODO_ENTITY,
                        "notify_service": NOTIFY_SERVICE,
                    },
                }
            }
        },
    )
    await hass.async_block_till_done()
    assert hass.states.get("automation.automation_0") is not None, (
        "the automation was not created — the blueprint generated an invalid "
        "automation and Home Assistant discarded it"
    )

    # Arrive.
    hass.states.async_set(
        "person.test",
        "The shop",
        {
            "latitude": 32.880837,
            "longitude": -117.237561,
            "in_zones": ["zone.the_shop"],
        },
    )
    await hass.async_block_till_done()
    assert notifications == [], "sent on arrival — the dwell was not waited out"

    # Ninety seconds in: still nothing. This half matters as much as the other,
    # because a dwell that fires immediately is what the two minutes exist to
    # prevent — a red light outside the shop, or a drop-off in the car park.
    freezer.move_to("2026-08-09 10:01:30+00:00")
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert notifications == [], "sent after ninety seconds — the dwell is too short"

    # Two and a half minutes in.
    freezer.move_to("2026-08-09 10:02:30+00:00")
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()

    assert len(notifications) == 1, "stayed two minutes and no list arrived"
    card = notifications[0].data
    assert "Tesco" in card["title"] or "shop" in card["title"].lower()
    assert "5 things" in card["title"]
    assert card["data"]["tag"] == TAG
    assert len(card["data"]["actions"]) == 4
