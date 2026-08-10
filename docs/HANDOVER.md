# Handover

For whoever picks this up next, including a future me with no memory of it.

**Read `AGENTS.md` first** — it is the standing rules and it outranks this file.
This one is only *where things stand*, which goes stale; that one is *how to
work here*, which does not.

---

## What this repository is

A Home Assistant integration for Calendora, distributed through HACS. It is also
a deliberate experiment: it is the **conformance test** for Calendora's
third-party API, built by a separate agent with no access to Calendora's source.
If this integration can do everything through the public API, the mandate that
there are no web-only write paths holds. That is why the rules about not working
around a missing endpoint are strict, and why a blocked feature with a filed gap
counts as success.

Two agents, two repositories, one interface. **The interface is
`docs/API-SURFACE.md` plus `fixtures/`, both vendored.** Anything told to you in
prose is a heads-up; the files are the contract. If they disagree, the files win
and it becomes a gap.

## Where to look

| For | Read |
|---|---|
| How to work here — the rules | `AGENTS.md` |
| What the API promises | `docs/API-SURFACE.md` (vendored, do not edit) |
| Request/response pairs to test against | `fixtures/` (vendored, do not edit) |
| The shop-arrival design | `docs/DESIGN-shop-arrival.md` (vendored; **carries a supersession note — read it**) |
| What was built of it, and what was found | `docs/SHOP-ARRIVAL-BUILD-LOG.md` — build status lives here, **not** in the vendored design |
| What Home Assistant's todo platform needs | `docs/TODO-PLATFORM-REQUIREMENTS.md` |
| What shipped and when | `CHANGELOG.md` |
| Device-verified notification facts | the header comment in the blueprint |

## Where things stand

**`0.4.3`, released 2026-08-10** — the release that makes the shop-arrival
blueprint work for the first time. 309 tests.

Working: household and per-member calendars, next-event and clash sensors,
to-do lists with write-back, calendar write-back with `scope`, per-member opt-in.

**The shop-arrival blueprint did not work in any released version and now does.**
Found 2026-08-09: `for: "{{ dwell_minutes }}"` on the arrival trigger meant Home
Assistant rejected the whole automation when it loaded, in 0.4.0, 0.4.1 and 0.4.2
alike. Anything you read anywhere describing how the shopping notification
behaves in a released version is describing something that never ran. Full
account in `docs/SHOP-ARRIVAL-BUILD-LOG.md`.

**And it had never been imported into any household** — verified against Mike's
live Home Assistant on 2026-08-10: 11 automation blueprints installed, none of
them Calendora's. A HACS integration does not register its own blueprint, so
there was no step at which anybody would have found out it was broken. Importing
it is a **first** import, not a re-import, and the integration now raises a
Repairs notice when it finds the blueprint absent.

Built since: the replacement card on your own tap, and the completion card when
the list empties.

## Not built, each for a reason worth keeping

- **Batching** (design §5, "step 3"). Stopped on a product question: whether a
  fifteen-item list across four buttons is a problem this household has. The
  *replacement loop* was split out of that step and shipped; what is open is
  §5's shape — a batch as a section of the shop rather than the next five.
- **Android low-importance completion channel.** Closed **by decision, not by
  test**: Android is out of scope, there is no completion card there, and an
  Android device turning up does not reopen it. On iOS the card is
  `interruption-level: passive`, which is per notification and needs no channel.
- **The trip's own stop conditions.** §6 names an 8-push cap and a 90-minute
  expiry and neither exists; §0 declares a `max_pushes` input that was never
  built. Card #151, waiting on Mike — the count needs state a blueprint cannot
  hold without asking for a helper entity.
- **`MOVE_TODO_ITEM`.** Never. Calendora's list sections are *shops*; dragging in
  Home Assistant's flat list would silently change where something is bought.
- **Presence.** Blocked on unmade product decisions, and the scope is not
  grantable. Do not unblock it from this side.
- **A `leave_by` sensor.** No route exists, and `travelMinutes` is a property of
  the event rather than a route from where the person actually is.
- **A `busy` binary sensor.** A calendar entity is already `on` during an event;
  a second entity saying the same thing is two sources for one truth.

## Blocked on a physical phone, not on effort

1. **Does per-action `action_data` come back on a tap?** The blueprint sends item
   ids that way. If the platform omits them the tick falls back to the slice the
   card showed — which is correct while one message carries the whole list and
   **stops being correct the moment batching lands**. Note that this fallback was
   itself broken until 2026-08-09: it raised instead of falling back, so a tap on
   such a phone ticked nothing and sent nothing. Fixed and tested; still
   unanswered on a device.
2. ~~Two Android notification channels from one automation.~~ **Closed by
   decision**, not by test. Android is out of scope; see above.

## The most valuable thing nobody has done

**A real shop.** The dwell length, whether the title reads at a glance on a
watch, and whether the count is right after a tap are all untested, and the
design is more exposed on them than on anything in the test suite.

**And until `0.4.3` it could not have been done.** The blueprint had never been
imported into the household, and the automation it builds could not have loaded
if it had been. A trip would have produced nothing — most likely read as the zone
or the dwell being wrong, or the design being wrong, rather than as a bug. Three
sessions treated this as "nobody has got round to it". It was not runnable.
Update in HACS, restart, then import the blueprint before going.

## Working rhythm that earned its place

- **Verify, never recall.** Read the installed Home Assistant source rather than
  remembering its API; probe the live server rather than assuming. Anything that
  cannot be checked gets labelled unverified in the report *and* in the code.
- **Three verification layers beyond the unit tests**, and each has found bugs
  fixtures cannot: `scripts/verify_api.py` against the live API; installing into
  a real Home Assistant before every release; and **executing rather than reading
  anything Home Assistant interprets**. The install check found a debounce bug no
  unit test could see. The third layer is newer and has the best hit rate so far
  — `tests/test_shop_blueprint_behaviour.py` found two shipped bugs on its first
  run, after every YAML-reading test had passed over both.
- **A structural test on a document proves it is the document you meant to
  write.** Only running it proves Home Assistant agrees. That distinction cost
  three releases.
- **A declined capability is a gap.** Choosing not to build something because
  the API cannot support it honestly is exactly as reportable as being blocked.
  Both produce the same silence upstream, and the silence is the failure.
- **Never declare a capability you cannot honour.** This was broken once, on
  member calendars, and a real household found it.
