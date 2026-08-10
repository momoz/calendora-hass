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
    """Every `action: <notify service>` call anywhere in the automation.

    Walks the tree instead of indexing a known path, because the shape of
    `choose`/`if`/`repeat` changes as the design grows and a hard-coded path
    would silently stop finding anything — passing while checking nothing.
    """
    found = [] if found is None else found
    if isinstance(node, dict):
        action = node.get("action")
        if isinstance(action, InputRef) and action.name == "notify_service":
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
    assert len(calls) >= 3, f"expected arrival, clear and completion sends, got {len(calls)}"


def test_the_completion_card_is_off_by_default(blueprint: dict) -> None:
    """The default has to be safe on a phone this blueprint cannot identify.

    There is no platform detection available to a blueprint. Defaulting this on
    would mean an Android household gets the one thing §10.3 forbids — a sound
    at the end of a shop — without ever having chosen it.
    """
    inputs = blueprint["blueprint"]["input"]
    assert "completion_card" in inputs, "the completion card input is gone"
    assert inputs["completion_card"]["default"] is False, (
        "the completion card must default to OFF — see DESIGN-shop-arrival.md "
        "§10.3. On Android this card cannot be sent silently, and a buzz to "
        "announce that a shop is over is worse than no card at all."
    )


def test_the_completion_card_is_passive_and_has_no_buttons(blueprint: dict) -> None:
    """§10.3 on iOS, §6 on the button set."""
    passive = [
        call
        for call in _notify_calls(blueprint)
        if call.get("data", {}).get("data", {}).get("push", {}).get("interruption-level")
        == "passive"
    ]
    assert len(passive) == 1, (
        f"expected exactly one passive send (the completion card), found {len(passive)}"
    )

    card = passive[0]["data"]["data"]
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
        call.get("data", {}).get("data", {}).get("channel")
        for call in _notify_calls(blueprint)
    }
    channels.discard(None)
    assert channels == {"Shopping list"}, (
        f"expected exactly one Android channel, found {sorted(channels)} — see "
        f"DESIGN-shop-arrival.md §10.3"
    )


def test_every_send_that_can_wake_a_phone_declares_its_interruption_level(
    blueprint: dict,
) -> None:
    """Nothing is time-sensitive, and nothing relies on the platform default.

    A shopping list is not allowed to break somebody's Focus (§8), and the
    default is the one thing that changes underneath you when an OS updates.
    """
    for call in _notify_calls(blueprint):
        card = call.get("data", {}).get("data", {})
        # The clear-notification call carries no content and cannot alert.
        if call.get("data", {}).get("message") == "clear_notification":
            continue
        level = card.get("push", {}).get("interruption-level")
        assert level in {"active", "passive"}, (
            f"a send left interruption-level unset ({level!r}) — state it rather "
            f"than inheriting a platform default"
        )
        assert level != "time-sensitive", "§8: a shopping list never breaks a Focus"
