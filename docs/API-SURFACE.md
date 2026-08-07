# Calendora `/api/v1` — the third-party surface

**Source:** `momoz/calendora` @ `becbe3e`
**Contract fingerprint:** `4d4b1291bcf4e0ac` — see §10
**Regenerated:** 2026-08-08

This is the whole of what a third-party client is promised. Nothing outside this
file and `fixtures/api-v1/` is a contract: if something you need is not written
down here, that is a gap to file rather than a behaviour to discover.

**Hand-built for a public repository.** It deliberately omits the first-party
route inventory, the sync protocol, and anything unsettled.

---

## What changed since the last extract

- **A refused write now answers `409 conflict` rather than `400 bad_request`**
  (§2, §7). Retry-safety is machine readable: `conflict` is the only code you
  should retry on.
- **`PATCH /events/{id}` now accepts the occurrence id it was already handing
  out** (§7). It previously refused that form, so a client could read
  "gym, Tuesday the 16th" and had no way to edit that Tuesday. `GAP-007`.
- **`scope` is now required on every `PATCH`** — including a bare series id and
  an event that does not repeat. **Breaking.**
- **`due` replaced `dueAt`** on list items (§6). **Breaking.** `GAP-002`.
- **The 400-day range limit accepts exactly 400** (§5). It used to refuse it.
  `GAP-005`.
- **Types for every field** (§9). `GAP-006`.

---

## 1. Authentication

`Authorization: Bearer cal_…`

A key names **exactly one household**. No route takes a household id, because a
client that could name one could name somebody else's.

**Scopes are exact**: `calendar:read` does **not** imply `calendar:write`.

| Scope | Allows |
|---|---|
| `household:read` | The household, its members, and people |
| `calendar:read` | Reading events |
| `calendar:write` | Creating, changing and removing events |
| `lists:read` | Reading lists and their items |
| `lists:write` | Creating, changing and removing list items |

There is no wildcard scope, and there will not be one. A key that can do
everything is indistinguishable from a password, and it is handed to software
running in somebody's house.

**A key is not a member.** Changes made through one are recorded as the
integration — never as the person who created it.

---

## 2. Errors

Every route answers the same shape.

```json
{ "error": "a human sentence", "code": "bad_request" }
```

**Branch on `code`, never on the sentence.** Sentences change; codes do not — and
`bad_request` and `conflict` need opposite responses, so telling them apart by
reading English would break the first time a message is reworded.

| `code` | Status | Means |
|---|---|---|
| `unauthenticated` | 401 | No key, unknown, revoked, or expired — **deliberately indistinguishable** |
| `forbidden` | 403 | Valid key, missing scope. Names the scope, because re-issuing is actionable |
| `not_found` | 404 | No such thing — **or it belongs to another household** |
| `bad_request` | 400 | Your request is wrong. Says which part. **Do not retry unchanged** |
| `conflict` | 409 | Your request was **correct** and somebody else got there first. **Retry it** |
| `server_error` | 500 | Ours. File a gap |

A list or event in another household answers **404, not 403**: "that exists but
is not yours" is how ids get enumerated.

---

## 3. Reads

```
GET /household        household:read
GET /members          household:read
GET /people           household:read
GET /events           calendar:read
GET /lists            lists:read
GET /lists/{id}/items lists:read
GET /stream           household:read   (SSE)
```

### `GET /household`
```json
{ "household": { "id", "name", "description", "color" },
  "timezone":  { "value": "Europe/London", "source": "key-owner" } }
```

There is **no household timezone** — it is a per-person preference, so this
reports whose it is rather than pretending otherwise. Key your configuration on
`household.id`.

### `GET /members`
```json
{ "members": [ { "id", "name", "kind", "color", "role", "avatarId", "personId" } ] }
```

`name` is **already resolved** — a display-name override beats the stored name
server-side. Making a client work that out is how two clients call the same
person different things.

### `GET /people`
```json
{ "people": [ { "id", "name", "firstName", "lastName", "kind",
                "relationship", "birthday", "color" } ] }
```

### `GET /stream`

Server-sent events. `event: ready` on connect, `event: changed` when something
changes, `: keep-alive` every 25 seconds.

**The payload is always `{}`.** It says that something changed, never what. On
`changed`, re-read whatever you care about.

---

## 4. Events are occurrences

One object per occurrence, not per rule.

```json
{ "occurrences": [ {
    "id": "{eventId}:{occurrenceKey}", "eventId", "occurrenceKey",
    "title", "description", "location", "icon",
    "isAllDay": false,
    "start": "2027-03-02T07:00:00.000Z", "end": "…", "timezone": "Europe/London",
    "repeats": true, "importance", "travelMinutes",
    "attendeeIds": ["membershipId", …]
} ] }
```

Sorted by `start`. **The RRULE is never exposed** — `repeats` is a boolean.

**`start` and `end` are always instants, including when `isAllDay` is true.**
`timezone` is the event's own authored zone. An all-day event must be rendered
as a *date* derived using that zone — not the viewer's, and not UTC. Converting
in the viewer's zone is how a birthday moves a day.

**An all-day `end` is EXCLUSIVE** — the first instant not in the event. One day
on 10 August is `2027-08-10T00:00:00` → `2027-08-11T00:00:00`. This is the RFC
5545 `VALUE=DATE` convention, so no translation is needed in either direction.

**`attendeeIds` is resolved per occurrence.** Somebody who dropped out of one
Tuesday is absent from that Tuesday and present on the others.

**An occurrence with an empty `attendeeIds` belongs to the whole household** and
is never filtered out by `?member=`.

---

## 5. Asking for a range

`GET /events?from=YYYY-MM-DD&to=YYYY-MM-DD&member={membershipId}`

`from` and `to` are **days, not instants**, resolved in the key owner's
timezone. An instant is rejected: it would mean a different day depending on the
zone it was written in.

**Both ends are inclusive**, and the limit is the difference between them:

| | |
|---|---|
| `to = from + 400 days` | accepted |
| `to = from + 401 days` | 400 |
| `from = to` | a single day |

A longer range is **rejected rather than truncated** — a client that asked for
five years and got one would believe the calendar was empty after that.

---

## 6. Lists

### `GET /lists`
```json
{ "lists": [ { "id", "name", "description", "type", "color", "icon", "isArchived" } ] }
```

### `GET /lists/{id}/items`
```json
{ "listId",
  "sections": [ { "id", "name", "position" } ],
  "items": [ { "id", "text", "quantity", "notes", "isChecked",
               "sectionId", "position", "due", "assignedMembershipId" } ] }
```

Both arrays arrive **pre-sorted by `position`, which is a fractional index — a
STRING.** Compare it as a string; parsing it as a number gives an order nobody
arranged.

### `due` carries day-versus-moment in its FORM

| Value | Means |
|---|---|
| `"2027-09-03"` | due that **day** |
| `"2027-09-03T14:30:00.000Z"` | due at that **moment** |
| `null` | no due date |

**This replaced `dueAt`, and the replacement is the point.** An instant cannot
say which it is: `2027-09-03T22:00:00Z` is either "due on the 4th" or "due at
22:00". The write takes the same two forms, so an item read and written back
unchanged really is unchanged.

There is no separate boolean. A boolean beside the value has a state where the
two disagree, and a field that can contradict itself eventually will.

---

## 7. Writes

```
POST   /events                        calendar:write
PATCH  /events/{id}                   calendar:write
DELETE /events/{id}                   calendar:write
POST   /lists/{id}/items              lists:write
PATCH  /lists/{id}/items/{itemId}     lists:write
DELETE /lists/{id}/items/{itemId}     lists:write
```

**Semantics, everywhere:** partial. An omitted field is untouched, an explicit
`null` clears, and the server never reads-merges-writes on your behalf. An
unknown field is a **400 that names it** — never a silent drop, because a third
party cannot notice one and files it against the wrong project.

**`position` never appears in a write body.** Ordering is server-owned; see §8.

### `POST /events` → `201 { "id" }`

```json
{ "id": "optional — yours to choose",
  "title": "Bin day",
  "start": "2027-08-11"  |  "2027-08-11T07:00:00.000Z",
  "end":   "2027-08-12"  |  "2027-08-11T07:15:00.000Z",
  "timezone": "Europe/London",
  "description": null, "location": null, "icon": null,
  "importance": 5, "travelMinutes": 20 }
```

**Send an `id`.** It is optional and honoured. A request that times out cannot
be told from a reply that was lost, and a retry without an id creates the event
twice; with one, the retry lands on the same row.

**`start` and `end` say whether they are days or moments by their FORM.** A date
is a day, an instant is a moment, and `isAllDay` follows. Sending `isAllDay`
that disagrees with the form is a 400, as is mixing a date with an instant.

That is not a nicety. A client meaning "all day on the 11th" naturally sends
`2027-08-11T00:00:00Z`; resolved in a New York event's own zone that instant is
the evening of the **tenth**, and the event lands a day early with no error
anywhere. A date has no such reading.

### `PATCH /events/{id}` → `200 { "id", "scope", "result" }`

**`{id}` takes two forms**, and they mean different things:

```
PATCH /api/v1/events/019fd9…                the series
PATCH /api/v1/events/019fd9…:2027-03-16     one occurrence of it
```

The second is exactly the `id` `GET /events` returned. **This is new** — it was
previously refused, which meant the API handed out an identifier it would not
accept back.

#### `scope` is a BODY FIELD, and it is required

Not a query parameter. It sits alongside the fields being changed:

```json
{ "scope": "this", "location": "The pool" }
```

| `scope` | Means |
|---|---|
| `"this"` | Only this occurrence. It is taken out of the repeat and changed on its own |
| `"following"` | This one and every one after it. The old repeat ends the millisecond before |
| `"all"` | The whole series, shifted by however far this occurrence moved |

**Required on every `PATCH`** — including a bare series id, and including an
event that does not repeat. On a one-off all three mean the same thing and it is
still required, so the same client code keeps working when somebody makes the
event repeat. The server never guesses which occurrences you meant.

Omitting it is a 400 naming `scope`.

#### The reply, and the field carrying the new id

```json
{ "id": "019fdcd4-72d2-7f60-994f-2437297f7d03",
  "scope": "this",
  "result": "this one was taken out of the repeat and changed on its own" }
```

**`id` is the row to address next.** For `scope: "this"` and
`scope: "following"` the server **creates a row**, and `id` is that new row's
id — **not** the id you sent. A client that kept using the series id afterwards
would aim its next request at the wrong row.

| `scope` | `id` in the reply | `result` |
|---|---|---|
| `"this"` | the **new** standalone event | `this one was taken out of the repeat and changed on its own` |
| `"following"` | the **new** series | `the repeat was ended and a new one started from this occurrence` |
| `"all"` | the same series id you sent | `the whole series was changed` |

`result` is prose and may be reworded. **Branch on `scope`, not on `result`.**

After `"this"`, the original series gains an exception for that date and the new
row stands alone. After `"following"`, the original series ends the millisecond
before this occurrence and the new one carries the rule forward. In both cases
a subsequent `GET` returns occurrences from both rows, with different `eventId`s.

#### Failures particular to `PATCH`

| Case | Response |
|---|---|
| No `scope` | 400 naming `scope` |
| Body with only `scope` | 400 — a well-formed request that changes nothing |
| A date the series does not fall on | **400, not 404** — the event exists; that day is not one of its occurrences |
| An id with something other than a date after the colon | 400 |
| An event id that does not exist | 404. **A `PATCH` never inserts** |
| Somebody else changed the event between your request arriving and it being written | **409 `conflict`. Nothing was applied.** See below |

#### When somebody else got there first

```json
{ "error": "somebody else changed this a moment ago, so nothing was saved",
  "code": "conflict" }
```

**Status 409, `code: "conflict"`.** This is the *only* code you should retry on,
and it is deliberately not `bad_request`: that one means the request was wrong
and sending it again will fail the same way. Here the request was right.

Two facts, and both are contract rather than implementation:

1. **Nothing was applied — not part of it.** `scope: "this"` and
   `scope: "following"` each write two rows: the original series changes and a
   new row appears. If the first is refused, the second is never attempted. A
   detach that half-applied would leave the series without its exception while
   the standalone row existed, and that day would show **twice**.
2. **Retrying is the correct response**, and it is safe. The second attempt
   reads the event as it now stands, so it either succeeds or refuses again for
   the same reason. There is no state to clean up and no partial write to
   reconcile.

It means the household edited that event in the same moment. Retrying once
immediately is reasonable; retrying in a loop is not, because the other writer
may still be going.

**This is deliberately different from the ordinary conflict behaviour.** Two
devices editing one row through the sync protocol resolve by last-write-wins
and nobody is told, because the loser pulls the winner's version a moment
later. A request that answers once has nobody to pull anything, so it is told.

### `DELETE /events/{id}` → `200 { "id", "deleted": true }`

A tombstone, so the removal reaches every device.

**A repeating event is refused, 400.** The scope's own description promises that
it cannot delete a whole series, and a surface whose ids address series rows
cannot express "just this Tuesday" for a deletion.

### `POST /lists/{id}/items` → `201 { "id" }`

```json
{ "id": "optional", "text": "Milk", "quantity": "2", "notes": null,
  "isChecked": false, "due": "2027-09-03" | "2027-09-03T14:30:00.000Z" | null,
  "sectionId": null, "assignedMembershipId": null }
```

`due` takes the two forms of §6. A day is stored anchored at **9am** in the
caller's zone, not midnight — "due Thursday" means during Thursday, and a
midnight deadline is late the moment Thursday starts.

### `PATCH /lists/{id}/items/{itemId}` → `200 { "id" }`

Same fields, minus `id`. A body of `{}` is a 400.

Setting `isChecked` stamps the checked time with it — two halves of one fact.

**Both ids are checked, and against each other.** An item that exists but is on
a **different list** answers 404.

### `DELETE /lists/{id}/items/{itemId}` → `200 { "id", "deleted": true }`

A tombstone.

---

## 8. Two capabilities deliberately absent

Recorded with reasoning so they are not raised as oversights.

**Reordering list items.** There is no move endpoint and there will not be one.
Calendora's list sections are shops — PUBLIX, COSTCO — and a flat surface
dragging an item has two possible outcomes: it silently moves between shops, or
it snaps back. The information needed to choose is not in the request.
Reordering is the only capability whose absence costs nothing a user can
perceive: the list still shows every item and still checks off.

**Changing who is coming, per occurrence.** Attendance is readable and not
writable here yet. Ask if you need it.

---

## 9. Types

Every field, derived from the handlers rather than from intent.

| Field | Type | Notes |
|---|---|---|
| every id, `eventId`, `listId`, `sectionId`, `personId`, `avatarId`, `assignedMembershipId`, `attendeeIds[]` | `string` | Opaque. **Do not parse one** |
| `name`, `title`, `text` | `string` | Never null, never empty |
| `description`, `location`, `notes`, `quantity`, `icon`, `color`, `relationship`, `firstName`, `lastName` | `string \| null` | Null means not set |
| `kind` | `"person" \| "pet" \| "other"` | Members and people alike |
| `role` | `"owner" \| "admin" \| "member" \| "guest"` | |
| `type` (lists) | `"shopping" \| "todo" \| "packing" \| "checklist" \| "custom"` | |
| `isAllDay`, `repeats`, `isChecked`, `isArchived` | `boolean` | Never null |
| `importance` | `integer 1–10 \| null` | **Null is not zero and not "normal"** — nobody set one |
| `travelMinutes` | `integer ≥ 0 \| null` | Whole minutes |
| `start`, `end` | `string` | ISO 8601 instant, always — even when `isAllDay` |
| `timezone` | `string` | IANA name, the event's own |
| `birthday` | `string \| null` | `YYYY-MM-DD` **or** the year-less `--MM-DD`. Never an instant |
| `due` | `string \| null` | `YYYY-MM-DD` **or** an ISO instant — the form is the meaning |
| `position` | `string` | A fractional index. Compare as a string |
| `occurrenceKey` | `string` | `YYYY-MM-DD`, in the event's own zone |
| `scope` | `"this" \| "following" \| "all"` | Request only |

**On a read, every documented field is always present** — absent and null are
the same thing. On a **write** they are not: omitted means untouched, `null`
clears.

---

## 10. Fixtures

`fixtures/api-v1/` in the Calendora repository — **35 request/response pairs**,
generated by replaying real requests through the real handlers, covering every
endpoint above and every failure in §2 and §7.

Vendor that directory and test against it. Calendora replays every case on its
own build too, so a contract change breaks the build of whoever made it before
it reaches you.

The pairs for this release's change are `write-occurrence-this`,
`write-occurrence-following`, `error-scope-missing`,
`error-occurrence-not-on-that-day`, and `error-changed-underneath` — the
refusal in §7, generated against an event stamped in the future so it loses the
race every time it is regenerated.

`Bearer cal_<key>` and `<new-id>` are placeholders. **No fixture contains a
working credential**, and a server-minted id is redacted because it differs on
every generation — what is pinned is that the reply carries a *new* id, not its
value.

**The fingerprint at the top of this file covers that directory.** If it does
not match the fixtures you have, one of us is out of date — file a gap rather
than guessing which.

---

## 11. When something disagrees with this file

**File it in `docs/API-GAPS.md` rather than adapting to it.** Adapting silently
is how two ends drift apart with both builds green, and it is the failure this
document and the fixtures exist to prevent.

Six gaps have been filed this way and all six are closed. Two of them were
defects in Calendora that no internal test had caught.
