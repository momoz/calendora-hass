"""Tests for the Calendora `/api/v1` client.

Two things carry most of the weight here.

`test_no_failure_ever_leaks_the_key` is the important one. The API key is a
secret (`docs/API-SURFACE.md` §9), so a key that reaches an exception message
reaches the log, and a log is the first thing a user pastes into a public issue.
Nobody notices that bug until after it has happened, so it is guarded
mechanically across every failure path rather than by remembering.

The rest pin the error *meanings* the contract fixes — particularly that 401 and
403 are different problems with different remedies, and that 404 never means
"invalid id".
"""

from __future__ import annotations

from datetime import date

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.calendora.api import (
    CalendoraAuthError,
    CalendoraBadRequestError,
    CalendoraClient,
    CalendoraConnectionError,
    CalendoraError,
    CalendoraForbiddenError,
    CalendoraNotFoundError,
    CalendoraResponseError,
    CalendoraServerError,
)
from custom_components.calendora.const import API_BASE_URL

from .const import API_KEY

HOUSEHOLD_URL = f"{API_BASE_URL}/api/v1/household"
EVENTS_URL = f"{API_BASE_URL}/api/v1/events"
STREAM_URL = f"{API_BASE_URL}/api/v1/stream"


def _client(hass: HomeAssistant) -> CalendoraClient:
    return CalendoraClient(async_get_clientsession(hass), API_KEY)


async def test_sends_the_bearer_token(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The documented auth header, and nothing else clever."""
    aioclient_mock.get(HOUSEHOLD_URL, json={"timezone": {"value": "Europe/Amsterdam"}})

    await _client(hass).async_get_household()

    headers = aioclient_mock.mock_calls[0][3]
    assert headers["Authorization"] == f"Bearer {API_KEY}"


async def test_returns_decoded_json_untouched(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The client does not interpret bodies, so callers can name fields later."""
    payload = {"anything": ["at", "all"], "nested": {"n": 1}}
    aioclient_mock.get(HOUSEHOLD_URL, json=payload)

    assert await _client(hass).async_get_household() == payload


@pytest.mark.parametrize(
    ("status", "code", "expected"),
    [
        (401, "unauthenticated", CalendoraAuthError),
        (403, "forbidden", CalendoraForbiddenError),
        (404, "not_found", CalendoraNotFoundError),
        (400, "bad_request", CalendoraBadRequestError),
        (500, "server_error", CalendoraServerError),
    ],
)
async def test_documented_errors_map_to_their_meanings(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    status: int,
    code: str,
    expected: type[CalendoraError],
) -> None:
    """Each documented failure becomes the exception that implies its remedy."""
    aioclient_mock.get(
        HOUSEHOLD_URL, status=status, json={"error": "a sentence", "code": code}
    )

    with pytest.raises(expected):
        await _client(hass).async_get_household()


async def test_auth_and_scope_failures_are_not_the_same_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """401 and 403 must never collapse into one branch.

    401 means reauth — get a new key. 403 means the key is *fine* and is missing
    a scope, so reauth would hand back the same key and loop forever. Conflating
    them is the difference between a fix and an infinite prompt.
    """
    assert not issubclass(CalendoraForbiddenError, CalendoraAuthError)
    assert not issubclass(CalendoraAuthError, CalendoraForbiddenError)

    aioclient_mock.get(
        HOUSEHOLD_URL,
        status=403,
        json={"error": "missing scope: calendar:read", "code": "forbidden"},
    )
    with pytest.raises(CalendoraForbiddenError) as err:
        await _client(hass).async_get_household()

    # The message names the scope, which is the actionable part — keep it.
    assert "calendar:read" in str(err.value)


async def test_unknown_error_code_still_behaves_by_status(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A `code` we have never seen must not change what 401 means.

    The contract fixes the status; the code is a label. Keying on the label
    would make a future code string silently downgrade an auth failure.
    """
    aioclient_mock.get(
        HOUSEHOLD_URL, status=401, json={"error": "nope", "code": "brand_new_code"}
    )

    with pytest.raises(CalendoraAuthError):
        await _client(hass).async_get_household()


async def test_html_error_page_does_not_break_error_handling(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A proxy's HTML 502 is still a server error, not a parse crash."""
    aioclient_mock.get(
        HOUSEHOLD_URL,
        status=502,
        text="<html>Bad Gateway</html>",
        headers={"Content-Type": "text/html"},
    )

    with pytest.raises(CalendoraServerError):
        await _client(hass).async_get_household()


async def test_non_json_success_is_a_response_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 200 carrying a login page is not success."""
    aioclient_mock.get(
        HOUSEHOLD_URL, text="<html>Sign in</html>", headers={"Content-Type": "text/html"}
    )

    with pytest.raises(CalendoraResponseError):
        await _client(hass).async_get_household()


@pytest.mark.parametrize(
    "exc", [aiohttp.ClientConnectionError("boom"), TimeoutError()]
)
async def test_transport_failures_are_connection_errors(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, exc: Exception
) -> None:
    """Unreachable and too-slow tell a user the same story."""
    aioclient_mock.get(HOUSEHOLD_URL, exc=exc)

    with pytest.raises(CalendoraConnectionError):
        await _client(hass).async_get_household()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": 401, "json": {"error": "no", "code": "unauthenticated"}},
        {"status": 403, "json": {"error": "no", "code": "forbidden"}},
        {"status": 404, "json": {"error": "no", "code": "not_found"}},
        {"status": 400, "json": {"error": "no", "code": "bad_request"}},
        {"status": 500, "json": {"error": "no", "code": "server_error"}},
        {"status": 502, "text": "<html/>", "headers": {"Content-Type": "text/html"}},
        {"text": "<html/>", "headers": {"Content-Type": "text/html"}},
        {"exc": aiohttp.ClientConnectionError("boom")},
        {"exc": TimeoutError()},
    ],
    ids=["401", "403", "404", "400", "500", "502-html", "200-html", "refused", "timeout"],
)
async def test_no_failure_ever_leaks_the_key(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
    kwargs: dict,
) -> None:
    """No failure path may put the API key in a message, a repr, or a log.

    Parametrised over every way a request can fail rather than spot-checked: the
    guard is only worth something if adding a tenth failure mode without
    thinking about it breaks the build.
    """
    aioclient_mock.get(HOUSEHOLD_URL, **kwargs)

    with pytest.raises(CalendoraError) as err_info:
        await _client(hass).async_get_household()

    err = err_info.value
    assert API_KEY not in str(err)
    assert API_KEY not in repr(err)
    assert API_KEY not in caplog.text
    # The chained transport exception rides along in the traceback, so it has to
    # be clean too.
    assert API_KEY not in repr(err.__cause__)


async def test_key_is_not_in_the_client_repr(hass: HomeAssistant) -> None:
    """A debugger frame or a diagnostics dump must not spill the key."""
    client = _client(hass)

    assert API_KEY not in repr(client)
    assert API_KEY not in str(vars(client).get("_headers", ""))


async def test_events_sends_days_not_instants(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """`from`/`to` are `YYYY-MM-DD`; §4 rejects an instant outright."""
    aioclient_mock.get(EVENTS_URL, json=[])

    await _client(hass).async_get_events(date(2026, 8, 1), date(2026, 9, 1))

    query = aioclient_mock.mock_calls[0][1].query
    assert query["from"] == "2026-08-01"
    assert query["to"] == "2026-09-01"
    assert "T" not in query["from"]


async def test_events_passes_member_filter_only_when_asked(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """§5 rejects unknown fields, so nothing is sent speculatively."""
    aioclient_mock.get(EVENTS_URL, json=[])

    await _client(hass).async_get_events(date(2026, 8, 1), date(2026, 8, 2))
    assert "member" not in aioclient_mock.mock_calls[0][1].query

    await _client(hass).async_get_events(
        date(2026, 8, 1), date(2026, 8, 2), member_id="m-1"
    )
    assert aioclient_mock.mock_calls[1][1].query["member"] == "m-1"


async def test_over_long_range_fails_before_the_request(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """§4 rejects a range over 400 days rather than truncating it.

    Caught client-side so the failure names the real mistake, and so a caller
    cannot mistake a rejection for an empty calendar.
    """
    with pytest.raises(ValueError, match="400"):
        await _client(hass).async_get_events(date(2026, 1, 1), date(2027, 6, 1))

    assert not aioclient_mock.mock_calls


async def test_backwards_range_is_rejected(hass: HomeAssistant) -> None:
    """An inverted window is a bug, not an empty result."""
    with pytest.raises(ValueError):
        await _client(hass).async_get_events(date(2026, 9, 1), date(2026, 8, 1))


async def test_stream_yields_event_names_and_ignores_keep_alives(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """§4 fixes the vocabulary: `ready`, `changed`, and `:` keep-alive comments."""
    aioclient_mock.get(
        STREAM_URL,
        text=(
            "event: ready\ndata: {}\n\n"
            ": keep-alive\n\n"
            "event: changed\ndata: {}\n\n"
            ": keep-alive\n\n"
            "event: changed\ndata: {}\n\n"
        ),
        headers={"Content-Type": "text/event-stream"},
    )

    names = [name async for name in _client(hass).async_stream()]

    assert names == ["ready", "changed", "changed"]


async def test_stream_auth_failure_is_an_auth_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A revoked key kills the stream too, and must reach reauth the same way."""
    aioclient_mock.get(
        STREAM_URL, status=401, json={"error": "no", "code": "unauthenticated"}
    )

    with pytest.raises(CalendoraAuthError):
        async for _ in _client(hass).async_stream():
            pass
