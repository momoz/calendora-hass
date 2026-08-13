"""The shopping trip's push budget.

§6 stops a trip at eight pushes. The whole reason this lives in the integration
rather than the blueprint is **persistence**: a blueprint has nowhere to keep a
number between runs, and Mike's ruling was that Home Assistant should store it
itself rather than Calendora holding a counter it has no other reason to know
about.

So the test that carries the weight is `test_the_count_survives_a_restart`. A
counter that resets on restart is **a cap that silently does not cap** — it reads
as enforced while letting a trip push a family indefinitely, and Home Assistant
restarts on updates, config reloads and power cuts. Every other test here is
arithmetic; that one is the requirement.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.calendora.const import DOMAIN
from custom_components.calendora.push_budget import (
    SERVICE_SHOP_PUSH_BUDGET,
    ShopPushBudget,
    async_register_push_budget,
)

TRIP = "calendora_shop_mike"


async def _spend(hass: HomeAssistant, **data) -> dict:
    return await hass.services.async_call(
        DOMAIN,
        SERVICE_SHOP_PUSH_BUDGET,
        {"trip": TRIP, **data},
        blocking=True,
        return_response=True,
    )


@pytest.fixture(autouse=True)
async def _registered(hass: HomeAssistant) -> None:
    await async_register_push_budget(hass)


async def test_a_trip_may_send_up_to_its_limit(hass: HomeAssistant) -> None:
    """Eight allowed, the ninth refused — §6's hard stop."""
    first = await _spend(hass, reset=True)
    assert first == {"allowed": True, "count": 1, "max": 8}

    for expected in range(2, 9):
        result = await _spend(hass)
        assert result["allowed"] is True, f"push {expected} was refused"
        assert result["count"] == expected

    ninth = await _spend(hass)
    assert ninth["allowed"] is False, "the ninth push was allowed — §6 caps at eight"
    assert ninth["count"] == 9


async def test_the_count_survives_a_restart(hass: HomeAssistant) -> None:
    """**The requirement.** This is why the counter is not a script variable.

    A restart-scoped counter reads as a limit and is not one: Home Assistant
    restarts on every update, every config reload and every power cut, and a
    trip that survives one would start again from zero. That is the
    silent-success shape inside a control whose only job is to be a limit.

    Simulated by building a second `ShopPushBudget` against the same store,
    which is what a restart produces — a fresh object over the same file.
    """
    for _ in range(5):
        await _spend(hass, reset=False)

    after_restart = ShopPushBudget(hass)
    result = await after_restart.async_spend(TRIP, maximum=8, reset=False)

    assert result["count"] == 6, (
        "the count restarted at zero — this cap does not survive a restart, "
        "which is the one property it exists to have"
    )


async def test_a_new_trip_starts_from_zero(hass: HomeAssistant) -> None:
    """Without this the eighth push *ever sent* would be the household's last.

    The arrival card is the thing that resets, which is what makes the budget
    per-trip rather than per-lifetime.
    """
    for _ in range(8):
        await _spend(hass)
    assert (await _spend(hass))["allowed"] is False

    fresh = await _spend(hass, reset=True)
    assert fresh == {"allowed": True, "count": 1, "max": 8}


async def test_two_people_shopping_have_separate_budgets(hass: HomeAssistant) -> None:
    """§6's "two people, one list": both loops run independently.

    The trip key is the notification tag, which is one per person per trip, so
    Donna exhausting her budget must not silence Mike's card mid-aisle.
    """
    for _ in range(9):
        await _spend(hass, reset=False)
    assert (await _spend(hass))["allowed"] is False

    donna = await hass.services.async_call(
        DOMAIN,
        SERVICE_SHOP_PUSH_BUDGET,
        {"trip": "calendora_shop_donna", "reset": True},
        blocking=True,
        return_response=True,
    )
    assert donna["allowed"] is True and donna["count"] == 1


async def test_the_limit_is_honoured_and_bounded(hass: HomeAssistant) -> None:
    """§0 declares 3–20. Enforced here as well as in the blueprint's selector.

    A service is callable by anything — an automation, a script, a REST call —
    so a range that only the UI enforces is not a range.
    """
    result = await _spend(hass, reset=True, max=3)
    assert result["max"] == 3
    for _ in range(2):
        await _spend(hass, max=3)
    assert (await _spend(hass, max=3))["allowed"] is False

    for bad in (2, 21):
        with pytest.raises((ServiceValidationError, Exception)):
            await _spend(hass, max=bad)
