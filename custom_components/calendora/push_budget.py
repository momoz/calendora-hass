"""The shopping trip's push budget.

`DESIGN-shop-arrival.md` §6: *"The trip stops at whichever comes first: list
cleared · GOT_ALL · STOP · 90 minutes since arrival · **8 pushes**."* §0 declares
a `max_pushes` input, 3–20, default 8. **Neither was ever built.**

**Why this lives in the integration rather than the blueprint.** A blueprint has
nowhere to keep a number between runs — each trigger is a fresh script with fresh
variables, and the only persistence available to it is a helper entity the
household would have to create by hand. Mike's ruling (2026-08-10): *"I think HA
should store itself."* Home Assistant's own `Store` survives updates, config
reloads and power cuts, **which is the entire property the decision turned on** —
a counter that resets on restart is a cap that silently does not cap, and Home
Assistant restarts often.

**Why not Calendora's database**, which was the first answer: the pushes
originate in Home Assistant, go to a phone, and never touch Calendora, which has
no other reason to know how many notifications a blueprint sent during a shop.
That route meant a new public `/api/v1` surface, maintained forever, for a
counter.

**What this deliberately is not.** It does not decide whether to send, it counts
and reports. The blueprint owns the sending, because §6's other stop conditions
live there and splitting them across two files would leave nobody able to read
the rule in one place.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store

from .const import DOMAIN, LOGGER

SERVICE_SHOP_PUSH_BUDGET = "shop_push_budget"

STORAGE_KEY = f"{DOMAIN}.shop_budget"
STORAGE_VERSION = 1

ATTR_TRIP = "trip"
ATTR_MAX = "max"
ATTR_RESET = "reset"

#: §0 declares 3–20, default 8. Enforced here as well as in the blueprint's
#: selector, because a service is callable by anything and a limit that only the
#: UI enforces is not a limit.
MIN_PUSHES = 3
MAX_PUSHES = 20
DEFAULT_MAX_PUSHES = 8

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_TRIP): cv.string,
        vol.Optional(ATTR_MAX, default=DEFAULT_MAX_PUSHES): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_PUSHES, max=MAX_PUSHES)
        ),
        vol.Optional(ATTR_RESET, default=False): cv.boolean,
    }
)


class ShopPushBudget:
    """Counts pushes per trip, across restarts."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._trips: dict[str, int] | None = None

    async def _async_trips(self) -> dict[str, int]:
        if self._trips is None:
            stored = await self._store.async_load()
            self._trips = dict(stored or {})
        return self._trips

    async def async_spend(self, trip: str, maximum: int, reset: bool) -> dict[str, Any]:
        """Record one push against a trip and say whether it was within budget.

        `reset` starts a fresh trip — the arrival card calls it that way, which
        is what makes the count per-trip rather than per-lifetime. Without it the
        eighth push ever sent would be the last one this household received.
        """
        trips = await self._async_trips()

        if reset:
            trips[trip] = 0

        count = trips.get(trip, 0) + 1
        trips[trip] = count
        await self._store.async_save(trips)

        allowed = count <= maximum
        if not allowed:
            # §6: "The eighth is a hard stop with no explanatory ninth. If a trip
            # has taken eight, the design has already failed and a message about
            # it is not the repair." So this is logged for whoever goes looking,
            # and nothing is sent to the phone.
            LOGGER.info(
                "Shopping trip %s has spent its push budget (%s of %s); staying quiet",
                trip,
                count,
                maximum,
            )
        return {"allowed": allowed, "count": count, "max": maximum}


async def async_register_push_budget(hass: HomeAssistant) -> None:
    """Register the counting service, once per Home Assistant."""
    if hass.services.has_service(DOMAIN, SERVICE_SHOP_PUSH_BUDGET):
        return

    budget = ShopPushBudget(hass)

    async def _handle(call: ServiceCall) -> ServiceResponse:
        return await budget.async_spend(
            call.data[ATTR_TRIP], call.data[ATTR_MAX], call.data[ATTR_RESET]
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SHOP_PUSH_BUDGET,
        _handle,
        schema=SERVICE_SCHEMA,
        # ONLY, not OPTIONAL: a caller that does not read the answer has not
        # asked whether it may send — it has just incremented a counter.
        supports_response=SupportsResponse.ONLY,
    )
