"""Tests for the Calendora config, reauth and reconfigure flows."""

from __future__ import annotations

import aiohttp
import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.calendora.const import API_BASE_URL, CONF_API_KEY, DOMAIN

from .const import API_KEY

HOUSEHOLD_URL = f"{API_BASE_URL}/api/v1/household"
MEMBERS_URL = f"{API_BASE_URL}/api/v1/members"
EVENTS_URL = f"{API_BASE_URL}/api/v1/events"
LISTS_URL = f"{API_BASE_URL}/api/v1/lists"
STREAM_URL = f"{API_BASE_URL}/api/v1/stream"

NEW_KEY = "cal_test_replacement_key_111111111111111111"


def _entry(key: str = API_KEY) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN, title="Calendora", data={CONF_API_KEY: key}, version=2
    )


def _mock_ok(aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(HOUSEHOLD_URL, json={"timezone": {"value": "UTC"}})
    aioclient_mock.get(MEMBERS_URL, json={"members": []})
    aioclient_mock.get(LISTS_URL, json={"lists": []})
    aioclient_mock.get(EVENTS_URL, json=[])
    aioclient_mock.get(STREAM_URL, text="", headers={"Content-Type": "text/event-stream"})


async def test_user_flow(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Paste a key, get a loaded entry."""
    _mock_ok(aioclient_mock)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    aioclient_mock.get(LISTS_URL, json={"lists": []})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: API_KEY}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_API_KEY: API_KEY}
    assert result["result"].version == 2


async def test_user_flow_strips_whitespace(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A key pasted from a web page often carries a trailing space."""
    _mock_ok(aioclient_mock)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: f"  {API_KEY}\n"}
    )
    await hass.async_block_till_done()

    assert result["data"][CONF_API_KEY] == API_KEY


async def test_same_key_cannot_be_added_twice(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Weaker than a household id, but it stops the obvious duplicate."""
    _mock_ok(aioclient_mock)
    _entry().add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: API_KEY}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"status": 401, "json": {"error": "no", "code": "unauthenticated"}}, "invalid_auth"),
        ({"status": 403, "json": {"error": "missing scope: calendar:read", "code": "forbidden"}}, "missing_scope"),
        ({"exc": aiohttp.ClientConnectionError("boom")}, "cannot_connect"),
        ({"status": 500, "json": {"error": "no", "code": "server_error"}}, "cannot_connect"),
    ],
    ids=["revoked", "wrong-scopes", "unreachable", "server-error"],
)
async def test_user_flow_errors_recover(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, kwargs: dict, expected: str
) -> None:
    """Each failure shows its own error, and the form still works afterwards."""
    aioclient_mock.get(HOUSEHOLD_URL, **kwargs)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: API_KEY}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}

    aioclient_mock.clear_requests()
    _mock_ok(aioclient_mock)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: API_KEY}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_wrong_scope_is_not_treated_as_bad_auth(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """403 must not send the user to reauth.

    Reauth asks for a key. The key they have is valid — it is the *scopes* that
    are wrong, so reauth would accept the same key and fail again forever.
    """
    aioclient_mock.get(
        HOUSEHOLD_URL,
        status=403,
        json={"error": "missing scope: household:read", "code": "forbidden"},
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: API_KEY}
    )

    assert result["errors"] == {"base": "missing_scope"}


async def test_flow_never_logs_the_key(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The catch-all branch logs a traceback; it must not carry the secret."""
    aioclient_mock.get(HOUSEHOLD_URL, exc=ValueError("something odd"))

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: API_KEY}
    )

    assert result["errors"] == {"base": "unknown"}
    assert API_KEY not in caplog.text


async def test_reauth_replaces_the_key_in_place(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A revoked key is replaced without losing the entry or its entities."""
    _mock_ok(aioclient_mock)
    entry = _entry()
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: NEW_KEY}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_API_KEY] == NEW_KEY
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_reauth_keeps_the_old_key_if_the_new_one_fails(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A typo during reauth must not destroy a recoverable entry."""
    aioclient_mock.get(HOUSEHOLD_URL, status=401, json={"error": "no", "code": "unauthenticated"})
    entry = _entry()
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: NEW_KEY}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data[CONF_API_KEY] == API_KEY


async def test_reconfigure_swaps_the_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Rotating a key on purpose keeps everything built on the entry."""
    _mock_ok(aioclient_mock)
    entry = _entry()
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: NEW_KEY}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_API_KEY] == NEW_KEY
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
