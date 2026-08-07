"""Data coordinator for Calendora.

Push, not poll. `GET /api/v1/stream` says *that* something changed and never
what, so the shape is: hold the stream open, and on every `changed` re-read what
we care about. The 30-minute poll underneath is a safety net for a stream that
died without saying so — not a data path. A push integration that also polls
every minute is a polling integration wearing a costume.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    CalendoraAuthError,
    CalendoraClient,
    CalendoraError,
    CalendoraForbiddenError,
    CalendoraServerError,
)
from .const import (
    CONF_API_KEY,
    DOMAIN,
    EVENT_WINDOW_FUTURE,
    EVENT_WINDOW_PAST,
    FALLBACK_POLL_INTERVAL,
    LOGGER,
)

if TYPE_CHECKING:
    from . import CalendoraConfigEntry

# Reconnect backoff for the stream. Starts quickly because the common case is a
# blip, and gives up climbing at five minutes because a server that has been
# down for five minutes is not helped by being asked every second.
STREAM_RETRY_INITIAL = timedelta(seconds=5)
STREAM_RETRY_MAX = timedelta(minutes=5)

# Long enough to collapse the burst of identical requests one dashboard render
# produces across several calendar entities; short enough to never be the reason
# somebody sees an old event.
WINDOW_CACHE_SECONDS = 15
WINDOW_CACHE_MAX = 32


@dataclass(slots=True)
class CalendoraData:
    """Everything one refresh produced.

    Fields come from `docs/API-SURFACE.md` §4a and nowhere else. Anything not
    named there is not read, however obvious it looks in a response.
    """

    household_id: str
    household_name: str
    # §4a: `name` is already resolved server-side — a display-name override beats
    # the stored name. Never re-derive it from /people.
    members: list[dict[str, Any]]
    # {list: {…}, items: [...], sections: [...]} keyed by list id.
    lists: dict[str, dict[str, Any]]
    # The key owner's zone, not the household's — §4 is explicit that there is
    # no household timezone, only a per-person preference reported as whose it
    # is. It is used to turn a requested window into the days the API wants.
    key_owner_timezone: str
    occurrences: list[dict[str, Any]]


class CalendoraDataUpdateCoordinator(DataUpdateCoordinator[CalendoraData]):
    """Keeps the household's data fresh, driven by the stream."""

    config_entry: CalendoraConfigEntry

    def __init__(
        self, hass: HomeAssistant, config_entry: CalendoraConfigEntry
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=FALLBACK_POLL_INTERVAL,
        )
        self._window_cache: dict[tuple[date, date], tuple[float, list[dict[str, Any]]]] = {}
        self._window_lock = asyncio.Lock()
        self._api_key: str = config_entry.data.get(CONF_API_KEY, "")
        self.client = CalendoraClient(async_get_clientsession(hass), self._api_key)

    def _window(self) -> tuple[date, date]:
        """Return the day range to load.

        Days, not instants: §4 rejects an instant outright, because the same
        instant is a different day depending on the zone it was written in.
        """
        today = dt_util.now().date()
        return today - EVENT_WINDOW_PAST, today + EVENT_WINDOW_FUTURE

    async def _async_update_data(self) -> CalendoraData:
        """Re-read the household and its events."""
        if not self._api_key:
            # A 0.0.1 entry that was migrated off the calendar feed. There is no
            # key to try, so go straight to asking for one.
            raise ConfigEntryAuthFailed(
                "Calendora now needs an API key. Add one to continue.",
                translation_domain=DOMAIN,
                translation_key="invalid_auth",
            )

        date_from, date_to = self._window()
        try:
            household, members, events, lists = await asyncio.gather(
                self.client.async_get_household(),
                self.client.async_get_members(),
                self.client.async_get_events(date_from, date_to),
                self.client.async_get_lists(),
            )
            # One request per list, in parallel. Sequential would make a
            # household with six lists six round trips deep on every refresh,
            # and the stream refreshes on every change anybody makes.
            list_rows = [
                row
                for row in (lists.get("lists") or [])
                if not row.get("isArchived")
            ]
            item_payloads = await asyncio.gather(
                *(self.client.async_get_list_items(row["id"]) for row in list_rows)
            )
        except CalendoraAuthError as err:
            # §3: never retry a 401, never fail silently. This hands the user a
            # reauth flow instead of an entity that is quietly always stale.
            raise ConfigEntryAuthFailed(
                "Calendora rejected the API key. It may have been revoked or"
                " expired — add a new one to continue.",
                translation_domain=DOMAIN,
                translation_key="invalid_auth",
            ) from err
        except CalendoraForbiddenError as err:
            # A valid key missing a scope. Reauth would return the same key and
            # loop, so this fails the refresh with the scope named instead.
            raise UpdateFailed(
                f"The Calendora API key is missing a permission: {err}",
                translation_domain=DOMAIN,
                translation_key="missing_scope",
                translation_placeholders={"detail": str(err)},
            ) from err
        except CalendoraServerError as err:
            raise UpdateFailed(
                "Calendora answered with an error. Home Assistant will keep trying.",
                translation_domain=DOMAIN,
                translation_key="server_error",
            ) from err
        except CalendoraError as err:
            raise UpdateFailed(
                "Could not reach Calendora. Home Assistant will keep trying.",
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
            ) from err

        if (
            not isinstance(household, dict)
            or not isinstance(members, dict)
            or not isinstance(events, dict)
            or not isinstance(lists, dict)
        ):
            # §4a fixes both shapes as objects. Anything else means the server
            # changed under us, and a clear failure beats an AttributeError
            # surfacing from a dict access three lines later.
            raise UpdateFailed(
                "Calendora returned data in an unexpected shape. This is a bug —"
                " please report it.",
                translation_domain=DOMAIN,
                translation_key="unexpected_response",
            )

        household_data = household.get("household") or {}
        return CalendoraData(
            household_id=household_data.get("id", ""),
            household_name=household_data.get("name") or "Calendora",
            members=members.get("members") or [],
            lists={
                row["id"]: {
                    "list": row,
                    "items": payload.get("items") or [],
                    "sections": payload.get("sections") or [],
                }
                for row, payload in zip(list_rows, item_payloads, strict=True)
            },
            key_owner_timezone=household.get("timezone", {}).get("value") or "UTC",
            occurrences=events.get("occurrences") or [],
        )

    async def async_fetch_window(
        self, date_from: date, date_to: date
    ) -> list[dict[str, Any]]:
        """Fetch occurrences for an arbitrary window, shared between entities.

        Home Assistant asks every calendar entity for the same window at the same
        moment when a dashboard renders, so without this a household of five
        makes five identical requests for one month view. Entries are held very
        briefly — long enough to collapse one render, short enough that nobody is
        looking at stale data.
        """
        key = (date_from, date_to)
        async with self._window_lock:
            cached = self._window_cache.get(key)
            now = self.hass.loop.time()
            if cached is not None and now - cached[0] < WINDOW_CACHE_SECONDS:
                return cached[1]

            occurrences = (
                await self.client.async_get_events(date_from, date_to)
            ).get("occurrences") or []

            # Bounded so that a user scrubbing through a year of months cannot
            # grow this without limit.
            if len(self._window_cache) >= WINDOW_CACHE_MAX:
                self._window_cache.clear()
            self._window_cache[key] = (now, occurrences)
            return occurrences

    async def async_run_stream(self) -> None:
        """Hold the stream open and refresh on every `changed`.

        Runs for the life of the config entry as a background task. It never
        exits on a transport failure — that is what a reconnect loop is for —
        but it does exit on an auth failure, because retrying a 401 is
        prohibited and the only way out is the user supplying a new key.
        """
        delay = STREAM_RETRY_INITIAL

        while True:
            try:
                async for event_name in self.client.async_stream():
                    # A successful read means the connection is healthy, so the
                    # backoff resets here rather than after connecting — a server
                    # that accepts the connection and then drops it would
                    # otherwise reconnect in a tight loop forever.
                    delay = STREAM_RETRY_INITIAL

                    if event_name == "changed":
                        async with self._window_lock:
                            self._window_cache.clear()
                        # The payload is always `{}`; it says something changed,
                        # never what. Re-read rather than trying to be clever.
                        await self.async_request_refresh()

            except CalendoraAuthError:
                LOGGER.debug("Calendora stream rejected the API key; starting reauth")
                self.config_entry.async_start_reauth(self.hass)
                return

            except CalendoraError as err:
                LOGGER.debug("Calendora stream dropped (%s); reconnecting", type(err).__name__)

            except asyncio.CancelledError:
                # Unload, or Home Assistant shutting down. Not an error, and it
                # must not be swallowed or the task cannot be cancelled.
                raise

            else:
                LOGGER.debug("Calendora stream closed cleanly; reconnecting")

            await asyncio.sleep(delay.total_seconds())
            delay = min(delay * 2, STREAM_RETRY_MAX)
