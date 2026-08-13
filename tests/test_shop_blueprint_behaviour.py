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
#: The REAL Calendora to-do entity, set up from the real integration against
#: mocked HTTP — not a hand-made state object.
#:
#: The blueprint used to read `state_attr(todo_entity, 'items')`, and these
#: tests passed by publishing an `items` attribute with
#: `hass.states.async_set(...)`. **No Home Assistant to-do entity has such an
#: attribute**, and this one never did — it exposes `list_id`, `list_type` and
#: `section_count`. So the fixture invented the state shape the blueprint
#: wanted, the two agreed, and neither agreed with the integration in the next
#: directory. Driving the real entity is what stops that recurring.
TODO_ENTITY = "todo.test_household_shopping"
TAG = "calendora_shop_test"

#: A purpose-built API payload rather than the shared fixture, because these
#: tests need five open items. The INTEGRATION still translates it, so the
#: entity under test is the real one publishing its real shape — only the data
#: is chosen here.
_NAMES = ["Milk", "Bread", "Eggs", "Butter", "Coffee"]
LIST_ITEMS_PAYLOAD = {
    "listId": "lst-1",
    "sections": [],
    "items": [
        {
            "id": f"i{n}",
            "text": name,
            "quantity": None,
            "notes": None,
            "isChecked": False,
            "sectionId": None,
            "position": f"a{n}",
            "due": None,
            "assignedMembershipId": None,
        }
        for n, name in enumerate(_NAMES, start=1)
    ],
}


@pytest.fixture
def notifications(hass: HomeAssistant) -> list[ServiceCall]:
    return async_mock_service(hass, "notify", NOTIFY_SERVICE.split(".", 1)[1])


@pytest.fixture(name="phone")
def phone_fixture(hass: HomeAssistant, monkeypatch) -> str:
    """A mobile_app device, and the two lookups that turn it into a service.

    The blueprint sends through mobile_app's **device action** rather than a
    named service, because no Home Assistant selector yields a service name.
    At runtime that action resolves device id → webhook id → notify service.
    The device is real, registered against a real config entry; only the two
    webhook lookups are stubbed, because they read mobile_app's own storage
    which a test has no honest way to populate.

    Stubbing them is the smallest lie that still exercises the real device
    action — the schema, the template rendering and the service call underneath
    are all Home Assistant's.
    """
    from homeassistant.components.mobile_app import device_action
    from homeassistant.helpers import device_registry as dr
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain="mobile_app", data={})
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("mobile_app", "test-phone")},
        name="Test Phone",
    )
    monkeypatch.setattr(
        device_action, "webhook_id_from_device_id", lambda hass, device_id: "webhook-1"
    )
    monkeypatch.setattr(
        device_action,
        "get_notify_service",
        lambda hass, webhook_id: NOTIFY_SERVICE.split(".", 1)[1],
    )
    return device.id


@pytest.fixture
def ticked(aioclient_mock):
    """The item ids actually ticked off, read from the outgoing API requests.

    Not a spy on `todo.update_item`. That service now reaches the real Calendora
    entity, which writes to the API — so the truthful record of what got ticked
    is the request that left the house. A service spy would sit in front of the
    entity and prove only that something was asked for.
    """

    def _ids() -> list[str]:
        return [
            str(call[1]).rsplit("/", 1)[-1]
            for call in aioclient_mock.mock_calls
            if call[0] == "PATCH" and (call[2] or {}).get("isChecked") is True
        ]

    _ids.clear = aioclient_mock.mock_calls.clear
    return _ids


@pytest.fixture(name="phone")
def phone_fixture(hass: HomeAssistant, monkeypatch) -> str:
    """A mobile_app device, and the two lookups that turn it into a service.

    The blueprint sends through mobile_app's **device action** rather than a
    named service, because no Home Assistant selector yields a service name.
    At runtime that action resolves device id → webhook id → notify service.
    The device is real, registered against a real config entry; only the two
    webhook lookups are stubbed, because they read mobile_app's own storage
    which a test has no honest way to populate.

    Stubbing them is the smallest lie that still exercises the real device
    action — the schema, the template rendering and the service call underneath
    are all Home Assistant's.
    """
    from homeassistant.components.mobile_app import device_action
    from homeassistant.helpers import device_registry as dr
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain="mobile_app", data={})
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("mobile_app", "test-phone")},
        name="Test Phone",
    )
    monkeypatch.setattr(
        device_action, "webhook_id_from_device_id", lambda hass, device_id: "webhook-1"
    )
    monkeypatch.setattr(
        device_action,
        "get_notify_service",
        lambda hass, webhook_id: NOTIFY_SERVICE.split(".", 1)[1],
    )
    return device.id




async def _setup(
    hass: HomeAssistant, phone: str, mocker, *, completion_card: bool = False
) -> None:
    """Install the blueprint and build an automation from it.

    The blueprint is copied into the config directory rather than pointed at,
    because that is where Home Assistant looks for it and a test that reads it
    from anywhere else is not testing the file that ships.
    """
    target = Path(hass.config.path("blueprints/automation/calendora"))
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy(BLUEPRINT, target / BLUEPRINT.name)

    await hass.config.async_set_time_zone("UTC")
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
    hass.states.async_set(
        "person.test",
        "not_home",
        {"latitude": 40.0, "longitude": -80.0, "in_zones": []},
    )
    hass.states.async_set(
        "sensor.calendora_member_test", "ok", {"shop_notifications": True}
    )
    await _setup_calendora(hass, mocker)

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
                        "notify_device": phone,
                        "send_completion_card": completion_card,
                    },
                }
            }
        },
    )
    await hass.async_block_till_done()


async def _setup_calendora(hass: HomeAssistant, mocker) -> None:
    """Stand up the real integration so the real to-do entity exists.

    This is the repair for the defect these tests hid. They used to publish a
    to-do state by hand, complete with an `items` attribute that no Home
    Assistant to-do entity has — so the blueprint read the attribute, the
    fixture supplied it, and the pair agreed with each other while disagreeing
    with the integration in the next directory. Now the entity is built by the
    integration from an API response, and the blueprint has to get its items the
    way a household's would: through `todo.get_items`.
    """
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.calendora.const import API_BASE_URL, CONF_API_KEY, DOMAIN

    from .const import API_KEY, load_fixture

    base = f"{API_BASE_URL}/api/v1"
    mocker.get(f"{base}/household", json=load_fixture("household.json"))
    mocker.get(f"{base}/members", json=load_fixture("members.json"))
    mocker.get(f"{base}/events", json=load_fixture("events.json"))
    mocker.get(f"{base}/lists", json=load_fixture("lists.json"))
    mocker.get(f"{base}/lists/lst-1/items", json=LIST_ITEMS_PAYLOAD)
    mocker.get(f"{base}/lists/lst-2/items", json={"listId": "lst-2", "sections": [], "items": []})
    mocker.get(f"{base}/stream", text="", headers={"Content-Type": "text/event-stream"})
    for item in LIST_ITEMS_PAYLOAD["items"]:
        mocker.patch(f"{base}/lists/lst-1/items/{item['id']}", json={"id": item["id"]})

    entry = MockConfigEntry(
        domain=DOMAIN, title="Calendora", data={CONF_API_KEY: API_KEY}, version=2
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(TODO_ENTITY) is not None, "the real to-do entity is missing"


async def _arrive(
    hass: HomeAssistant, freezer, notifications: list[ServiceCall]
) -> None:
    """Walk the person into the shop and wait out the dwell.

    Every tap test does this now, and that is a correction rather than extra
    setup: a tap with no preceding trip is not a state a household can be in,
    and the tests that skipped it were exercising one that cannot happen. The
    90-minute expiry made that visible — it refuses a tap when the automation
    has never run, which is right, and which no test could tolerate while they
    were all tapping out of nowhere.

    Time is frozen because the blueprint will not send outside 07:00–21:30.
    """
    from datetime import timedelta

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    hass.states.async_set(
        "person.test",
        "The shop",
        {"latitude": 32.880837, "longitude": -117.237561, "in_zones": ["zone.the_shop"]},
    )
    await hass.async_block_till_done()
    freezer.move_to(dt_util.utcnow() + timedelta(minutes=3))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert notifications, "the trip did not start — no arrival card"
    notifications.clear()


async def _tap(
    hass: HomeAssistant, action: str, item_ids: list[str] | None = None, *, tag: str = TAG
) -> None:
    data: dict = {"action": action, "tag": tag}
    if item_ids is not None:
        data["action_data"] = {"item_ids": item_ids}
    hass.bus.async_fire("mobile_app_notification_action", data)
    await hass.async_block_till_done()


async def test_a_tap_ticks_the_items_and_the_card_comes_back(
    hass: HomeAssistant,
    notifications: list[ServiceCall],
    ticked,
    phone: str,
    freezer,
    aioclient_mock,
) -> None:
    """§6, the row with no debounce and no cap.

    This is the whole of #112: before it, a tap ended at `todo.update_item` and
    the shopper got silence from a card their tap had just dismissed.
    """
    freezer.move_to("2026-08-11 10:00:00+00:00")
    await _setup(hass, phone, aioclient_mock)
    await _arrive(hass, freezer, notifications)
    await _tap(hass, "CALENDORA_SHOP_GOT_BATCH", ["i1", "i2"])

    assert ticked() == ["i1", "i2"]
    assert len(notifications) == 1, "the tap produced no replacement card"

    card = notifications[0].data
    assert "3 things" in card["title"], f"wrong count in the title: {card['title']!r}"
    assert card["message"].startswith("Eggs, Butter, Coffee"), (
        f"the replacement should list what is left, not what was ticked: "
        f"{card['message']!r}"
    )
    assert "Milk" not in card["message"] and "Bread" not in card["message"]


async def test_the_replacement_carries_the_same_four_buttons(
    hass: HomeAssistant,
    notifications: list[ServiceCall],
    ticked,
    phone: str,
    freezer,
    aioclient_mock,
) -> None:
    """The anchor's payoff, observed at runtime rather than in the YAML.

    A shopper mid-trip is looking at the second card, not the first. If the two
    ever come apart, this is where a person notices.
    """
    freezer.move_to("2026-08-11 10:00:00+00:00")
    await _setup(hass, phone, aioclient_mock)
    await _arrive(hass, freezer, notifications)
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
    hass: HomeAssistant,
    notifications: list[ServiceCall],
    ticked,
    phone: str,
    freezer,
    aioclient_mock,
) -> None:
    """The todo service is mocked, so the entity still holds all five items.

    A blueprint that re-read the entity would send back a card identical to the
    one the shopper just cleared. That is not a hypothetical: `todo.update_item`
    returning does not mean the entity has settled, and the failure would be
    intermittent in a real house and absent in every unit test that does not
    hold the state still like this.
    """
    freezer.move_to("2026-08-11 10:00:00+00:00")
    await _setup(hass, phone, aioclient_mock)
    await _arrive(hass, freezer, notifications)
    await _tap(hass, "CALENDORA_SHOP_GOT_BATCH", ["i1", "i2"])

    # The entity still reports five open items: nothing has been re-read, and
    # `items` is not an attribute at all — asserting on one is what hid the
    # defect this test now guards.
    assert hass.states.get(TODO_ENTITY).state == "5"
    assert "items" not in hass.states.get(TODO_ENTITY).attributes
    assert "5 things" not in notifications[0].data["title"]


async def test_got_the_rest_ends_the_trip_without_a_replacement(
    hass: HomeAssistant,
    notifications: list[ServiceCall],
    ticked,
    phone: str,
    freezer,
    aioclient_mock,
) -> None:
    """Nothing is left, so there is no card to come back with.

    With the completion card off — the default — the correct behaviour is
    silence, not an empty list card.
    """
    freezer.move_to("2026-08-11 10:00:00+00:00")
    await _setup(hass, phone, aioclient_mock, completion_card=False)
    await _arrive(hass, freezer, notifications)
    await _tap(hass, "CALENDORA_SHOP_GOT_ALL")

    assert ticked() == ["i1", "i2", "i3", "i4", "i5"]
    assert notifications == [], (
        "an empty list must not produce a list card — and the completion card is off"
    )


async def test_the_completion_card_replaces_the_trip_card_when_switched_on(
    hass: HomeAssistant,
    notifications: list[ServiceCall],
    ticked,
    phone: str,
    freezer,
    aioclient_mock,
) -> None:
    """§6: "list cleared → one card, no buttons, silent."."""
    freezer.move_to("2026-08-11 10:00:00+00:00")
    await _setup(hass, phone, aioclient_mock, completion_card=True)
    await _arrive(hass, freezer, notifications)
    await _tap(hass, "CALENDORA_SHOP_GOT_ALL")

    assert len(notifications) == 1
    card = notifications[0].data
    assert "that's the lot" in card["title"]
    assert card["data"]["push"]["interruption-level"] == "passive"
    assert "actions" not in card["data"]
    assert card["data"]["tag"] == TAG


async def test_another_households_tap_is_ignored(
    hass: HomeAssistant,
    notifications: list[ServiceCall],
    ticked,
    phone: str,
    freezer,
    aioclient_mock,
) -> None:
    """Home Assistant does not route the action event to the automation that sent
    the notification — every automation on the instance sees every tap. The tag
    check is the only thing standing between two households' shopping lists.
    """
    freezer.move_to("2026-08-11 10:00:00+00:00")
    await _setup(hass, phone, aioclient_mock)
    await _arrive(hass, freezer, notifications)
    await _tap(hass, "CALENDORA_SHOP_GOT_BATCH", ["i1"], tag="calendora_shop_someone_else")

    assert ticked() == [] and notifications == []


async def test_a_tap_with_no_action_data_falls_back_to_the_batch_it_showed(
    hass: HomeAssistant,
    notifications: list[ServiceCall],
    ticked,
    phone: str,
    freezer,
    aioclient_mock,
) -> None:
    """The `action_data` device test (#67) is still unanswered.

    If the platform does not return per-action data, the tick falls back to the
    slice the card was built from. That fallback is correct while one message
    carries the whole list, and this pins the behaviour either way so the
    device test has something to confirm or contradict rather than a guess.
    """
    freezer.move_to("2026-08-11 10:00:00+00:00")
    await _setup(hass, phone, aioclient_mock)
    await _arrive(hass, freezer, notifications)
    await _tap(hass, "CALENDORA_SHOP_GOT_BATCH")

    assert ticked() == ["i1", "i2", "i3", "i4", "i5"]
    assert notifications == [], "a five-item list and a five-item batch leaves nothing"


async def test_arriving_at_the_shop_and_staying_sends_the_list(
    hass: HomeAssistant,
    notifications: list[ServiceCall],
    ticked,
    phone: str,
    freezer,
    aioclient_mock,
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
    await _setup_calendora(hass, aioclient_mock)
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
                        "notify_device": phone,
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


async def test_a_card_left_overnight_no_longer_ticks_anything(
    hass: HomeAssistant,
    notifications: list[ServiceCall],
    ticked,
    phone: str,
    freezer,
    aioclient_mock,
) -> None:
    """§6: the trip stops after 90 minutes.

    The failure this closes is quiet and plausible: somebody abandons a shop,
    the card stays in the notification shade with its buttons live, and a tap
    the next morning ticks **tomorrow's list** off yesterday's card. Nothing
    errors, nothing is logged, and the items simply go.

    Time is stepped rather than waited out — a test that only fails when the
    machine is slow gets re-run until green and then deleted.
    """
    from datetime import timedelta

    from homeassistant.util import dt as dt_util

    freezer.move_to("2026-08-11 10:00:00+00:00")
    await _setup(hass, phone, aioclient_mock)
    await _arrive(hass, freezer, notifications)

    # Still shopping twenty minutes in: the loop works.
    freezer.move_to(dt_util.utcnow() + timedelta(minutes=20))
    await _tap(hass, "CALENDORA_SHOP_GOT_BATCH", ["i1"])
    assert ticked() == ["i1"]
    assert len(notifications) == 1, "an active trip stopped answering taps"

    ticked.clear()
    notifications.clear()

    # The trip is abandoned. Ninety-one minutes after the last thing happened,
    # the card in the shade is a relic.
    freezer.move_to(dt_util.utcnow() + timedelta(minutes=91))
    await _tap(hass, "CALENDORA_SHOP_GOT_BATCH", ["i2"])

    assert ticked() == [], (
        "a tap 91 minutes after the trip went quiet still ticked an item off — "
        "that is yesterday's card editing today's list"
    )
    assert notifications == [], "an expired trip answered with a card"


async def test_a_long_shop_is_not_cut_off_while_it_is_still_being_shopped(
    hass: HomeAssistant,
    notifications: list[ServiceCall],
    ticked,
    phone: str,
    freezer,
    aioclient_mock,
) -> None:
    """The deliberate deviation from §6, asserted so it is a decision and not a bug.

    §6 says the trip stops 90 minutes after **arrival**. This measures 90
    minutes since the last thing that happened, so a slow shop with steady
    tapping keeps working past the two-hour mark. Somebody still ticking items
    off is still shopping, and cutting them off mid-aisle to honour the letter
    of the rule is the worse reading of it.
    """
    from datetime import timedelta

    from homeassistant.util import dt as dt_util

    freezer.move_to("2026-08-11 09:00:00+00:00")
    await _setup(hass, phone, aioclient_mock)
    await _arrive(hass, freezer, notifications)

    for index, uid in enumerate(("i1", "i2", "i3"), start=1):
        freezer.move_to(dt_util.utcnow() + timedelta(minutes=50))
        await _tap(hass, "CALENDORA_SHOP_GOT_BATCH", [uid])
        assert ticked() == [uid], (
            f"tap {index}, at {index * 50} minutes past arrival, was refused — "
            f"the expiry is measuring from arrival rather than from activity"
        )
        ticked.clear()


async def test_run_actions_in_the_ui_sends_the_card(
    hass: HomeAssistant,
    notifications,
    ticked,
    phone: str,
    freezer,
    aioclient_mock,
) -> None:
    """The button a person presses to ask "is this working?".

    It calls `automation.trigger`, which passes `trigger: {platform: None}` —
    defined, but with **no `id`**. Every branch of the `choose` opens with
    `condition: trigger`, so all of them are false and nothing happened at all.
    Correct, and useless: the one tool anyone reaches for to diagnose an
    automation was the one that could never answer.

    Four releases of this blueprint sent nothing for four different reasons, and
    every one of those days would have been shorter if this button had worked.
    """
    freezer.move_to("2026-08-13 10:00:00+00:00")
    await _setup(hass, phone, aioclient_mock)

    await hass.services.async_call(
        "automation",
        "trigger",
        {"entity_id": "automation.automation_0"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert len(notifications) == 1, (
        "pressing Run actions sent nothing — the dry run is not reachable"
    )
    card = notifications[0]
    assert "5 things" in card.data["title"]
    assert len(card.data["data"]["actions"]) == 4, (
        "the dry run must send the REAL card, buttons and all — a diagnostic "
        "that sends something simpler proves the simpler thing works"
    )
    assert ticked() == [], "a dry run must not tick anything off"


async def test_run_actions_says_why_when_it_cannot_send(
    hass: HomeAssistant,
    notifications,
    phone: str,
    freezer,
    aioclient_mock,
) -> None:
    """Silence with a reason beats silence.

    The opt-in is off here, which is a setup mistake and the single most likely
    reason a household gets nothing. Before this, the automation and the button
    both did exactly what they do when everything is fine.
    """
    freezer.move_to("2026-08-13 10:00:00+00:00")
    # The dry run reports through `persistent_notification.create`, which is not
    # registered unless the component is set up. A real Home Assistant always
    # has it; a test does not, and without this the service call fails and the
    # branch looks broken.
    assert await async_setup_component(hass, "persistent_notification", {})
    await _setup(hass, phone, aioclient_mock)
    hass.states.async_set(
        "sensor.calendora_member_test", "ok", {"shop_notifications": False}
    )
    await hass.async_block_till_done()

    await hass.services.async_call(
        "automation",
        "trigger",
        {"entity_id": "automation.automation_0"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert notifications == [], "sent to a member who has not opted in"

    # Persistent notifications stopped being entities in Home Assistant; they
    # live in their own store now, so `hass.states.get(...)` finds nothing and
    # a test written against the old shape would fail for the wrong reason.
    from homeassistant.components.persistent_notification import (
        _async_get_or_create_notifications,
    )

    notices = _async_get_or_create_notifications(hass)
    assert "calendora_shop_dry_run" in notices, (
        "nothing was sent and nothing said why — that is the failure mode this "
        "branch exists to end"
    )
    assert "not opted in" in notices["calendora_shop_dry_run"]["message"]
