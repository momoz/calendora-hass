"""Tests for the Calendora client.

The most important test in this file is `test_no_failure_ever_leaks_the_token`.
The feed URL is a capability URL — possession is authorisation — so a token that
reaches an exception message reaches the log, and a log is the first thing a user
pastes into a public issue. Nobody notices that bug until it has already
happened, so it is guarded mechanically here across *every* failure path rather
than by remembering not to write it.
"""

from __future__ import annotations

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.calendora.api import (
    CalendoraConnectionError,
    CalendoraError,
    CalendoraFeedClient,
    CalendoraInvalidFeedError,
    CalendoraResponseError,
    feed_host,
    feed_identity,
)

from .const import FEED_TOKEN, FEED_URL, ICS, ICS_HEADERS, OTHER_FEED_URL


async def test_fetches_ics(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A well-formed feed comes back as text."""
    aioclient_mock.get(FEED_URL, text=ICS, headers=ICS_HEADERS)

    client = CalendoraFeedClient(async_get_clientsession(hass), FEED_URL)
    assert (await client.async_fetch_ics()).startswith("BEGIN:VCALENDAR")


async def test_accepts_content_type_with_charset(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A proxy or CDN may append a charset; that is still a calendar."""
    aioclient_mock.get(
        FEED_URL, text=ICS, headers={"Content-Type": "text/calendar; charset=utf-8"}
    )

    client = CalendoraFeedClient(async_get_clientsession(hass), FEED_URL)
    assert "BEGIN:VCALENDAR" in await client.async_fetch_ics()


async def test_member_query_is_sent(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """`?member=` narrows the feed to one person (API-SURFACE §2)."""
    aioclient_mock.get(f"{FEED_URL}?member=member-1", text=ICS, headers=ICS_HEADERS)

    client = CalendoraFeedClient(
        async_get_clientsession(hass), FEED_URL, member_id="member-1"
    )
    await client.async_fetch_ics()

    assert aioclient_mock.mock_calls[0][1].query["member"] == "member-1"


@pytest.mark.parametrize("status", [404, 410])
async def test_rejected_token_is_an_invalid_feed(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, status: int
) -> None:
    """404 is also 'not yours' (API-SURFACE §1) — either way, the URL is dead."""
    aioclient_mock.get(FEED_URL, status=status)

    client = CalendoraFeedClient(async_get_clientsession(hass), FEED_URL)
    with pytest.raises(CalendoraInvalidFeedError):
        await client.async_fetch_ics()


async def test_html_body_is_an_invalid_feed(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A login page from a reverse proxy is a user error, not a transport error."""
    aioclient_mock.get(
        FEED_URL, text="<html>Sign in</html>", headers={"Content-Type": "text/html"}
    )

    client = CalendoraFeedClient(async_get_clientsession(hass), FEED_URL)
    with pytest.raises(CalendoraInvalidFeedError):
        await client.async_fetch_ics()


async def test_ics_content_type_with_junk_body_is_an_invalid_feed(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The content type can lie; the body cannot."""
    aioclient_mock.get(FEED_URL, text="not a calendar", headers=ICS_HEADERS)

    client = CalendoraFeedClient(async_get_clientsession(hass), FEED_URL)
    with pytest.raises(CalendoraInvalidFeedError):
        await client.async_fetch_ics()


async def test_server_error_is_a_response_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 500 is Calendora's problem and may well be transient."""
    aioclient_mock.get(FEED_URL, status=500)

    client = CalendoraFeedClient(async_get_clientsession(hass), FEED_URL)
    with pytest.raises(CalendoraResponseError):
        await client.async_fetch_ics()


@pytest.mark.parametrize(
    "exc", [aiohttp.ClientConnectionError("boom"), TimeoutError()]
)
async def test_transport_failures_are_connection_errors(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, exc: Exception
) -> None:
    """Unreachable and too-slow are the same story to a user."""
    aioclient_mock.get(FEED_URL, exc=exc)

    client = CalendoraFeedClient(async_get_clientsession(hass), FEED_URL)
    with pytest.raises(CalendoraConnectionError):
        await client.async_fetch_ics()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": 404},
        {"status": 410},
        {"status": 500},
        {"status": 401},
        {"text": "<html>Sign in</html>", "headers": {"Content-Type": "text/html"}},
        {"text": "not a calendar", "headers": {"Content-Type": "text/calendar"}},
        {"exc": aiohttp.ClientConnectionError("boom")},
        {"exc": TimeoutError()},
    ],
    ids=["404", "410", "500", "401", "html", "junk-body", "disconnected", "timeout"],
)
async def test_no_failure_ever_leaks_the_token(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
    kwargs: dict,
) -> None:
    """No failure path may put the feed token into a message, a repr, or a log.

    Parametrised over every way the fetch can fail rather than spot-checked: the
    guard is only worth anything if adding a ninth failure mode without thinking
    about it breaks the build.
    """
    aioclient_mock.get(FEED_URL, **kwargs)

    client = CalendoraFeedClient(async_get_clientsession(hass), FEED_URL)
    with pytest.raises(CalendoraError) as err_info:
        await client.async_fetch_ics()

    err = err_info.value
    assert FEED_TOKEN not in str(err)
    assert FEED_TOKEN not in repr(err)
    assert FEED_TOKEN not in caplog.text
    # The chained transport exception is reachable from the traceback, so it must
    # be clean too — `raise ... from err` keeps it attached to what gets logged.
    assert FEED_TOKEN not in repr(err.__cause__)


def test_feed_identity_is_a_hash_not_the_token() -> None:
    """The unique id must never be the credential."""
    identity = feed_identity(FEED_URL)

    assert len(identity) == 64
    assert FEED_TOKEN not in identity
    assert identity != feed_identity(OTHER_FEED_URL)


def test_feed_identity_ignores_the_query_string() -> None:
    """`?member=` narrows a view; it does not make a different household."""
    assert feed_identity(FEED_URL) == feed_identity(f"{FEED_URL}?member=member-1")


def test_feed_identity_ignores_a_trailing_slash() -> None:
    """A pasted URL with a stray slash is the same feed."""
    assert feed_identity(FEED_URL) == feed_identity(f"{FEED_URL}/")


def test_feed_host_is_safe_to_show() -> None:
    """Entry titles are quoted into bug reports, so they carry the host only."""
    title = feed_host(FEED_URL)

    assert title == "example.invalid"
    assert FEED_TOKEN not in title
