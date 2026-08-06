"""Data coordinator for Calendora."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    CalendoraError,
    CalendoraFeedClient,
    CalendoraInvalidFeedError,
    CalendoraResponseError,
)
from .const import (
    CONF_FEED_URL,
    CONF_SCAN_INTERVAL_MINUTES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOGGER,
)

if TYPE_CHECKING:
    from . import CalendoraConfigEntry


@dataclass(slots=True)
class CalendoraData:
    """Everything one refresh produced.

    Phase 0 carries only the raw document. Phase 1 adds the parsed calendars —
    the seam is here so that the parsing work lands in the calendar platform and
    this class grows a field, rather than the coordinator growing a parser.
    """

    raw_ics: str


class CalendoraDataUpdateCoordinator(DataUpdateCoordinator[CalendoraData]):
    """Keeps the household's calendar data fresh.

    `AGENTS.md` mandates a push coordinator "where possible" — and from Phase 2
    this becomes one, driven by `GET /api/v1/stream`. Phase 1 polls because the
    feed is a static ICS document with nothing to push with: the fallback path is
    the only path that exists yet.
    """

    config_entry: CalendoraConfigEntry

    def __init__(
        self, hass: HomeAssistant, config_entry: CalendoraConfigEntry
    ) -> None:
        """Initialise the coordinator."""
        interval = DEFAULT_SCAN_INTERVAL
        if minutes := config_entry.options.get(CONF_SCAN_INTERVAL_MINUTES):
            interval = timedelta(minutes=minutes)

        super().__init__(
            hass,
            LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=interval,
        )

        self.client = CalendoraFeedClient(
            async_get_clientsession(hass),
            config_entry.data[CONF_FEED_URL],
        )

    async def _async_update_data(self) -> CalendoraData:
        """Fetch the feed once.

        The three failures are kept apart on purpose. "Unavailable" with no
        explanation is a support thread; "your feed URL was rejected — you
        probably regenerated it, use Reconfigure" is a thirty-second fix. The
        distinction costs three lines here and is worth far more than that in the
        one case that actually happens.
        """
        # Each of these passes the message twice: once as plain text and once as
        # a translation key. They are not redundant — `entry.reason`, which is
        # what a user actually reads under a failed entry and what they paste
        # into an issue, carries the positional message, while the translated one
        # is what a localised frontend renders. Supplying only the key leaves the
        # reason showing whatever the underlying client error happened to say.
        try:
            raw_ics = await self.client.async_fetch_ics()
        except CalendoraInvalidFeedError as err:
            # A rejected token is not transient and retrying cannot fix it. The
            # feed has no credential to re-authenticate against, so the repair is
            # the reconfigure step, not a reauth flow — reauth arrives with API
            # keys in Phase 2.
            raise UpdateFailed(
                "Calendora rejected the calendar feed URL. This usually means the"
                " feed was regenerated — open the Calendora integration, choose"
                " Reconfigure, and paste the new address.",
                translation_domain=DOMAIN,
                translation_key="invalid_feed",
            ) from err
        except CalendoraResponseError as err:
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

        return CalendoraData(raw_ics=raw_ics)
