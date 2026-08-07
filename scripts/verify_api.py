#!/usr/bin/env python3
"""Check that the live Calendora API matches `docs/API-SURFACE.md`.

**Why this exists.** The test suite proves the integration matches the document.
Calendora's own tests prove the server matches its implementation. Until this
script existed, nothing tested *the document against the server* — so a wrong
field name in the doc meant a green build on both sides and a broken
integration in production, invisible to everybody.

It found four mismatches the first time it ran.

**What it reports.** Structure only: field names, types, counts and whether
documented invariants hold. Never a title, a name, a date, a location or a key.
The output is designed to be safe to paste into a public issue.

**What it does not do.** It never adapts to what it finds. A disagreement
between the document and the server is a gap to file — deciding which side is
wrong is not this script's business, and quietly following the server is how the
contract stops being the contract.

Usage:

    python scripts/verify_api.py                       # reads ~/.config/calendora-hass/api-key
    python scripts/verify_api.py --key-file /path/to/key
    CALENDORA_API_KEY=cal_… python scripts/verify_api.py

Exits non-zero if anything disagrees with the document.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiohttp

BASE_URL = "https://calendora.app"
DEFAULT_KEY_FILE = Path.home() / ".config" / "calendora-hass" / "api-key"

# Field sets exactly as `docs/API-SURFACE.md` §4a documents them. When the doc
# changes, change these — that is the point of the script.
DOCUMENTED = {
    "household": {"id", "name", "description", "color"},
    "members": {"id", "name", "kind", "color", "role", "avatarId", "personId"},
    "people": {
        "id", "name", "firstName", "lastName", "kind", "relationship",
        "birthday", "color",
    },
    "occurrences": {
        "id", "eventId", "occurrenceKey", "title", "description", "location",
        "icon", "isAllDay", "start", "end", "timezone", "repeats", "importance",
        "travelMinutes", "attendeeIds",
    },
    "lists": {"id", "name", "description", "type", "color", "icon", "isArchived"},
    "sections": {"id", "name", "position"},
    "items": {
        "id", "text", "quantity", "notes", "isChecked", "sectionId", "position",
        "due", "assignedMembershipId",
    },
}

MAX_RANGE_DAYS = 400
MEMBER_KINDS = {"person", "pet", "other"}


class Report:
    """Collects agreements and disagreements without ever holding a value."""

    def __init__(self) -> None:
        self.matches: list[str] = []
        self.mismatches: list[str] = []

    def check(self, condition: bool, message: str) -> bool:
        (self.matches if condition else self.mismatches).append(message)
        return condition

    def info(self, message: str) -> None:
        print(f"    {message}")


def value_shape(value: object) -> str:
    """Describe a value's shape without revealing it."""
    if value is None:
        return "null"
    if not isinstance(value, str):
        return type(value).__name__
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return "YYYY-MM-DD"
    if re.fullmatch(r"--\d{2}-\d{2}", value):
        return "--MM-DD"
    if "T" in value:
        return "ISO instant"
    return "string"


def compare_fields(report: Report, label: str, rows: list[dict], documented: set[str]) -> None:
    """Compare the keys a route actually returns against the documented set."""
    if not rows:
        report.info(f"{label}: no rows — fields not verified")
        return

    seen: set[str] = set()
    for row in rows:
        seen |= set(row)

    report.info(f"{label}: {len(rows)} rows; keys {sorted(seen)}")

    missing = documented - seen
    report.check(not missing, f"{label}: documented but absent: {sorted(missing)}"
                 if missing else f"{label}: every documented field present")

    if extra := seen - documented:
        report.check(False, f"{label}: returned but undocumented: {sorted(extra)}")

    if partial := {k for k in documented & seen if any(k not in row for row in rows)}:
        report.check(False, f"{label}: present on only some rows: {sorted(partial)}")


class Client:
    """Minimal client. Deliberately not the integration's — a conformance check
    that shares code with the thing it checks proves only that they agree."""

    def __init__(self, session: aiohttp.ClientSession, key: str) -> None:
        self._session = session
        self._key = key

    async def get(self, path: str, params: dict | None = None, key: str | None = None):
        return await self.send("GET", path, params=params, key=key)

    async def send(self, method, path, *, params=None, json=None, key=None):
        headers = {
            "Authorization": f"Bearer {key or self._key}",
            "Accept": "application/json",
        }
        async with self._session.request(
            method, f"{BASE_URL}{path}", headers=headers, params=params, json=json
        ) as response:
            try:
                return response.status, await response.json(content_type=None)
            except (aiohttp.ClientError, ValueError):
                return response.status, None


async def check_household(client: Client, report: Report) -> None:
    print("\n[1/8] GET /api/v1/household")
    status, body = await client.get("/api/v1/household")
    if not report.check(status == 200, f"household: HTTP {status}"):
        return

    compare_fields(report, "household", [body.get("household") or {}], DOCUMENTED["household"])

    timezone = body.get("timezone")
    report.check(
        isinstance(timezone, dict) and {"value", "source"} <= set(timezone),
        f"household.timezone shape: {sorted(timezone) if isinstance(timezone, dict) else timezone}",
    )
    if isinstance(timezone, dict):
        report.info(f"timezone.source = {timezone.get('source')!r}")
        try:
            ZoneInfo(timezone.get("value") or "")
            report.check(True, "household.timezone.value is a valid IANA zone")
        except (ZoneInfoNotFoundError, ValueError):
            report.check(False, "household.timezone.value is not a valid IANA zone")

    household_id = (body.get("household") or {}).get("id")
    report.check(
        isinstance(household_id, str) and bool(household_id),
        "household.id is a usable unique_id",
    )


async def check_members(client: Client, report: Report) -> None:
    print("\n[2/8] GET /api/v1/members")
    status, body = await client.get("/api/v1/members")
    if not report.check(status == 200, f"members: HTTP {status}"):
        return

    members = (body or {}).get("members") or []
    compare_fields(report, "members[]", members, DOCUMENTED["members"])

    kinds = {m.get("kind") for m in members if m.get("kind")}
    report.info(f"kind values observed: {sorted(kinds)}")
    report.check(kinds <= MEMBER_KINDS, f"members.kind within documented enum: {sorted(kinds)}")


async def check_people(client: Client, report: Report) -> None:
    print("\n[3/8] GET /api/v1/people")
    status, body = await client.get("/api/v1/people")
    if not report.check(status == 200, f"people: HTTP {status}"):
        return

    people = (body or {}).get("people") or []
    compare_fields(report, "people[]", people, DOCUMENTED["people"])

    birthdays = [p.get("birthday") for p in people if p.get("birthday")]
    shapes = {value_shape(b) for b in birthdays}
    report.info(f"birthday shapes: {sorted(shapes)} across {len(birthdays)} people")
    report.check(
        shapes <= {"YYYY-MM-DD", "--MM-DD"},
        f"birthday is a date string, never an instant: {sorted(shapes)}",
    )


async def check_events(client: Client, report: Report) -> None:
    print("\n[4/8] GET /api/v1/events")
    today = date.today()
    status, body = await client.get("/api/v1/events", {
        "from": (today - timedelta(days=330)).isoformat(),
        "to": (today + timedelta(days=60)).isoformat(),
    })
    if not report.check(status == 200, f"events: HTTP {status}"):
        return

    occurrences = (body or {}).get("occurrences") or []
    compare_fields(report, "occurrences[]", occurrences, DOCUMENTED["occurrences"])
    if not occurrences:
        return

    starts = [o["start"] for o in occurrences if o.get("start")]
    report.check(starts == sorted(starts), "occurrences arrive sorted by start")
    report.check(
        all("T" in s for s in starts),
        "start is an instant on every occurrence, including all-day ones",
    )
    report.check(
        all(o.get("id") == f"{o.get('eventId')}:{o.get('occurrenceKey')}" for o in occurrences),
        "id == eventId:occurrenceKey on every occurrence",
    )

    unresolvable = set()
    for occurrence in occurrences:
        try:
            ZoneInfo(occurrence.get("timezone") or "")
        except (ZoneInfoNotFoundError, ValueError):
            unresolvable.add(occurrence.get("timezone"))
    report.check(not unresolvable, f"unresolvable timezones: {sorted(unresolvable)}"
                 if unresolvable else "every occurrence timezone resolves")

    household_wide = [o for o in occurrences if not o.get("attendeeIds")]
    report.info(
        f"household-wide occurrences (empty attendeeIds): "
        f"{len(household_wide)} of {len(occurrences)}"
    )

    # All-day events resolved in the event's own timezone, which is the
    # conversion the integration performs and the one that is easy to get wrong.
    all_day = [o for o in occurrences if o.get("isAllDay")]
    report.info(f"all-day occurrences: {len(all_day)} of {len(occurrences)}")
    if all_day:
        inclusive = 0
        spans = set()
        for occurrence in all_day:
            zone = ZoneInfo(occurrence["timezone"])
            start = datetime.fromisoformat(occurrence["start"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(occurrence["end"].replace("Z", "+00:00"))
            start_day = start.astimezone(zone).date()
            end_day = end.astimezone(zone).date()
            spans.add((end_day - start_day).days)
            if end_day <= start_day:
                inclusive += 1
        report.info(f"all-day spans in whole days, event zone: {sorted(spans)}")
        report.info(
            f"all-day rows still using the old inclusive convention: {inclusive}"
            " (these rely on the integration's fallback)"
        )


async def check_lists(client: Client, report: Report) -> list[dict]:
    print("\n[5/8] GET /api/v1/lists")
    status, body = await client.get("/api/v1/lists")
    if status == 403:
        report.check(True, "lists:read not granted to this key (403, documented)")
        return []
    if not report.check(status == 200, f"lists: HTTP {status}"):
        return []

    lists = (body or {}).get("lists") or []
    compare_fields(report, "lists[]", lists, DOCUMENTED["lists"])
    return lists


async def check_list_items(client: Client, report: Report, lists: list[dict]) -> None:
    print("\n[6/8] GET /api/v1/lists/{id}/items")
    if not lists:
        report.info("skipped: no lists available")
        return

    seen_items: list[dict] = []
    sorted_lists = 0

    for todo_list in lists:
        status, body = await client.get(f"/api/v1/lists/{todo_list['id']}/items")
        if status != 200:
            report.check(False, f"list items: HTTP {status}")
            return
        if not seen_items:
            report.check("listId" in body, "items response carries listId")
        compare_fields(report, "sections[]", body.get("sections") or [], DOCUMENTED["sections"])

        items = body.get("items") or []
        # Ordering is checked **per list**. `position` is a fractional index
        # scoped to its own list, so concatenating two lists and sorting the
        # result asks a question the API never claimed to answer.
        positions = [i["position"] for i in items if "position" in i]
        if positions == sorted(positions):
            sorted_lists += 1
        seen_items.extend(items)

    compare_fields(report, "items[]", seen_items, DOCUMENTED["items"])
    if not seen_items:
        return

    position_types = {type(i["position"]).__name__ for i in seen_items if "position" in i}
    report.check(
        position_types <= {"str"},
        f"position is a fractional-index STRING: observed {sorted(position_types)}",
    )
    report.check(
        sorted_lists == len(lists),
        f"items arrive pre-sorted by position within each list"
        f" ({sorted_lists}/{len(lists)} lists)",
    )


async def check_stream(client: Client, report: Report, key: str, seconds: int = 6) -> None:
    print(f"\n[7/8] GET /api/v1/stream (sampling {seconds}s)")
    headers = {"Authorization": f"Bearer {key}", "Accept": "text/event-stream"}
    try:
        async with client._session.get(
            f"{BASE_URL}/api/v1/stream",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=None, sock_read=30),
        ) as response:
            report.check(response.status == 200, f"stream: HTTP {response.status}")
            report.check(
                "text/event-stream" in (response.headers.get("Content-Type") or ""),
                f"stream content-type: {response.headers.get('Content-Type')}",
            )

            lines: list[str] = []
            try:
                async with asyncio.timeout(seconds):
                    async for raw in response.content:
                        lines.append(raw.decode("utf-8", "replace").rstrip("\n"))
                        if len(lines) > 20:
                            break
            except TimeoutError:
                pass

            events = [l.removeprefix("event:").strip() for l in lines if l.startswith("event:")]
            payloads = {l.removeprefix("data:").strip() for l in lines if l.startswith("data:")}
            report.info(f"events observed: {events[:5]}")
            report.check("ready" in events, "stream opens with `ready`")
            report.check(
                payloads <= {"{}", ""},
                f"stream payloads are always empty: observed {sorted(payloads)}",
            )
    except (aiohttp.ClientError, TimeoutError) as err:
        report.check(False, f"stream: {type(err).__name__}")


async def check_errors(client: Client, report: Report) -> None:
    print("\n[8/8] Error shapes and documented rejections")

    status, body = await client.get("/api/v1/household", key="cal_not_a_real_key_at_all")
    report.check(status == 401, f"an unknown key returns 401: got {status}")
    if isinstance(body, dict):
        report.check({"error", "code"} <= set(body), f"error envelope keys: {sorted(body)}")
        report.check(
            body.get("code") == "unauthenticated",
            f"401 carries code `unauthenticated`: got {body.get('code')!r}",
        )

    status, body = await client.get("/api/v1/lists/does-not-exist-0000/items")
    report.check(status == 404, f"an unknown id returns 404: got {status}")

    status, _ = await client.get("/api/v1/events", {
        "from": "2026-08-01T00:00:00Z", "to": "2026-08-31T00:00:00Z"})
    report.check(status == 400, f"an instant in from/to is rejected: got {status}")

    # The exact boundary. `docs/API-SURFACE.md` §4 says a range *longer than* 400
    # days is rejected, which means 400 itself must be accepted — and the
    # integration's clamp lands precisely there, so an off-by-one here breaks the
    # one path that handles an over-long window.
    start = date(2026, 1, 1)
    for span, expected in ((MAX_RANGE_DAYS - 1, 200), (MAX_RANGE_DAYS, 200), (MAX_RANGE_DAYS + 1, 400)):
        status, _ = await client.get("/api/v1/events", {
            "from": start.isoformat(),
            "to": (start + timedelta(days=span)).isoformat(),
        })
        report.check(
            status == expected,
            f"a {span}-day range returns {expected}: got {status}",
        )


async def check_write_rejections(client: Client, report: Report, lists: list[dict]) -> None:
    """Check the documented *refusals*. Nothing here can mutate anything.

    Run unconditionally, because every one of these is a request the server is
    documented to turn down — if one of them ever succeeds, that is the finding.
    """
    print("\n[9/10] Write rejections (no data is created or changed)")

    # §7: PATCH on a row that does not exist is a 404, not an insert.
    if lists:
        status, _ = await client.send(
            "PATCH", f"/api/v1/lists/{lists[0]['id']}/items/does-not-exist-0000",
            json={"text": "should never be created"},
        )
        report.check(status == 404, f"PATCH on a missing item is 404, not an insert: got {status}")

        # NOTE: "an empty PATCH body is a 400" cannot be checked here. Against a
        # row that does not exist, 404 legitimately wins, and the precedence
        # between the two is not specified. It is checked in the write
        # round-trip instead, where a real row exists.

    # §7: `{id}` on an event PATCH is the SERIES id, and an occurrence id is
    # "refused by name". Using an id that cannot exist means this distinguishes
    # refused-by-shape (400) from merely-absent (404) without touching real data.
    status, body = await client.send(
        "PATCH", "/api/v1/events/does-not-exist-0000:2026-01-01",
        json={"title": "should never be applied"},
    )
    code = body.get("code") if isinstance(body, dict) else None
    report.check(
        status == 400,
        f"an occurrence id on PATCH /events is refused by name (400): got {status} {code}",
    )

    status, _ = await client.send(
        "PATCH", "/api/v1/events/does-not-exist-0000",
        json={"title": "should never be applied"},
    )
    report.check(status == 404, f"PATCH on a missing event series is 404: got {status}")


async def check_writes(client: Client, report: Report, lists: list[dict]) -> None:
    """Round-trip a throwaway item. **This creates and deletes real data.**

    Opt-in via --writes, and deliberately so: the person who connected the
    integration is notified about its writes (§8), a delete leaves a tombstone
    rather than vanishing, and nobody running a conformance check casually
    against their own household expects it to appear on their family's shopping
    list. Everything created here is named so that a human seeing it knows what
    it is, and is deleted before the script exits.
    """
    print("\n[10/10] Write round-trip (creates and deletes one throwaway item)")
    if not lists:
        report.info("skipped: no lists available")
        return

    list_id = lists[0]["id"]
    item_id = f"hass-conformance-{uuid4().hex[:12]}"
    label = "Home Assistant conformance check — safe to delete"

    # §7: the id is honoured when sent, which is what makes a retry idempotent.
    status, body = await client.send(
        "POST", f"/api/v1/lists/{list_id}/items",
        json={"id": item_id, "text": label, "quantity": "3", "due": "2026-09-03"},
    )
    if not report.check(status == 201, f"POST an item returns 201: got {status}"):
        return
    report.check(
        isinstance(body, dict) and body.get("id") == item_id,
        "a client-supplied id is honoured, so a retry cannot duplicate",
    )

    try:
        # §7: position is computed server-side and rejected if sent.
        status, _ = await client.send(
            "POST", f"/api/v1/lists/{list_id}/items",
            json={"id": f"{item_id}-pos", "text": label, "position": "a0"},
        )
        report.check(status == 400, f"sending `position` on create is rejected: got {status}")

        # §5/§7: a day-form due stays a day through the round trip. This is what
        # makes SET_DUE_DATE_ON_ITEM honourable rather than a lie.
        status, payload = await client.get(f"/api/v1/lists/{list_id}/items")
        created = next((i for i in (payload.get("items") or []) if i["id"] == item_id), None)
        if report.check(created is not None, "a created item comes back on the list"):
            report.check(
                created.get("due") == "2026-09-03",
                f"a day-form `due` round-trips as a day: got {value_shape(created.get('due'))}",
            )
            report.check(
                created.get("quantity") == "3",
                "quantity round-trips as sent",
            )

        # §6: the whole point. Patch ONE field and prove the others survive.
        status, _ = await client.send(
            "PATCH", f"/api/v1/lists/{list_id}/items/{item_id}", json={"isChecked": True},
        )
        report.check(status == 200, f"PATCH one field returns 200: got {status}")

        status, payload = await client.get(f"/api/v1/lists/{list_id}/items")
        after = next((i for i in (payload.get("items") or []) if i["id"] == item_id), None)
        if report.check(after is not None, "the patched item is still on the list"):
            report.check(after.get("isChecked") is True, "the patched field changed")
            report.check(
                after.get("quantity") == "3",
                f"an OMITTED field is untouched by a patch: quantity is "
                f"{'intact' if after.get('quantity') == '3' else 'GONE'}",
            )
            report.check(
                after.get("due") == "2026-09-03",
                "an omitted `due` is untouched by a patch",
            )

        # §6: a well-formed request that changes nothing is indistinguishable
        # from success, so an empty body is refused. Checked against a real row,
        # where 404 cannot mask the answer.
        status, _ = await client.send(
            "PATCH", f"/api/v1/lists/{list_id}/items/{item_id}", json={},
        )
        report.check(status == 400, f"an empty PATCH body on a real item is 400: got {status}")

        # An instant-form due, which is the other half of the two due flags.
        status, _ = await client.send(
            "PATCH", f"/api/v1/lists/{list_id}/items/{item_id}",
            json={"due": "2026-09-04T14:30:00.000Z"},
        )
        status, payload = await client.get(f"/api/v1/lists/{list_id}/items")
        after = next((i for i in (payload.get("items") or []) if i["id"] == item_id), None)
        report.check(
            after is not None and value_shape(after.get("due")) == "ISO instant",
            f"an instant-form `due` round-trips as an instant: got "
            f"{value_shape(after.get('due')) if after else 'missing'}",
        )

        # §6: explicit null clears.
        await client.send(
            "PATCH", f"/api/v1/lists/{list_id}/items/{item_id}", json={"due": None},
        )
        status, payload = await client.get(f"/api/v1/lists/{list_id}/items")
        after = next((i for i in (payload.get("items") or []) if i["id"] == item_id), None)
        report.check(
            after is not None and after.get("due") is None,
            "an explicit null clears the field",
        )

        # §6: an unknown field is a 400 that names it, never a silent drop.
        status, body = await client.send(
            "PATCH", f"/api/v1/lists/{list_id}/items/{item_id}", json={"sparkle": True},
        )
        report.check(status == 400, f"an unknown field is rejected, not dropped: got {status}")
        if isinstance(body, dict):
            report.check(
                "sparkle" in (body.get("error") or ""),
                f"the 400 names the offending field: {'yes' if 'sparkle' in (body.get('error') or '') else 'no'}",
            )

        # §7: both ids are checked against each other.
        if len(lists) > 1:
            status, _ = await client.send(
                "PATCH", f"/api/v1/lists/{lists[1]['id']}/items/{item_id}",
                json={"text": label},
            )
            report.check(
                status == 404,
                f"an item on a different list answers 404: got {status}",
            )
    finally:
        status, body = await client.send(
            "DELETE", f"/api/v1/lists/{list_id}/items/{item_id}"
        )
        report.check(status == 200, f"DELETE returns 200: got {status}")
        report.check(
            isinstance(body, dict) and body.get("deleted") is True,
            "DELETE confirms with deleted: true",
        )
        print(f"    cleaned up {item_id}")


def read_key(args: argparse.Namespace) -> str:
    if key := os.environ.get("CALENDORA_API_KEY"):
        return key.strip()
    path = Path(args.key_file).expanduser()
    if not path.is_file():
        sys.exit(
            f"No API key. Set CALENDORA_API_KEY, or put one in {path}.\n"
            "The key is a credential: keep it outside this repository."
        )
    return path.read_text().strip()


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key-file", default=str(DEFAULT_KEY_FILE))
    parser.add_argument(
        "--writes",
        action="store_true",
        help=(
            "also check the write routes. CREATES AND DELETES one clearly-named "
            "throwaway item on your first list. The person who connected the "
            "integration is notified about writes, and a delete leaves a "
            "tombstone rather than vanishing."
        ),
    )
    args = parser.parse_args()
    key = read_key(args)

    report = Report()
    print("Checking https://calendora.app against docs/API-SURFACE.md")
    print("Structure only — no titles, names, dates or keys are printed.")

    async with aiohttp.ClientSession() as session:
        client = Client(session, key)
        await check_household(client, report)
        await check_members(client, report)
        await check_people(client, report)
        await check_events(client, report)
        lists = await check_lists(client, report)
        await check_list_items(client, report, lists)
        await check_stream(client, report, key)
        await check_errors(client, report)
        await check_write_rejections(client, report, lists)
        if args.writes:
            await check_writes(client, report, lists)
        else:
            print("\n[10/10] Write round-trip skipped — pass --writes to include it")

    print("\n" + "=" * 72)
    print(f"AGREES WITH THE DOCUMENT ({len(report.matches)})")
    for line in report.matches:
        print(f"  ok   {line}")

    print(f"\nDISAGREES ({len(report.mismatches)})")
    for line in report.mismatches:
        print(f"  GAP  {line}")

    if report.mismatches:
        print(
            "\nEach disagreement is a gap to file — one of the document and the"
            "\nserver is wrong. Do not change the integration to match what was"
            "\nobserved; that is how the document stops being the contract."
        )
        return 1

    print("\nNo disagreements.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
