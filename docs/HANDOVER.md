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
| What Home Assistant's todo platform needs | `docs/TODO-PLATFORM-REQUIREMENTS.md` |
| What shipped and when | `CHANGELOG.md` |
| Device-verified notification facts | the header comment in the blueprint |

## Where things stand

`0.4.2`, released 2026-08-07. Roughly 280 tests.

Working: household and per-member calendars, next-event and clash sensors,
to-do lists with write-back, calendar write-back with `scope`, per-member opt-in,
and the shop-arrival blueprint through its arrival send.

## Not built, each for a reason worth keeping

- **Batching** (design §5, "step 3"). Stopped deliberately: nobody knows yet
  whether a fifteen-item list across four buttons is a real problem. **Blocked
  anyway** on a device test — see below.
- **Android low-importance completion channel.** Unverified for want of a
  working Android device. Channel importance is frozen at creation, so a wrong
  guess is permanent on that phone. Design says: if it cannot be silent, do not
  send it on Android at all.
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
   ids that way per the design. If the platform does not return them, the tick
   path falls back to re-reading the list — which is correct while one message
   carries the whole list and **stops being correct the moment batching lands**.
   Test before step 3, not after.
2. **Can one automation write to two Android notification channels with
   different importance?** One test on any working Android phone closes it.

## The most valuable thing nobody has done

**A real shop.** The dwell length, whether the title reads at a glance on a
watch, and whether the count is right after a tap are all untested, and the
design is more exposed on them than on anything in the test suite.

## Working rhythm that earned its place

- **Verify, never recall.** Read the installed Home Assistant source rather than
  remembering its API; probe the live server rather than assuming. Anything that
  cannot be checked gets labelled unverified in the report *and* in the code.
- **Two verification layers beyond the unit tests**, and each has found bugs
  fixtures cannot: `scripts/verify_api.py` against the live API, and installing
  into a real Home Assistant before every release. The install check found a
  debounce bug no unit test could see.
- **A declined capability is a gap.** Choosing not to build something because
  the API cannot support it honestly is exactly as reportable as being blocked.
  Both produce the same silence upstream, and the silence is the failure.
- **Never declare a capability you cannot honour.** This was broken once, on
  member calendars, and a real household found it.
