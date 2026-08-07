"""Config flow for Calendora."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    CalendoraAuthError,
    CalendoraClient,
    CalendoraError,
    CalendoraForbiddenError,
)
from .const import CONF_API_KEY, CONF_SHOP_MEMBERS, DOMAIN, LOGGER

API_KEY_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): TextSelector(
            # PASSWORD, so the key is masked on screen and never lands in a
            # screenshot of the setup dialog. It is a credential (§9).
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        )
    }
)


class CalendoraConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Calendora."""

    VERSION = 2

    async def _async_key_works(self, api_key: str, errors: dict[str, str]) -> bool:
        """Prove the key works before storing it.

        `GET /api/v1/household` is the cheapest documented call that exercises
        authentication, and it needs only `household:read` — the scope every
        useful key must have anyway.
        """
        client = CalendoraClient(async_get_clientsession(self.hass), api_key)
        try:
            await client.async_get_household()
        except CalendoraAuthError:
            errors["base"] = "invalid_auth"
        except CalendoraForbiddenError as err:
            # A real key with the wrong scopes. Distinct from invalid_auth
            # because the user must issue a *different* key, not re-enter this
            # one — and the message names the scope, which is the actionable bit.
            LOGGER.debug("Calendora key is missing a scope: %s", err)
            errors["base"] = "missing_scope"
        except CalendoraError:
            errors["base"] = "cannot_connect"
        except Exception:  # noqa: BLE001 - a flow must never leak a traceback
            # Logged without the key: this line reaches every log, and every bug
            # report pasted out of one.
            LOGGER.exception("Unexpected error validating the Calendora API key")
            errors["base"] = "unknown"
        else:
            return True
        return False

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Take an API key and prove it works before saving it."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()

            # Weaker than the `async_set_unique_id` on a household id that
            # AGENTS.md asks for, and deliberately not faked: no documented
            # response field carries the household id yet, so there is nothing
            # honest to key on. This at least stops the same key being added
            # twice. Filed as a gap.
            self._async_abort_entries_match({CONF_API_KEY: api_key})

            if await self._async_key_works(api_key, errors):
                return self.async_create_entry(
                    title="Calendora", data={CONF_API_KEY: api_key}
                )

        return self.async_show_form(
            step_id="user", data_schema=API_KEY_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauth after a 401.

        Reached when Calendora rejects the key — revoked, expired, or simply
        unknown, which §3 makes deliberately indistinguishable. The remedy is
        the same for all three: a new key.
        """
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Take a replacement key into the existing entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            if await self._async_key_works(api_key, errors):
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), data_updates={CONF_API_KEY: api_key}
                )

        return self.async_show_form(
            step_id="reauth_confirm", data_schema=API_KEY_SCHEMA, errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Swap the key deliberately, rather than in response to a failure.

        Separate from reauth because the reasons differ: rotating a key on a
        schedule, or replacing one whose scopes were too narrow. Both should keep
        every entity and automation the user has already built on this entry,
        which removing and re-adding would not.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            if await self._async_key_works(api_key, errors):
                return self.async_update_reload_and_abort(
                    self._get_reconfigure_entry(),
                    data_updates={CONF_API_KEY: api_key},
                )

        return self.async_show_form(
            step_id="reconfigure", data_schema=API_KEY_SCHEMA, errors=errors
        )


    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> CalendoraOptionsFlow:
        """Return the options flow."""
        return CalendoraOptionsFlow()


class CalendoraOptionsFlow(OptionsFlowWithReload):
    """Who takes part in shop-arrival notifications.

    Per member, not per household (design §1). One person wanting their
    shopping list on their wrist is not consent for everybody else's phone, and
    a household-wide switch would make it one.

    `OptionsFlowWithReload` reloads the entry on save, so a change takes effect
    without the user restarting anything.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the members who opt in."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        coordinator = self.config_entry.runtime_data
        members = [
            SelectOptionDict(value=member["id"], label=member.get("name") or "Unknown")
            for member in coordinator.data.members
            if member.get("id")
        ]

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SHOP_MEMBERS,
                        default=self.config_entry.options.get(CONF_SHOP_MEMBERS, []),
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=members,
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )
