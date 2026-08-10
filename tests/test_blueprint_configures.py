"""Can a person actually save an automation built from this blueprint?

**This is the gate that did not exist, and its absence cost the fourth release in
a row.** `0.4.0`–`0.4.2` could not be *loaded*. `0.4.3` loads and cannot be
*configured*: a real household picked its inputs, pressed save, and Home
Assistant answered

    Message malformed: value should be a string for dictionary value
      @ data['actions'][1]['choose'][0]['sequence'][0]['action']

Substituting `!input` values and validating the result is a separate gate from
loading the blueprint, and it is the one a user meets first.

**Why the existing substitution test did not catch it, which is the part worth
learning.** `test_shop_blueprint.py` already substitutes inputs and runs the
result through Home Assistant — and it passed throughout, because *I chose the
values*, and I chose `notify_service: "notify.mobile_app_test_iphone"`: a plain
string, the shape the code wants, picked by the person who wrote the code. **A
judge fed by the defendant.** The `action` selector actually yields an action
*sequence* — a list — and no test had ever fed it one, because nobody who
believed it was a service name would think to.

So the rule here is: **input values are derived from the selector each input
declares, not written by hand.** `_ui_value_for` below is the whole point of the
file. When a new input appears with a selector it does not know, it fails rather
than skipping — a gate that silently ignores what it does not recognise is the
thing this file exists to stop.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import voluptuous as vol
from homeassistant.components.automation.config import async_validate_config_item
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA
from homeassistant.core import HomeAssistant
from homeassistant.util.yaml import loader as yaml_loader

BLUEPRINT = (
    Path(__file__).resolve().parents[1]
    / "blueprints"
    / "automation"
    / "calendora"
    / "shopping_list_on_arrival.yaml"
)


def _ui_value_for(name: str, definition: dict[str, Any], device_id: str) -> Any:
    """The shape Home Assistant's UI hands back for this input's selector.

    Deliberately keyed on the **selector**, never on the input's name or on what
    the blueprint body does with it. That is the whole guard: an input's name
    says what its author meant, and the selector says what the user interface
    will actually produce, and this file exists because those two disagreed.
    """
    selector = definition.get("selector") or {}
    kind = next(iter(selector), None)

    if kind == "entity":
        # Honour the selector's own domain filter rather than picking a domain.
        # The UI will only ever offer an entity the filter permits, so a fixture
        # that ignores it is testing a state the user cannot reach — and Home
        # Assistant enforces it, which is how this was caught.
        config = selector["entity"] or {}
        filters = config.get("filter") or [{}]
        if isinstance(filters, dict):
            filters = [filters]
        domain = filters[0].get("domain", "sensor")
        if isinstance(domain, list):
            domain = domain[0]
        return f"{domain}.example"
    if kind == "device":
        # A REAL device id from the registry, not a plausible-looking string.
        # Device-action validation resolves the device and rejects an unknown
        # one, so a made-up id fails for the wrong reason and would have hidden
        # whether the action itself is well-formed.
        return device_id
    if kind == "duration":
        return {"hours": 0, "minutes": 2, "seconds": 0}
    if kind == "number":
        return definition.get("default", 1)
    if kind == "boolean":
        return bool(definition.get("default", False))
    if kind == "time":
        return definition.get("default", "07:00:00")
    if kind == "text":
        return "some text"
    if kind == "action":
        # An action SEQUENCE — a list of action steps. This is the shape that
        # broke 0.4.3, and it is what the selector is documented to produce:
        # `ActionSelector` in homeassistant/helpers/selector.py is "Selector of
        # an action sequence (script syntax)", and its __call__ is `return data`,
        # so it validates nothing and passes any shape straight through.
        return [{"action": "notify.mobile_app_example", "data": {"message": "hi"}}]

    raise AssertionError(
        f"input {name!r} uses selector {kind!r}, which this gate does not know how "
        f"to fill in. Add it to _ui_value_for with the shape the UI produces — do "
        f"NOT let it be skipped, because an unrecognised selector is exactly how "
        f"the 0.4.3 defect reached a household."
    )


@pytest.fixture(name="notify_device_id")
async def notify_device_fixture(hass: HomeAssistant) -> str:
    """A mobile_app device, because the blueprint now targets one.

    Registered against a real `mobile_app` config entry rather than faked: the
    device action is validated by mobile_app itself, and validation that never
    reaches the integration proves nothing about whether the action is right.
    """
    from homeassistant.helpers import device_registry as dr
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain="mobile_app", data={})
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("mobile_app", "test-phone")},
        name="Test Phone",
    )
    return device.id


@pytest.fixture(name="blueprint")
def blueprint_fixture() -> Blueprint:
    return Blueprint(
        yaml_loader.parse_yaml(BLUEPRINT.read_text(encoding="utf-8")),
        expected_domain="automation",
        schema=BLUEPRINT_SCHEMA,
    )


async def test_the_blueprint_can_be_saved_with_what_the_ui_produces(
    hass: HomeAssistant, blueprint: Blueprint, notify_device_id: str
) -> None:
    """Configure it the way a person does, and let Home Assistant judge.

    `async_validate_config_item` is the same validation the UI runs on save, and
    it raises rather than warning, so a failure here is the message the user
    would have seen — not an approximation of it.
    """
    substitutions = {
        name: _ui_value_for(name, definition, notify_device_id)
        for name, definition in blueprint.inputs.items()
    }
    config = BlueprintInputs(
        blueprint, {"use_blueprint": {"path": "x.yaml", "input": substitutions}}
    ).async_substitute()

    try:
        await async_validate_config_item(hass, "automation", config)
    except vol.Invalid as err:
        pytest.fail(
            "a person filling this in from the Home Assistant UI cannot save it.\n"
            f"Home Assistant says: {err}\n"
            "This is the gate that did not exist for 0.4.3."
        )


async def test_every_input_is_one_this_gate_understands(blueprint: Blueprint) -> None:
    """Fail on an unknown selector rather than quietly covering less.

    Separated from the test above so that adding an input with a novel selector
    produces "this gate does not cover your new input" rather than a confusing
    failure inside automation validation.
    """
    for name, definition in blueprint.inputs.items():
        _ui_value_for(name, definition, "0123456789abcdef")


async def test_no_input_is_used_where_a_service_name_is_required(
    blueprint: Blueprint,
) -> None:
    """The specific mistake, named, so it cannot come back by a different route.

    `action:` in script syntax takes a service name — a string. No selector in
    Home Assistant produces one: the full registered list is entity, device,
    duration, number, boolean, time, text, action, target, template and the rest,
    and none is service-shaped. So an `!input` sitting directly under `action:`
    is always wrong, whichever selector is declared for it, and the only reason
    to write one is believing a selector exists that does not.
    """
    raw = yaml_loader.parse_yaml(BLUEPRINT.read_text(encoding="utf-8"))
    offenders: list[str] = []

    def walk(node: Any, path: str = "$") -> None:
        from homeassistant.util.yaml.objects import Input

        if isinstance(node, dict):
            if isinstance(node.get("action"), Input):
                offenders.append(f"{path}.action -> !input {node['action'].name}")
            for key, value in node.items():
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(raw)
    assert not offenders, (
        "an `!input` is being used directly as a service name:\n  "
        + "\n  ".join(offenders)
        + "\nNo Home Assistant selector yields a service-name string. Use the "
        "mobile_app device action, or build the name in a variable."
    )
