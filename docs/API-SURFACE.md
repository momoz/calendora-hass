<!-- Third-party API contract, extracted from momoz/calendora docs/05-API-SURFACE.md
     on 2026-08-07 (response bodies added same day). This is an EXTRACT, not the whole document — the internal doc contains
     the route inventory, sync-protocol internals and open security questions, none of which
     are part of the third-party contract and none of which are published here.
     Do not edit here; re-extract from source. -->

# Calendora — third-party API contract

This is the **entire** interface available to this integration. If something you need is not
in this document, it is not part of the contract — **file a gap**. Do not infer endpoints,
do not probe, do not use anything you find that is not written here.

**Status: `/api/v1` reads are live** (v2608.0134/0135). Writes are not built yet.

---

## 1. Base URL

```
https://calendora.app
```

Every `/api/v1/...` path is relative to it.

**There is no issuer field on a key and no discovery endpoint.** Hardcode this value as a
single constant. Do not offer it as a config field — a deployment model that does not exist
is not worth a form field every user has to skip past.

Self-hosted deployments would need their own host, and nothing supports that today: there is
no tenancy model and no way for a key to name its own origin. If it becomes real it will
appear here as a documented field first. **Never guess a host, and never derive one from a
key.**

## 2. Authentication

```
Authorization: Bearer cal_…
```

Keys are issued by the user in Calendora settings, scoped to **exactly one household**, and
revocable. Scopes are exact — **`calendar:write` does not imply `calendar:read`.** There is
no wildcard.

`calendar:read` · `calendar:write` · `lists:read` · `lists:write` · `household:read` ·
`presence:write`

A key is **not a member**. Changes made with it are attributed to the integration, never to
a person, and nothing it creates carries a member's colour or appears authored by them.

**There is no household parameter on any route**, because a key names exactly one household
and a client that could name a household could name somebody else's.

## 3. Errors

Every route answers the same shape:

```json
{ "error": "human sentence", "code": "unauthenticated" }
```

| `code` | Status | Means |
|---|---|---|
| `unauthenticated` | 401 | No key, unknown key, revoked, or expired — **deliberately indistinguishable** |
| `forbidden` | 403 | Valid key, missing scope. Names the scope, because that is actionable |
| `not_found` | 404 | No such thing — **or it belongs to another household** |
| `bad_request` | 400 | Says which parameter |
| `server_error` | 500 | Ours |

On **401**, raise `ConfigEntryAuthFailed` so Home Assistant starts a reauth flow. Never
retry a 401, never fail silently.

A resource from another household answers **404, not 403** — "that exists but is not yours"
is how ids get enumerated. Do not treat 404 as evidence an id is invalid.

## 4. The routes

```
GET /api/v1/household                    household:read
GET /api/v1/members                      household:read
GET /api/v1/people                       household:read
GET /api/v1/events?from=&to=&member=     calendar:read
GET /api/v1/lists                        lists:read
GET /api/v1/lists/{id}/items             lists:read
GET /api/v1/stream                       household:read    # SSE
```

### Events are occurrences

One object per occurrence, **not per rule**. The server expands recurrence; do not
re-derive it. `id` is `{eventId}:{occurrenceKey}` and is stable, and `eventId` groups them.

`attendeeIds` is resolved **per occurrence** — somebody who dropped out of one Tuesday is
absent from that Tuesday and present on the others.

A range longer than **400 days is rejected, not truncated**. A client that asked for five
years and got one would believe the calendar was empty after that.

### Dates are days, not instants

`from` and `to` are `YYYY-MM-DD`, resolved in the key owner's timezone. **An instant is
rejected**, because it would silently mean a different day depending on the zone it was
written in.

There is no household timezone — it is a per-person preference. `GET /api/v1/household`
reports `{ timezone: { value, source: "key-owner" } }`, named as whose it is rather than as
the household's.

All-day events and birthdays are **date-only** and must never become instants. Birthdays
stay strings, including the year-less `--MM-DD` form.

### `GET /api/v1/stream`

Server-sent events. `event: ready` on connect, `event: changed` when something in the
household changes, and a `: keep-alive` comment every 25 seconds.

**The payload is always `{}`.** It says *that* something changed, never what. On `changed`,
re-read whatever you care about. Drive `coordinator.async_set_updated_data()` from it and
keep a slow poll only as a fallback.

No household parameter — the key names one.

## 4a. Response bodies

Generated from the handlers, not from intent.

### `GET /api/v1/household`
```json
{ "household": { "id", "name", "description", "color" },
  "timezone":  { "value": "Europe/London", "source": "key-owner" } }
```
**`household.id` is what your config entry's `unique_id` should be.**

### `GET /api/v1/members`
```json
{ "members": [ { "id", "name", "kind", "color", "role", "avatarId", "personId" } ] }
```
`name` is **already resolved** — a display-name override beats the stored name server-side.
Do not re-derive it. `kind` is `person | pet | other`. `personId` links to `/people`, and is
reported from this side only. No email, no user id, no sign-in state — deliberately.

### `GET /api/v1/people`
```json
{ "people": [ { "id", "name", "firstName", "lastName", "kind",
                "relationship", "birthday", "color" } ] }
```
`birthday` is a **date string, never an instant**, and may be the year-less `--MM-DD` form.
`firstName` / `lastName` may be null — a pet has no surname.

### `GET /api/v1/events`
```json
{ "occurrences": [ {
    "id": "{eventId}:{occurrenceKey}", "eventId", "occurrenceKey",
    "title", "description", "location", "icon",
    "isAllDay": false,
    "start": "2026-08-07T09:00:00.000Z", "end": "…", "timezone": "Europe/London",
    "repeats": true, "importance", "travelMinutes",
    "attendeeIds": ["membershipId", …]
} ] }
```
Arrives sorted by `start`. `repeats` is a boolean — the RRULE is never exposed.

**`start` and `end` are always instants, including when `isAllDay` is true**, and `timezone`
is the event's own authored zone. Home Assistant requires an all-day `CalendarEvent` to carry
`date` objects and a timed one to carry `datetime` — both ends the same type. **Derive the
all-day date using the event's `timezone`, never the viewer's and never UTC.** Converting in
the wrong zone is exactly how a birthday moves a day.

**An occurrence with an empty `attendeeIds` belongs to the whole household** and is never
filtered out by `?member=`.

### `GET /api/v1/lists`
```json
{ "lists": [ { "id", "name", "description", "type", "color", "icon", "isArchived" } ] }
```

### `GET /api/v1/lists/{id}/items`
```json
{ "listId",
  "sections": [ { "id", "name", "position" } ],
  "items": [ { "id", "text", "quantity", "notes", "isChecked",
               "sectionId", "position", "dueAt", "assignedMembershipId" } ] }
```
Both arrays arrive **pre-sorted by `position`, which is a fractional index — a STRING.**
Compare it as a string; parsing it as a number gives an order nobody arranged. `sectionId` is
null for an item not in a section. `dueAt` is an ISO instant or null.


## 5. Unknown fields are rejected, not ignored

Send a field that is unknown or not writable and you get **400 naming the field**.

This differs from Calendora's internal protocol, which silently drops them. A silent drop is
invisible to a third party — it looks like a successful save and the user reports it against
the wrong project.

**Do not send fields speculatively.** Send what the endpoint documents.

## 6. What these routes deliberately do not carry

- **No email, user id or sign-in state** on `/members`
- **No `notes`** on `/people` — free text a family writes about a person has no integration
  use and is only ever read by accident once it is on a wire

If you find yourself wanting either, that is a gap, not an oversight to work around.

## 7. Not built yet

- **Writes** — events and list items. Coming; do not design around their absence permanently.
- **`GET /api/v1/events/{id}/leave-by`**
- **`POST /api/v1/presence`** — designed, and **blocked pending a product decision** on
  retention, syncability and per-member opt-out. It is the most sensitive data Calendora
  will ever hold. Building it before those are settled is a contract violation, not
  initiative.

## 8. Not available, and not coming

Do not ask for, infer, probe for, or build against:

- **The sync protocol** (`/api/sync/*`). First-party clients only. It is replication, not an
  API, and it is explicitly out of bounds.
- **Identity** — sessions, passkeys, invitation tokens.
- **Impersonation and support tooling.**
- **The personal Second Brain.** Private is a *retrieval* rule; a third-party API is a
  retrieval path. No scope grants it, now or ever.
- **The household activity log.** Server-only by design, never synced, and the
  household-level view is server-rendered HTML. If you need it, **file a gap. Do not scrape
  it.**
- **The ICS feed** (`/api/feeds/{token}`). Superseded by these routes and now a prohibited
  surface.

## 9. Security expectations of this integration

- The API key is a secret. Not in logs, not in diagnostics, not in issue templates, not in
  debug output. Redact it from any config-entry diagnostics you implement.
- The Home Assistant webhook id, if you register one, **is itself a credential** — generate
  it with `webhook.async_generate_id()` and never derive it from a household id, a user id,
  or anything else guessable.
- No real household data in screenshots, test fixtures, or example YAML in this public repo.
