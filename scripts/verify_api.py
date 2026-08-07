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
    """Minimal read-only client. Deliberately not the integration's."""

    def __init__(self, session: aiohttp.ClientSession, key: str) -> None:
        self._session = session
        self._key = key

    async def get(self, path: str, params: dict | None = None, key: str | None = None):
        headers = {
            "Authorization": f"Bearer {key or self._key}",
            "Accept": "application/json",
        }
        async with self._session.get(
            f"{BASE_URL}{path}", headers=headers, params=params
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
