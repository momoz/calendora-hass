<!-- Third-party API contract, extracted from momoz/calendora docs/05-API-SURFACE.md
     on 2026-08-07. This is an EXTRACT, not the whole document — the internal doc contains
     the route inventory, sync-protocol internals and open security questions, none of which
     are part of the third-party contract and none of which are published here.
     Do not edit here; re-extract from source.

     SUPERSEDES the 2026-08-07 copy. That copy was two days stale and caused two false
     findings in a live verification. Changes: writes SHIPPED; `dueAt` replaced by `due`;
     a types table added; the 400-day boundary corrected. -->

# Calendora — third-party API contract

This is the **entire** interface available to this integration. If something you need is not
here, it is not part of the contract — **file a gap**. Do not infer endpoints, do not probe,
do not use anything you find that is not written here.

**Status: reads and writes are both live.**

---

## 1. Base URL

```
https://calendora.app
```

Hardcode it as one constant. There is no issuer field on a key and no discovery endpoint.
Never guess a host and never derive one from a key.

## 2. Authentication

```
Authorization: Bearer cal_…
```

Scoped to **exactly one household**, revocable. Scopes are exact — **`calendar:write` does
not imply `calendar:read`.** No wildcard.

`calendar:read` · `calendar:write` · `lists:read` · `lists:write` · `household:read` ·
`presence:write`

**There is no household parameter on any route**, because a key names one.

A key is **not a member**. See §8.

## 3. Errors

```json
{ "error": "human sentence", "code": "unauthenticated" }
```

| `code` | Status | Means |
|---|---|---|
| `unauthenticated` | 401 | No key, unknown, revoked, or expired — **deliberately indistinguishable** |
| `forbidden` | 403 | Valid key, missing scope. Names the scope |
| `not_found` | 404 | No such thing — **or it belongs to another household** |
| `bad_request` | 400 | Says which parameter |
| `server_error` | 500 | Ours |

On **401**, raise `ConfigEntryAuthFailed`. Never retry a 401, never fail silently.

A 404 can mean "not yours" — **do not treat it as proof an id is invalid.**

## 4. Reads

```
GET /api/v1/household                    household:read
GET /api/v1/members                      household:read
GET /api/v1/people                       household:read
GET /api/v1/events?from=&to=&member=     calendar:read
GET /api/v1/lists                        lists:read
GET /api/v1/lists/{id}/items             lists:read
GET /api/v1/stream                       household:read   # SSE
```

### `GET /api/v1/household`
```json
{ "household": { "id", "name", "description", "color" },
  "timezone":  { "value": "Europe/London", "source": "key-owner" } }
```
`household.id` is your config entry's `unique_id`.

### `GET /api/v1/members`
```json
{ "members": [ { "id", "name", "kind", "color", "role", "avatarId", "personId" } ] }
```
`name` is **already resolved** server-side, including a display-name override. Do not
re-derive it. No email, no user id, no sign-in state.

### `GET /api/v1/people`
```json
{ "people": [ { "id", "name", "firstName", "lastName", "kind",
                "relationship", "birthday", "color" } ] }
```

### `GET /api/v1/events`
```json
{ "occurrences": [ {
    "id": "{eventId}:{occurrenceKey}", "eventId", "occurrenceKey",
    "title", "description", "location", "icon", "isAllDay",
    "start": "2026-08-07T09:00:00.000Z", "end": "…", "timezone": "Europe/London",
    "repeats": true, "importance", "travelMinutes", "attendeeIds": [] } ] }
```
Sorted by `start`. One object **per occurrence, not per rule** — the server expands
recurrence; do not re-derive it. `repeats` is a boolean; the RRULE is never exposed.

**`start` and `end` are always instants, including when `isAllDay` is true**, and `timezone`
is the event's own authored zone. Derive an all-day date **in that zone** — never the
viewer's, never UTC.

**An all-day `end` is exclusive**: a one-day event on the 11th ends `2026-08-12`.

**An occurrence with empty `attendeeIds` belongs to the whole household** and is never
filtered out by `?member=`.

**`from` and `to` are both inclusive**, `YYYY-MM-DD`, resolved in the key owner's timezone.
An instant is rejected. **`to = from + 400 days` is accepted; `+401` is not; `from = to` is a
single day.** *(Corrected 2026-08-07 — the server previously compared elapsed time and
refused exactly 400. Found by live verification.)*

### `GET /api/v1/lists`
```json
{ "lists": [ { "id", "name", "description", "type", "color", "icon", "isArchived" } ] }
```

### `GET /api/v1/lists/{id}/items`
```json
{ "listId",
  "sections": [ { "id", "name", "position" } ],
  "items": [ { "id", "text", "quantity", "notes", "isChecked",
               "sectionId", "position", "due", "assignedMembershipId" } ] }
```
Pre-sorted by `position` — **a fractional index, a STRING.** Compare as a string; never parse
it as a number.

**`due` replaced `dueAt` on 2026-08-07. Breaking, and deliberate** — it closes GAP-002. The
form carries the meaning:

| Value | Means |
|---|---|
| `"2026-08-11"` | due that **day** |
| `"2026-08-11T18:00:00.000Z"` | due at that **moment** |
| `null` | no due date |

There is no separate boolean, because a boolean beside the value has a state where the two
disagree.

### `GET /api/v1/stream`
SSE. `event: ready` on connect, `event: changed` when something changes, `: keep-alive` every
25s. **Payload is always `{}`** — it says *that* something changed, never what. Re-read on
`changed`. No household parameter.

## 5. Types

| Field | Type | Notes |
|---|---|---|
| every id, `attendeeIds[]` | `string` | Opaque. Do not parse |
| `name`, `title`, `text` | `string` | Never null, never empty |
| `description`, `location`, `notes`, `quantity`, `icon`, `color`, `relationship`, `firstName`, `lastName` | `string \| null` | Null means not set |
| `kind` | `"person" \| "pet" \| "other"` | |
| `role` | `"owner" \| "admin" \| "member" \| "guest"` | |
| `type` (lists) | `"shopping" \| "todo" \| "packing" \| "checklist" \| "custom"` | |
| `isAllDay`, `repeats`, `isChecked`, `isArchived` | `boolean` | Never null |
| `importance` | `integer 1–10 \| null` | **Null is not zero and not "normal"** |
| `travelMinutes` | `integer ≥ 0 \| null` | Whole minutes |
| `start`, `end` | `string` | ISO instant, always — even when `isAllDay` |
| `timezone` | `string` | IANA name |
| `birthday` | `string \| null` | `YYYY-MM-DD` **or** year-less `--MM-DD`. Never an instant |
| `due` | `string \| null` | Date **or** instant — the form is the meaning |
| `position` | `string` | Fractional index. **Never parse as a number** |

## 6. Write semantics — read this before any write

> **Partial. An omitted field is untouched. An explicit `null` clears.
> Never read-merge-write.**

RFC 7386 JSON Merge Patch. Consequences you must know:

- **Send only what you are changing.** Sending a field back unchanged is not harmful, but it
  makes your write authoritative over it — so a concurrent edit by somebody else loses.
- **`null` is a value, not an absence.** `{"location": null}` clears it; `{}` leaves it alone.
- **An unknown field is a 400 that names it.** Unknown is an error; absent is "no change".
  The two are never confused. **Do not send fields speculatively.**
- **A `PATCH` body of `{}` is a 400.** A well-formed request that changes nothing is
  indistinguishable from success.
- **`PATCH` on a row that does not exist is a 404**, not an insert.
- **`updatedAt` is the server's, always.** You cannot backdate a write to win a conflict.

## 7. Writes

`position`, `creatorId`, `actor` and the RRULE **never appear in a write body.**

### `POST /api/v1/lists/{id}/items` → `201 {"id"}`
```json
{ "id": "optional", "text": "Milk", "quantity": "2", "notes": null,
  "isChecked": false, "due": "2026-09-03" | "2026-09-03T14:30:00.000Z" | null,
  "sectionId": null, "assignedMembershipId": null }
```
**Send an `id`.** It is honoured when present. A request that times out cannot be
distinguished from a lost reply, and a retry without an id creates the item twice.

`position` is **computed here and rejected if sent.**

A day-form `due` is anchored at **9am** in the caller's zone, not midnight — "due Thursday"
means during Thursday.

### `PATCH /api/v1/lists/{id}/items/{itemId}` → `200 {"id"}`
Same fields minus `id`. `{}` is a 400.

Setting `isChecked` stamps `checkedAt` with it. **Both ids are checked against each other** —
an item that exists but is on a different list answers 404.

### `DELETE /api/v1/lists/{id}/items/{itemId}` → `200 {"id","deleted":true}`
A tombstone, never a hard delete.

### `POST /api/v1/events` → `201 {"id"}`
```json
{ "id": "optional", "title": "Bin day",
  "start": "2026-08-11" | "2026-08-11T07:00:00.000Z",
  "end":   "2026-08-12" | "2026-08-11T07:15:00.000Z",
  "timezone": "Europe/London", "isAllDay": true,
  "description": null, "location": null, "icon": null,
  "importance": 5, "travelMinutes": 20 }
```
**`start` and `end` say whether they are days or moments by their FORM.** A date is a day, an
instant is a moment. Mixing the two is a 400. Send `isAllDay` only if you want it checked — a
value disagreeing with the form is a 400, not a silent choice.

This closes a trap: a client meaning "all day on the 11th" naturally sends
`2026-08-11T00:00:00Z`, which in a New York event's own zone is the evening of the **tenth**.
A date has no such reading.

An all-day `end` is exclusive. An end at or before the start is nudged up a day.
`title` cannot be empty. `importance` is 1–10.

### `PATCH /api/v1/events/{id}` → `200 {"id"}`
Same fields minus `id`. `{}` is a 400.

**`{id}` is the SERIES id. An occurrence id is refused by name.** `GET` hands you
`{eventId}:{occurrenceKey}`, so PATCHing what you were given is the obvious move — and taking
it to mean the series would move every Tuesday of somebody's year. **Editing one occurrence
of a repeat is not exposed here.**

### `DELETE /api/v1/events/{id}` → `200 {"id","deleted":true}`
A tombstone. **A repeating event is refused, 400** — the scope description promises it cannot
delete a whole series, and that has to stay true.

## 8. Attribution

Every write is attributed to the **integration**, never to the person who connected it. The
key's own label is the name: *"Added by Home Assistant, connected by Mike"*.

A behaviour worth knowing: **the person who connected the integration is notified about its
writes.** They set up an automation; they did not add this event.

## 9. Reordering is a deliberate non-goal

**There is no move endpoint, there will not be one, and `position` never appears in a write
body.** Home Assistant's list is flat; Calendora's sections are shops. A drag either silently
changes which shop an item is bought at, or snaps back — and reordering is the only
capability whose absence costs a user nothing they can see.

Order comes back already sorted. Render it; do not compute it.

## 10. Not available, and not coming

The sync protocol (`/api/sync/*`) · identity, sessions, passkeys, invitation tokens ·
impersonation · the personal Second Brain · the household activity log (**file a gap, do not
scrape**) · the ICS feed (`/api/feeds/{token}`) — superseded and prohibited.

**`POST /api/v1/presence`** remains designed and **blocked** pending a decision on retention,
syncability and per-member opt-out.

## 11. Security expectations

The API key is a secret: not in logs, diagnostics, issue templates or debug output. A Home
Assistant webhook id **is itself a credential** — `webhook.async_generate_id()`, never
derived from anything guessable. No real household data in screenshots, fixtures or example
YAML in this public repo.
