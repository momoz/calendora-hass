"""The Calendora `/api/v1` client.

**This is the only file in the integration that makes HTTP calls.** One file that
knows the wire means the rest of the integration cannot quietly grow a second way
to talk to Calendora — and it is the file where a temptation to reach for a
prohibited surface would have to be written down in order to happen.

The interface this speaks is `docs/API-SURFACE.md` and nothing else. Notably
prohibited, and absent from this file on purpose: `/api/sync/*`, session cookies,
scraping any HTML surface, and `/api/feeds/{token}` — the ICS feed, which §8 now
lists as superseded and prohibited. It was implemented here in 0.0.1 and has been
deleted rather than deprecated: a prohibited surface left in the codebase is a
prohibited surface someone reaches for at 2am.

This file deals in transport, authentication and error meaning. It deliberately
does **not** interpret response bodies — it returns decoded JSON and lets callers
name fields, so that when a response shape is finally documented, nothing in here
has to change.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date
from http import HTTPStatus
from typing import Any

import aiohttp

from .const import API_BASE_URL, MAX_EVENT_RANGE_DAYS

# Generous enough for a household with years of history, short enough that a hung
# connection cannot pin a coordinator refresh open forever.
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)

# The stream is long-lived, so a total timeout would kill a healthy connection.
# `docs/API-SURFACE.md` §4 promises a keep-alive comment every 25 seconds, which
# makes a read timeout the right instrument: silence for well over that interval
# means the connection is dead even though the socket has not said so.
STREAM_TIMEOUT = aiohttp.ClientTimeout(total=None, sock_read=90)


class CalendoraError(Exception):
    """Base class for every failure this client raises."""


class CalendoraConnectionError(CalendoraError):
    """Calendora could not be reached, or did not answer in time."""


class CalendoraAuthError(CalendoraError):
    """401 — no key, unknown key, revoked, or expired.

    §3 makes those four **deliberately indistinguishable**, so this exception
    cannot and must not try to tell a user which one it was. The caller's only
    correct response is `ConfigEntryAuthFailed`: never a retry, never a silent
    failure.
    """


class CalendoraForbiddenError(CalendoraError):
    """403 — the key is valid but is missing a scope.

    Kept separate from auth failure because the remedy differs and is actionable:
    the user issues a new key carrying the scope named in the message. Sending
    them through reauth instead would loop, because the key they have is fine.
    """


class CalendoraNotFoundError(CalendoraError):
    """404 — no such thing, **or it belongs to another household**.

    §3 is explicit that those are the same answer, so that ids cannot be
    enumerated. Never read this as proof that an id is invalid.
    """


class CalendoraBadRequestError(CalendoraError):
    """400 — the request was wrong, and the message names the parameter."""


class CalendoraServerError(CalendoraError):
    """500 — Calendora's problem, and probably transient."""


class CalendoraResponseError(CalendoraError):
    """The response was not something this client could read at all."""


def _error_for(status: int, code: str | None, message: str) -> CalendoraError:
    """Map one documented failure onto its exception.

    Keyed on the HTTP status rather than on the `code` string. The status is what
    the contract fixes; a `code` this client has never seen must still produce
    the right behaviour instead of falling through to something generic.
    """
    if status == HTTPStatus.UNAUTHORIZED:
        return CalendoraAuthError(message)
    if status == HTTPStatus.FORBIDDEN:
        return CalendoraForbiddenError(message)
    if status == HTTPStatus.NOT_FOUND:
        return CalendoraNotFoundError(message)
    if status == HTTPStatus.BAD_REQUEST:
        return CalendoraBadRequestError(message)
    if status >= HTTPStatus.INTERNAL_SERVER_ERROR:
        return CalendoraServerError(message)
    return CalendoraResponseError(f"Calendora answered HTTP {status} ({code})")


class CalendoraClient:
    """Reads Calendora's `/api/v1` surface."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str) -> None:
        """Initialise the client with Home Assistant's shared session."""
        self._session = session
        self._api_key = api_key

    def _build_headers(self, accept: str = "application/json") -> dict[str, str]:
        """Build the auth header.

        Assembled per request rather than kept on the instance, so the key never
        sits in an attribute that a repr, a diagnostics dump or a debugger frame
        might surface. The key is a secret (§9), and the cheapest way to keep it
        out of somewhere is to never put it there.
        """
        return {"Authorization": f"Bearer {self._api_key}", "Accept": accept}

    async def _async_send(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        expect: int = HTTPStatus.OK,
    ) -> Any:
        """Perform one request and return decoded JSON.

        Every failure becomes a `CalendoraError` subclass, and no message raised
        from here contains the key: messages reach logs, and logs reach public
        issue trackers.
        """
        try:
            response = await self._session.request(
                method,
                f"{API_BASE_URL}{path}",
                headers=self._build_headers(),
                params=params,
                json=json,
                timeout=REQUEST_TIMEOUT,
            )
        except aiohttp.ClientError as err:
            raise CalendoraConnectionError("Could not reach Calendora") from err
        except TimeoutError as err:
            raise CalendoraConnectionError("Calendora timed out") from err

        async with response:
            if response.status != expect:
                code, message = await self._async_read_error(response)
                raise _error_for(response.status, code, message)

            try:
                return await response.json()
            except (aiohttp.ClientError, ValueError) as err:
                raise CalendoraResponseError(
                    "Calendora returned something that was not JSON"
                ) from err

    async def _async_request(
        self, path: str, params: dict[str, str] | None = None
    ) -> Any:
        """Perform one GET and return decoded JSON."""
        return await self._async_send("GET", path, params=params)

    @staticmethod
    async def _async_read_error(
        response: aiohttp.ClientResponse,
    ) -> tuple[str | None, str]:
        """Pull `{"error": ..., "code": ...}` out of a failure response.

        A failing server is precisely the one likely to answer with an HTML error
        page from a proxy rather than the documented shape, so this never assumes
        it parsed.
        """
        try:
            body = await response.json()
        except (aiohttp.ClientError, ValueError):
            return None, f"Calendora answered HTTP {response.status}"

        if not isinstance(body, dict):
            return None, f"Calendora answered HTTP {response.status}"

        code = body.get("code")
        message = body.get("error") or f"Calendora answered HTTP {response.status}"
        return (code if isinstance(code, str) else None), str(message)

    async def async_get_household(self) -> Any:
        """`GET /api/v1/household` — requires `household:read`."""
        return await self._async_request("/api/v1/household")

    async def async_get_members(self) -> Any:
        """`GET /api/v1/members` — requires `household:read`."""
        return await self._async_request("/api/v1/members")

    async def async_get_people(self) -> Any:
        """`GET /api/v1/people` — requires `household:read`."""
        return await self._async_request("/api/v1/people")

    async def async_get_lists(self) -> Any:
        """`GET /api/v1/lists` — requires `lists:read`."""
        return await self._async_request("/api/v1/lists")

    async def async_get_list_items(self, list_id: str) -> Any:
        """`GET /api/v1/lists/{id}/items` — requires `lists:read`."""
        return await self._async_request(f"/api/v1/lists/{list_id}/items")

    async def async_get_events(
        self, date_from: date, date_to: date, member_id: str | None = None
    ) -> Any:
        """`GET /api/v1/events` — requires `calendar:read`.

        Takes `date` objects, never datetimes. §4: `from` and `to` are days,
        resolved in the key owner's timezone, and an instant is **rejected** —
        the same instant means different days depending on the zone it was
        written in. Typing the parameter as `date` makes that unrepresentable
        rather than merely documented.
        """
        if date_to < date_from:
            raise ValueError("date_to is before date_from")

        span = (date_to - date_from).days
        if span > MAX_EVENT_RANGE_DAYS:
            # Checked here rather than left to the server. The server rejects
            # rather than truncating, and this is a programming error rather
            # than a user one — failing at the call site names the real mistake.
            raise ValueError(
                f"range of {span} days exceeds the documented maximum of "
                f"{MAX_EVENT_RANGE_DAYS}"
            )

        params = {"from": date_from.isoformat(), "to": date_to.isoformat()}
        if member_id is not None:
            params["member"] = member_id
        return await self._async_request("/api/v1/events", params)

    # --- writes -------------------------------------------------------------
    #
    # §6 is the rule these all obey: **partial, omitted untouched, explicit null
    # clears, never read-merge-write.** None of these methods takes a "full
    # item" — they take only what is changing, because a field sent back
    # unchanged still makes this client authoritative over it and loses somebody
    # else's concurrent edit.

    async def async_create_list_item(
        self, list_id: str, item_id: str, fields: dict[str, Any]
    ) -> Any:
        """`POST /api/v1/lists/{id}/items` — requires `lists:write`.

        The caller supplies `item_id`. §7 is explicit about why: a request that
        times out cannot be told apart from a lost reply, and a retry without an
        id creates the item twice. A client-chosen id makes the retry idempotent.

        `position` is computed server-side and **rejected if sent** (§7), so it
        is not accepted here at all.
        """
        return await self._async_send(
            "POST",
            f"/api/v1/lists/{list_id}/items",
            json={"id": item_id, **fields},
            expect=HTTPStatus.CREATED,
        )

    async def async_update_list_item(
        self, list_id: str, item_id: str, changes: dict[str, Any]
    ) -> Any:
        """`PATCH /api/v1/lists/{id}/items/{itemId}` — requires `lists:write`.

        `changes` must contain **only** what is being changed. An empty body is a
        400 by design (§6) — a well-formed request that changes nothing is
        indistinguishable from success — so callers must not send one.
        """
        if not changes:
            raise ValueError("a PATCH with no changes is rejected by the API")
        return await self._async_send(
            "PATCH", f"/api/v1/lists/{list_id}/items/{item_id}", json=changes
        )

    async def async_delete_list_item(self, list_id: str, item_id: str) -> Any:
        """`DELETE /api/v1/lists/{id}/items/{itemId}` — requires `lists:write`."""
        return await self._async_send(
            "DELETE", f"/api/v1/lists/{list_id}/items/{item_id}"
        )

    async def async_create_event(self, event_id: str, fields: dict[str, Any]) -> Any:
        """`POST /api/v1/events` — requires `calendar:write`.

        The caller chooses the id, for the same reason list items do: a request
        that times out cannot be told from a reply that was lost, and a retry
        without an id creates the event twice.
        """
        return await self._async_send(
            "POST", "/api/v1/events",
            json={"id": event_id, **fields},
            expect=HTTPStatus.CREATED,
        )

    async def async_update_event(
        self, event_id: str, scope: str, changes: dict[str, Any]
    ) -> Any:
        """`PATCH /api/v1/events/{id}` — requires `calendar:write`.

        `event_id` may be a series id or the `{eventId}:{occurrenceKey}` form
        that `GET` handed out; the two mean different things and `scope` says
        which was meant.

        **`scope` is a body field and is required on every call** — including a
        bare series id and an event that does not repeat, where all three values
        mean the same thing. The server never guesses which occurrences were
        meant, and omitting it is a 400.

        Returns the reply intact, because **the `id` in it is not always the id
        that was sent**: `this` and `following` create a row, and that row is
        what a subsequent request must address.
        """
        if not changes:
            raise ValueError("a PATCH carrying only a scope changes nothing")
        return await self._async_send(
            "PATCH", f"/api/v1/events/{event_id}", json={"scope": scope, **changes}
        )

    async def async_delete_event(self, event_id: str) -> Any:
        """`DELETE /api/v1/events/{id}` — requires `calendar:write`.

        A repeating event is refused with a 400 that explains itself. That is
        not a failure to handle quietly: the message is written for the person
        reading it, so callers should surface it rather than replace it.
        """
        return await self._async_send("DELETE", f"/api/v1/events/{event_id}")

    async def async_stream(self) -> AsyncIterator[str]:
        """Yield event names from `GET /api/v1/stream` — requires `household:read`.

        Server-sent events. §4 fixes the vocabulary: `ready` on connect, `changed`
        when something in the household changes, and a `: keep-alive` comment
        every 25 seconds.

        **The payload is always `{}`.** It says *that* something changed, never
        what — so this yields event names and drops `data:` on the floor rather
        than pretending to parse it. A caller reading the payload would be
        building on something the contract explicitly refuses to promise.

        Reconnection is the caller's business: this iterator ends when the stream
        does, because how eagerly to come back is a policy decision and policy
        does not belong on the wire.
        """
        try:
            response = await self._session.get(
                f"{API_BASE_URL}/api/v1/stream",
                headers=self._build_headers(accept="text/event-stream"),
                timeout=STREAM_TIMEOUT,
            )
        except aiohttp.ClientError as err:
            raise CalendoraConnectionError(
                "Could not open the Calendora stream"
            ) from err
        except TimeoutError as err:
            raise CalendoraConnectionError("The Calendora stream timed out") from err

        async with response:
            if response.status != HTTPStatus.OK:
                code, message = await self._async_read_error(response)
                raise _error_for(response.status, code, message)

            try:
                async for raw_line in response.content:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    # A `:` comment is the keep-alive. Its whole job is to prove
                    # the connection is alive, which arriving has already done.
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("event:"):
                        yield line.removeprefix("event:").strip()
            except (aiohttp.ClientError, TimeoutError) as err:
                raise CalendoraConnectionError(
                    "The Calendora stream disconnected"
                ) from err
