"""Structural guards on the shopping blueprint.

`hassfest` checks that the blueprint is valid. It has no opinion about whether
it is the blueprint the design asked for, and the two decisions encoded here are
both the kind that get undone by a well-meaning edit months later:

- **No completion card on Android** (`DESIGN-shop-arrival.md` §10.3), decided
  rather than measured. The tempting repair — send it anyway, at normal
  importance, with quieter copy — is explicitly forbidden, and it is exactly
  what somebody reaches for when a card does not arrive on their phone.
- **The completion card carries no buttons** (§6). There is nothing left to
  tick, so an action on it could only be a way to get it wrong.

- **The replacement is the arrival card, not a copy of it** (§6). It is a YAML
  anchor, and the moment somebody expands it into a second payload the two start
  drifting — the arrival grows a button the replacement does not have, and the
  shopper finds it missing mid-trip.

These are asserted against the parsed YAML rather than a substring search, so
they survive reformatting and fail on meaning.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

BLUEPRINT = (
    Path(__file__).resolve().parents[1]
    / "blueprints"
    / "automation"
    / "calendora"
    / "shopping_list_on_arrival.yaml"
)


class _InputTolerantLoader(yaml.SafeLoader):
    """`!input` is a Home Assistant YAML tag, not a value.

    SafeLoader refuses unknown tags outright, so the blueprint cannot be parsed
    at all without teaching it this one. Resolving to a marker object rather
    than a string keeps a test from confusing an input reference with a literal.
    """


class InputRef:
    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"!input {self.name}"


_InputTolerantLoader.add_constructor(
    "!input", lambda loader, node: InputRef(loader.construct_scalar(node))
)


@pytest.fixture(scope="module")
def blueprint() -> dict:
    return yaml.load(BLUEPRINT.read_text(encoding="utf-8"), Loader=_InputTolerantLoader)


def _notify_calls(node, found=None) -> list[dict]:
    """Every mobile_app notify anywhere in the automation.

    A DEVICE ACTION rather than a service call since 0.4.4 — `domain`, `type`
    and `device_id` at the step's top level, with `title`, `message` and `data`
    beside them rather than nested under `data:`. See the blueprint's
    `notify_device` input for why: no selector in Home Assistant yields a
    service-name string, so `action: !input …` could never have worked.

    Walks the tree instead of indexing a known path, because the shape of
    `choose`/`if`/`repeat` changes as the design grows and a hard-coded path
    would silently stop finding anything — passing while checking nothing.
    """
    found = [] if found is None else found
    if isinstance(node, dict):
        if node.get("domain") == "mobile_app" and node.get("type") == "notify":
            found.append(node)
        for value in node.values():
            _notify_calls(value, found)
    elif isinstance(node, list):
        for item in node:
            _notify_calls(item, found)
    return found


def test_the_blueprint_parses_and_has_notify_calls(blueprint: dict) -> None:
    """Guard against every assertion below passing vacuously."""
    calls = _notify_calls(blueprint)
    assert len(calls) >= 4, (
        f"expected arrival, clear, replacement and completion sends, got {len(calls)}"
    )


def test_the_completion_card_is_off_by_default(blueprint: dict) -> None:
    """The default has to be safe on a phone this blueprint cannot identify.

    There is no platform detection available to a blueprint. Defaulting this on
    would mean an Android household gets the one thing §10.3 forbids — a sound
    at the end of a shop — without ever having chosen it.
    """
    inputs = blueprint["blueprint"]["input"]
    assert "send_completion_card" in inputs, (
        "the completion card input is gone, or is not called what §0's PERMANENT "
        "table calls it. Input keys are a public API: an automation built on one "
        "name breaks the day it is corrected."
    )
    assert inputs["send_completion_card"]["default"] is False, (
        "the completion card must default to OFF — see DESIGN-shop-arrival.md "
        "§10.3. On Android this card cannot be sent silently, and a buzz to "
        "announce that a shop is over is worse than no card at all."
    )


def test_the_completion_card_is_passive_and_has_no_buttons(blueprint: dict) -> None:
    """§10.3 on iOS, §6 on the button set."""
    passive = [
        call
        for call in _notify_calls(blueprint)
        if call.get("data", {}).get("push", {}).get("interruption-level")
        == "passive"
    ]
    assert len(passive) == 1, (
        f"expected exactly one passive send (the completion card), found {len(passive)}"
    )

    card = passive[0]["data"]
    assert "actions" not in card, (
        "the completion card must carry no buttons (§6) — nothing is left to tick"
    )
    assert "channel" not in card, (
        "the completion card must not name an Android channel — §10.3 decides "
        "against a second channel rather than leaving it unverified"
    )


def test_no_second_android_channel_anywhere(blueprint: dict) -> None:
    """§10.3, the decision that must not be quietly reversed.

    The low-importance completion channel was never verified, an Android
    channel's importance is frozen at creation, and Android is out of scope. A
    future edit adding one would be permanent on every device that received it.
    """
    channels = {
        call.get("data", {}).get("channel")
        for call in _notify_calls(blueprint)
    }
    channels.discard(None)
    assert channels == {"Shopping list"}, (
        f"expected exactly one Android channel, found {sorted(channels)} — see "
        f"DESIGN-shop-arrival.md §10.3"
    )


def test_the_replacement_is_the_arrival_card_and_not_a_copy(blueprint: dict) -> None:
    """§6 — "your own tap → replacement immediately, always, no debounce."

    The replacement is the same YAML node as the arrival send, reached through
    an anchor, so `is` holds. That identity is the point of this test: two
    separately-written payloads would pass any equality check on the day they
    were written and drift apart on the first edit that touches one of them. The
    failure mode is invisible until a shopper taps *Got these* mid-trip and the
    card that comes back is missing a button the first one had.

    If this fails because somebody expanded the alias, the repair is the anchor,
    not a second assertion that the two copies match.
    """
    cards = [
        call
        for call in _notify_calls(blueprint)
        if call.get("data", {}).get("actions")
    ]
    assert len(cards) == 2, (
        f"expected the list card to be sent twice — on arrival and as the "
        f"replacement after a tap — found {len(cards)} sends carrying buttons"
    )
    assert cards[0] is cards[1], (
        "the replacement has been expanded into its own copy of the arrival "
        "payload. It is one card sent twice (§6); two copies drift, and the "
        "drift only shows up mid-shop. Restore the `*shop_card` alias."
    )


def test_the_replacement_is_built_from_the_list_as_it_stands_after_the_tap(
    blueprint: dict,
) -> None:
    """The rebind is what makes one node correct in both places.

    `&shop_card` reads `outstanding`, `showing` and `remaining`. The ticking
    branch subtracts what the tap ticked and rebinds all three before sending
    it again. Lose that step and the replacement is a byte-identical re-send of
    the card the shopper just cleared — which looks like the tap did nothing,
    the exact failure §6 is written to prevent.

    Subtraction rather than re-reading the entity is deliberate: the
    `todo.update_item` calls have returned but the list entity is not
    guaranteed to have settled, and a card that is right only sometimes is
    worse than one that is wrong every time, because nobody chases it.
    """
    blocks = _find_variable_rebinds(blueprint)
    assert len(blocks) == 2, (
        f"expected `outstanding` to be defined twice — once from the entity at "
        f"the top, once by subtraction after the tick — found {len(blocks)}"
    )
    source, rebind = blocks
    assert "state_attr" in source["outstanding"], (
        "the first definition should read the list from the entity"
    )
    assert "rejectattr" in rebind["outstanding"] and "ticking" in rebind["outstanding"], (
        f"`outstanding` is rebound, but not by subtracting what this tap ticked: "
        f"{rebind['outstanding']!r}"
    )
    assert "state_attr" not in rebind["outstanding"], (
        "the replacement re-reads the list entity. The tick calls have returned "
        "but the entity is not guaranteed to have settled — subtract `ticking` "
        "from the list already in hand instead."
    )
    for name in ("showing", "remaining"):
        assert name in rebind, (
            f"`{name}` is not rebound alongside `outstanding`, so the replacement "
            f"card's body and its 'Then N more' count still describe the pre-tap list"
        )


def _find_variable_rebinds(node, found=None) -> list[dict]:
    """Every `variables:` step that redefines `outstanding`.

    Walked rather than indexed for the same reason as `_notify_calls`: a
    hard-coded path stops finding anything the moment the branch structure
    changes, and passes while checking nothing.
    """
    found = [] if found is None else found
    if isinstance(node, dict):
        variables = node.get("variables")
        if isinstance(variables, dict) and "outstanding" in variables:
            found.append(variables)
        for value in node.values():
            _find_variable_rebinds(value, found)
    elif isinstance(node, list):
        for item in node:
            _find_variable_rebinds(item, found)
    return found


def test_every_send_that_can_wake_a_phone_declares_its_interruption_level(
    blueprint: dict,
) -> None:
    """Nothing is time-sensitive, and nothing relies on the platform default.

    A shopping list is not allowed to break somebody's Focus (§8), and the
    default is the one thing that changes underneath you when an OS updates.
    """
    for call in _notify_calls(blueprint):
        card = call.get("data", {})
        # The clear-notification call carries no content and cannot alert.
        if call.get("message") == "clear_notification":
            continue
        level = card.get("push", {}).get("interruption-level")
        assert level in {"active", "passive"}, (
            f"a send left interruption-level unset ({level!r}) — state it rather "
            f"than inheriting a platform default"
        )
        assert level != "time-sensitive", "§8: a shopping list never breaks a Focus"


async def test_the_anchor_survives_home_assistant_s_own_loader(hass) -> None:
    """The tests above parse with PyYAML. Home Assistant does not.

    An anchor is the one construct in this file where that distinction can
    bite: HA loads blueprints with its own loader, then walks the parsed tree
    substituting `!input`, and the aliased node is reached twice on that walk.
    If substitution were destructive, or if the loader dropped aliases, the
    replacement card would arrive with `!input notify_service` unresolved — and
    nothing that parses the file with PyYAML would ever see it.

    So this loads it the way a household's Home Assistant does, substitutes real
    inputs, and checks the far side.
    """
    from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
    from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA
    from homeassistant.util.yaml import loader as yaml_loader
    from homeassistant.util.yaml.objects import Input

    blueprint = Blueprint(
        yaml_loader.parse_yaml(BLUEPRINT.read_text(encoding="utf-8")),
        expected_domain="automation",
        schema=BLUEPRINT_SCHEMA,
    )
    notify_service = "0123456789abcdef0123456789abcdef"  # a device id now
    substitutions = {
        "todo_entity": "todo.shopping",
        "person": "person.test",
        "calendora_member": "sensor.calendora_member_test",
        "shop_zone": "zone.the_shop",
        "notify_device": notify_service,
        "dwell_minutes": {"minutes": 2},
        "batch_size": 5,
        "revisit_hours": 2,
        "send_completion_card": True,
        "quiet_from": "21:30:00",
        "quiet_until": "07:00:00",
    }
    assert set(blueprint.inputs) == set(substitutions), (
        f"the blueprint's inputs have changed: {sorted(set(blueprint.inputs) ^ set(substitutions))}"
    )

    resolved = BlueprintInputs(
        blueprint, {"use_blueprint": {"path": "x.yaml", "input": substitutions}}
    ).async_substitute()

    def _walk(node):
        if isinstance(node, dict):
            yield node
            for value in node.values():
                yield from _walk(value)
        elif isinstance(node, list):
            for item in node:
                yield from _walk(item)

    nodes = list(_walk(resolved))
    assert not any(isinstance(value, Input) for node in nodes for value in node.values()), (
        "an `!input` survived substitution — the aliased node was not resolved"
    )

    sends = [
        node
        for node in nodes
        if node.get("domain") == "mobile_app" and node.get("type") == "notify"
    ]
    assert len(sends) == 4, (
        f"expected four sends after substitution — arrival, clear, replacement, "
        f"completion — found {len(sends)}"
    )
    with_buttons = [s for s in sends if s.get("data", {}).get("actions")]
    assert len(with_buttons) == 2, "the replacement lost its buttons in substitution"
    assert with_buttons[0]["data"] == with_buttons[1]["data"], (
        "the arrival and the replacement came out of substitution differing"
    )
