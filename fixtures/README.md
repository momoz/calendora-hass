# `/api/v1` contract fixtures

**For:** `calendora-hass`, and anything else that talks to this API.
**Generated from:** the real route handlers, on every push.
**Contract:** `23-AGENT-CONTRACT.md` §10.

Request/response pairs for every documented endpoint and every documented
failure. Vendor this directory and test your client against it in CI.

**The point is that Calendora cannot change the interface without breaking your
build.** That is what a monorepo would give, and it is the closest substitute
available across two repositories.

---

## What a file contains

```json
{
  "describes": "one line on what this pair proves",
  "request":  { "method", "path", "headers", "body"? },
  "response": { "status", "body" }
}
```

`Bearer cal_<key>` is a placeholder. **No fixture contains a working
credential**, and a test in the Calendora repo fails if one ever does.

## What is pinned, and why you can rely on it

Ids are `fx-…` rather than UUIDv7, times are fixed rather than "now", and the
key owner's timezone is `Europe/London` — so a fixture is byte-stable and a
diff is readable. A diff nobody can read is a diff that gets regenerated
without being read.

Real ids are opaque UUIDv7. **Do not parse one.**

## The cases worth reading before you build

| File | What it pins |
|---|---|
| `events.json` | Occurrences, not rules. A weekly repeat expands; `fx-event-gym:2027-03-09` has an empty `attendeeIds` because Donna dropped out of that one Tuesday |
| `events-filtered-by-member.json` | `?member=` keeps occurrences with **nobody** on them — those belong to the whole household and are never filtered out by a person |
| `events-max-range.json` | Exactly 400 days is accepted, and both ends are inclusive (`GAP-005`) |
| `list-items.json` | `due` is `"2027-03-11"` for a DAY and an ISO instant for a moment. The form is the meaning (`GAP-002`) |
| `write-event-create-all-day.json` | Sending dates rather than instants makes it all-day; the end is exclusive |
| `write-event-patch.json` | Partial. Omitted is untouched, explicit `null` clears (`GAP-003`) |
| `error-occurrence-id.json` | PATCHing the `{eventId}:{key}` id `GET` handed you is **refused**, because editing the series would move every occurrence |
| `error-unknown-field.json` | An unknown field is a 400 that names it, never a silent drop |
| `error-bad-key.json` | Unknown, revoked and expired keys are **indistinguishable** — do not branch on which |
| `error-other-household.json` | Somebody else's list is **404, not 403** |

## The four error codes

Branch on `code`, never on the sentence. The sentences change; the codes do
not.

| `code` | Status | Means |
|---|---|---|
| `unauthenticated` | 401 | No key, unknown, revoked, or expired |
| `forbidden` | 403 | Valid key, missing scope. Names the scope, because re-issuing is actionable |
| `not_found` | 404 | No such thing — **or it belongs to another household** |
| `bad_request` | 400 | Your request is wrong. Says which part |
| `server_error` | 500 | Ours. File a gap |

## When a fixture changes

A change here means the interface changed. If it was not announced, that is a
bug on the Calendora side — **file it in `docs/API-GAPS.md` rather than adapting
to it.** Adapting silently is how the two ends drift apart with both builds
green, which is the failure this directory exists to prevent.
