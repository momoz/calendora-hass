"""The Calendora client.

**This is the only file in the integration that makes HTTP calls.** One file that
knows the wire format means the Phase 2 swap from the ICS feed to `/api/v1`
touches one file — and it is also the file that would show it if this integration
were ever tempted to route around a missing endpoint.

The interface this speaks is `docs/API-SURFACE.md` and nothing else. If something
is not written there it is not part of the contract: raise it with the maintainer
rather than reaching for the sync protocol, a session cookie, or an HTML
surface.

Phase 1 surface (`docs/API-SURFACE.md` §2):

    GET /api/feeds/{token}
    GET /api/feeds/{token}?member={memberId}

Returns iCalendar. No auth — the token *is* the authorisation.
"""

from __future__ import annotations

from http import HTTPStatus
from urllib.parse import urlparse

import aiohttp
from yarl import URL

# The feed is a plain document fetch, but a household with a decade of history
# is not small and a stalled TCP connection must not hold a coordinator refresh
# open forever.
FEED_TIMEOUT = aiohttp.ClientTimeout(total=30)

# Enough of the ICS content types to recognise a real feed. A reverse proxy or a
# CDN may append a charset, so this is a prefix test, not equality.
_ICS_CONTENT_TYPES = ("text/calendar", "application/ics")


class CalendoraError(Exception):
    """Base class for every failure this client raises."""


class CalendoraConnectionError(CalendoraError):
    """The server could not be reached, or did not answer in time."""


class CalendoraInvalidFeedError(CalendoraError):
    """The URL is not a Calendora feed, or its token has been revoked.

    `docs/API-SURFACE.md` §1: 404 is also returned for "not yours", so a 404 here
    cannot be read as "this token never existed" — only as "this token does not
    work". Both mean the same thing to a user: regenerate it and reconfigure.
    """


class CalendoraResponseError(CalendoraError):
    """The server answered, but not with something usable."""


def feed_identity(feed_url: str) -> str:
    """Return a stable, non-secret identifier for a feed URL.

    Used as the config entry's ``unique_id`` so a household cannot be added
    twice. The token itself must never be the unique id: unique ids surface in
    places entry data does not, and this one is a credential.

    A SHA-256 of the token is stable for the life of the token and reveals
    nothing. It does change when the user regenerates their feed — accepted for
    Phase 1, because Phase 2 replaces this with the real household id from
    ``GET /api/v1/household``, which is what `AGENTS.md` actually asks for.
    """
    # Imported here rather than at module scope so the dependency is visible at
    # the one place it is used.
    from hashlib import sha256

    token = URL(feed_url).path.rstrip("/").rpartition("/")[2]
    return sha256(token.encode()).hexdigest()


def feed_host(feed_url: str) -> str:
    """Return the host of a feed URL, for use in a user-visible entry title.

    The host is not a secret; the path is. Titles are shown in the UI and quoted
    into bug reports, so only ever build them from this.
    """
    return urlparse(feed_url).hostname or "Calendora"


class CalendoraFeedClient:
    """Reads the Phase 1 ICS feed.

    Deliberately thin: it fetches and validates the transport, and returns the
    ICS document as text. Parsing and recurrence expansion belong to the calendar
    platform, not to the wire.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        feed_url: str,
        *,
        member_id: str | None = None,
    ) -> None:
        """Initialise the client.

        The session is Home Assistant's shared one — never create your own.
        """
        self._session = session
        self._feed_url = feed_url
        self._member_id = member_id

    async def async_fetch_ics(self) -> str:
        """Fetch the feed and return the raw iCalendar document.

        Raises a `CalendoraError` subclass on any failure. Nothing here ever
        includes the feed URL in an exception message: the token is in that URL,
        and exception messages reach the log.
        """
        url = URL(self._feed_url)
        if self._member_id is not None:
            url = url.update_query({"member": self._member_id})

        try:
            response = await self._session.get(url, timeout=FEED_TIMEOUT)
        except aiohttp.ClientError as err:
            raise CalendoraConnectionError("Could not reach the Calendora feed") from err
        except TimeoutError as err:
            raise CalendoraConnectionError("The Calendora feed timed out") from err

        async with response:
            if response.status in (HTTPStatus.NOT_FOUND, HTTPStatus.GONE):
                raise CalendoraInvalidFeedError(
                    "The feed URL was rejected — it may have been regenerated"
                )
            if response.status != HTTPStatus.OK:
                raise CalendoraResponseError(
                    f"The Calendora feed answered HTTP {response.status}"
                )

            content_type = response.headers.get(aiohttp.hdrs.CONTENT_TYPE, "")
            if not content_type.startswith(_ICS_CONTENT_TYPES):
                # Almost always a login page from a reverse proxy, or the user
                # pasting the web URL instead of the feed URL. Treating it as an
                # invalid feed rather than a transport error puts the repair
                # instruction in front of the person who can act on it.
                raise CalendoraInvalidFeedError(
                    "That URL did not return a calendar feed"
                )

            try:
                body = await response.text()
            except aiohttp.ClientError as err:
                raise CalendoraConnectionError(
                    "The Calendora feed disconnected mid-download"
                ) from err

        if "BEGIN:VCALENDAR" not in body:
            raise CalendoraInvalidFeedError("That URL did not return a calendar feed")

        return body
