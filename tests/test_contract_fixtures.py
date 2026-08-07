"""Replay the vendored contract fixtures against the real client.

`CONTRACT.md` §10: Calendora generates `fixtures/` from its own route handlers
on every push, this repository vendors the directory, and CI tests the client
against it. **The point is that Calendora cannot change the interface without
breaking this build** — the closest thing to a monorepo that two repositories
can have.

These tests are deliberately generic. They read what each fixture claims and
check the client agrees, rather than restating the fixtures in Python, because a
hand-copied expectation drifts from the file it was copied from.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.calendora.api import (
    CalendoraAuthError,
    CalendoraBadRequestError,
    CalendoraClient,
    CalendoraForbiddenError,
    CalendoraNotFoundError,
    CalendoraServerError,
)
from custom_components.calendora.const import API_BASE_URL

from .const import API_KEY

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

# The exception each documented `code` must become. This is the mapping the rest
# of the integration reasons about: 401 sends the user to reauth, 403 does not
# because their key is fine, and 404 never means "that id is invalid".
CODE_TO_EXCEPTION = {
    "unauthenticated": CalendoraAuthError,
    "forbidden": CalendoraForbiddenError,
    "not_found": CalendoraNotFoundError,
    "bad_request": CalendoraBadRequestError,
    "server_error": CalendoraServerError,
}


def _fixtures() -> list[tuple[str, dict]]:
    return sorted(
        (path.name, json.loads(path.read_text(encoding="utf-8")))
        for path in FIXTURES.glob("*.json")
    )


def _ids(pairs):
    return [name for name, _ in pairs]


ALL = _fixtures()
ERRORS = [(n, f) for n, f in ALL if f["response"]["status"] >= 400]


def test_the_fixture_directory_is_actually_vendored() -> None:
    """A missing directory would make every test below vacuously pass."""
    assert FIXTURES.is_dir()
    assert len(ALL) > 20, f"only {len(ALL)} fixtures — did the vendoring truncate?"


@pytest.mark.parametrize(("name", "fixture"), ALL, ids=_ids(ALL))
def test_every_fixture_has_the_documented_shape(name: str, fixture: dict) -> None:
    """`fixtures/README.md` promises describes / request / response."""
    assert fixture["describes"].strip()
    assert fixture["request"]["method"] in {"GET", "POST", "PATCH", "DELETE"}
    assert fixture["request"]["path"].startswith("/api/v1/")
    assert isinstance(fixture["response"]["status"], int)


@pytest.mark.parametrize(("name", "fixture"), ALL, ids=_ids(ALL))
def test_no_fixture_carries_a_working_credential(name: str, fixture: dict) -> None:
    """The README promises a placeholder, and this repository is public.

    Calendora has its own test for this; so does the consumer, because the cost
    of being wrong is somebody's household key in a public git history.
    """
    blob = json.dumps(fixture)
    assert "cal_<key>" in blob or "authorization" not in json.dumps(
        fixture["request"].get("headers", {})
    ).lower()
    assert API_KEY not in blob
    for token in ("cal_live", "cal_sk", "cal_prod"):
        assert token not in blob


@pytest.mark.parametrize(("name", "fixture"), ERRORS, ids=_ids(ERRORS))
async def test_documented_failures_become_the_right_exception(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    name: str,
    fixture: dict,
) -> None:
    """Every documented failure maps to the exception its remedy implies.

    Driven from the fixture's own `code`, so a new error code added upstream
    fails here rather than silently falling into a generic branch.
    """
    request, response = fixture["request"], fixture["response"]
    code = response["body"].get("code")
    assert code in CODE_TO_EXCEPTION, f"{name}: undocumented code {code!r}"

    url = f"{API_BASE_URL}{request['path'].split('?')[0]}"
    getattr(aioclient_mock, request["method"].lower())(
        url, status=response["status"], json=response["body"]
    )

    client = CalendoraClient(async_get_clientsession(hass), API_KEY)
    with pytest.raises(CODE_TO_EXCEPTION[code]):
        await _replay(client, request)


@pytest.mark.parametrize(("name", "fixture"), ERRORS, ids=_ids(ERRORS))
async def test_no_documented_failure_leaks_the_key(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
    name: str,
    fixture: dict,
) -> None:
    """The leak guard, driven by the contract rather than by imagination.

    Every failure Calendora documents is exercised, so a newly documented one
    is covered the day it is vendored rather than whenever somebody remembers.
    """
    request, response = fixture["request"], fixture["response"]
    url = f"{API_BASE_URL}{request['path'].split('?')[0]}"
    getattr(aioclient_mock, request["method"].lower())(
        url, status=response["status"], json=response["body"]
    )

    client = CalendoraClient(async_get_clientsession(hass), API_KEY)
    with pytest.raises(Exception) as err:
        await _replay(client, request)

    assert API_KEY not in str(err.value)
    assert API_KEY not in repr(err.value)
    assert API_KEY not in caplog.text


async def _replay(client: CalendoraClient, request: dict):
    """Issue the fixture's request through the client's own transport.

    Uses the private sender deliberately: the point is to prove the transport
    and error mapping agree with the contract for *every* documented case,
    including ones no public method reaches yet.
    """
    return await client._async_send(  # noqa: SLF001
        request["method"],
        request["path"],
        json=request.get("body"),
        expect=200 if request["method"] != "POST" else 201,
    )
