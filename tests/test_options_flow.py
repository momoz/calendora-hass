"""Per-member opt-in for shop-arrival notifications."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.calendora.const import (
    API_BASE_URL,
    CONF_API_KEY,
    CONF_SHOP_MEMBERS,
    DOMAIN,
)

from .const import API_KEY, load_fixture


async def _setup(hass, aioclient_mock) -> MockConfigEntry:
    aioclient_mock.get(f"{API_BASE_URL}/api/v1/household", json=load_fixture("household.json"))
    aioclient_mock.get(f"{API_BASE_URL}/api/v1/members", json=load_fixture("members.json"))
    aioclient_mock.get(f"{API_BASE_URL}/api/v1/events", json=load_fixture("events.json"))
    aioclient_mock.get(f"{API_BASE_URL}/api/v1/lists", json={"lists": []})
    aioclient_mock.get(f"{API_BASE_URL}/api/v1/stream", text="",
                       headers={"Content-Type": "text/event-stream"})
    entry = MockConfigEntry(
        domain=DOMAIN, title="Calendora", data={CONF_API_KEY: API_KEY}, version=2
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_nobody_is_opted_in_by_default(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Opt-in, not opt-out. Silence is not consent."""
    entry = await _setup(hass, aioclient_mock)

    assert entry.options.get(CONF_SHOP_MEMBERS, []) == []


async def test_members_can_be_opted_in_individually(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Per member, not per household — one person's wrist is not a household vote."""
    entry = await _setup(hass, aioclient_mock)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SHOP_MEMBERS: ["mem-1"]}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SHOP_MEMBERS] == ["mem-1"]
    # Opting one person in must not opt anybody else in.
    assert "mem-2" not in entry.options[CONF_SHOP_MEMBERS]
