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
| Every mistake this project made, in its own words | `MISTAKES.md` — read it before touching the shopping feature |
| What Home Assistant's todo platform needs | `docs/TODO-PLATFORM-REQUIREMENTS.md` |
| What shipped and when | `CHANGELOG.md` |
| Device-verified notification facts | the header comment in the blueprint |

## Where things stand

**`0.5.0`, released 2026-08-13.** 325 tests in the repository; 342 with the
uncommitted work described below. Eight releases in five days, and the sequence
is the point: 0.4.0–0.4.2 the blueprint would not load · 0.4.3 it loaded and
could not be saved · 0.4.4 fixed that and its "not imported" notice could never
be satisfied · 0.4.5 fixed that · **0.4.7 the shopping list had never actually
been read** (`state_attr(entity,'items')` does not exist; items come from
`todo.get_items`, so the card could never send) · 0.4.8 "Run actions" made a dry
run that says why it cannot send · 0.4.9 the card's deep link was a path and so
404'd inside Home Assistant · 0.5.0 the 8-push cap.

**Every one of those was found by a person or a live instance, never by CI** —
the gates were written afterwards, and each one holds. `MISTAKES.md` is the
honest ledger; read it before touching the shopping feature.

### Two operational facts that cost time to learn

- **An imported blueprint is a snapshot, and updating the integration does not
  refresh it.** HACS writes `custom_components/`; the blueprint HA uses is the
  copy it saved into `blueprints/automation/<github-owner>/` at import time.
  After any release that changes the blueprint, **import it again over the top**
  and accept the overwrite (`allow_override`, `blueprint/save`). Deleting first
  is unnecessary, and worse advice in general: Home Assistant refuses to delete a
  blueprint that an automation is using.
- **Making HACS offer a new release takes two steps, and the intuitive one alone
  does nothing.** `homeassistant.update_entity` on `update.calendora_update` did
  not move it; the HACS *repository record* has to be refreshed from GitHub first,
  and then the entity reflects it. I credited `update_entity` once and was wrong.

Working: household and per-member calendars, next-event and clash sensors,
to-do lists with write-back, calendar write-back with `scope`, per-member opt-in.

**The shop-arrival blueprint did not work in any released version and now does.**
Found 2026-08-09: `for: "{{ dwell_minutes }}"` on the arrival trigger meant Home
Assistant rejected the whole automation when it loaded, in 0.4.0, 0.4.1 and 0.4.2
alike. Anything you read anywhere describing how the shopping notification
behaves in a released version is describing something that never ran. Full
account in `docs/SHOP-ARRIVAL-BUILD-LOG.md`.

**And until 2026-08-10 it had never been imported into any household** —
verified against Mike's live Home Assistant that day: 11 automation blueprints
installed, none of them Calendora's. A HACS integration does not register its
own blueprint, so there was no step at which anybody would have found out it was
broken. **That is fixed and verified in both directions:** the integration raises
a Repairs notice when the blueprint is absent and clears it when it arrives, the
README carries the import step as a required one, and Mike's household has had
the blueprint imported since 2026-08-10 — three automations built from it as of
2026-08-22 (see the duplicate below).

**The permanent half remains permanent:** Home Assistant will still never
register a blueprint on an integration's behalf, so every new household needs a
person to paste a URL. Mitigable, never fixable from here.

Built since: the replacement card on your own tap, the completion card when the
list empties, a 90-minute trip expiry (`0.4.6`), and an 8-push cap kept in Home
Assistant's own `homeassistant.helpers.storage.Store` behind the response-only
`calendora.shop_push_budget` service (`0.5.0`). The counter survives restarts on
purpose: **a cap that resets when the hub reboots is a cap that silently does not
cap.**

## A real shop has now happened — three times

**This section used to say nobody had done one.** Read off Mike's live instance
on 2026-08-20 and 2026-08-22, from automation traces rather than from anybody's
recollection:

| When | Whose | What the trace shows |
|---|---|---|
| 2026-08-16 09:15 | Donna's instance | triggered on arrival; the trace has since expired, so what it did is unrecoverable |
| 2026-08-19 09:56 | Mike | zone entry `not_home` → `Publix-NorthDeLand`, real four-item list, `remaining: 0`, budget `{allowed, count 1, max 8}`, send executed with no error |
| 2026-08-21 09:00 | Mike | the same, with **nine** items outstanding: `showing` 5, **`remaining: 4`** — the "and N more" path on real data for the first time |

**So the zone trigger, the list read, the quiet-hours window, the push budget and
the send are all exercised on real hardware.** None of that is suite-only any
more.

**One precision on the dwell**, because it is the easiest thing here to overclaim:
both sends came *after* the wait rather than at the kerb, so the dwell does not
suppress a real arrival. Whether it suppresses a drive-past is **not** shown —
a correct non-send leaves no trace at all.

**Two things the same traces prove are still not true:**

- **No tap has ever reached Home Assistant.** A press on a card button is a run
  of the same automation. Across both of Mike's trips there is no such run, and
  the arrival traces are still stored, so nothing was cleared. **The replacement
  loop, the tick-through and the completion card remain suite-only.**
- **Whether the card arrived on the phone or the watch is not knowable from
  here.** Home Assistant executed the send without error; everything past that
  is the phone's word.

### The duplicate automation — open, and it distorts everything above

Mike's instance carries **three** automations built from this blueprint, and two
of them are byte-identical — same person, same zone, same list, same phone:

```
1786387458467  "… at the shop - mike"     person.mike_olsen · zone.publix_northdeland · todo.shopping_list
1786629794737  "… at the shop"            identical inputs
```

Both fired on 2026-08-19 and again on 2026-08-21, milliseconds apart, so **each
arrival sent two identical cards**. They also share one trip key
(`calendora_shop_mike_olsen`), so they spend the 8-push budget twice per send —
an 8-push cap behaving as a 4-push cap.

**This is a household configuration, not a bug in this repository**, and it was
flagged to Mike on 2026-08-20. **Still present as of 2026-08-22 — treat any
reading taken from his instance as doubled until it is gone.** Deleting either
one fixes it.

## Not built, each for a reason worth keeping

- **Batching** (design §5, "step 3"). Stopped on a product question: whether a
  fifteen-item list across four buttons is a problem this household has. The
  *replacement loop* was split out of that step and shipped; what is open is
  §5's shape — a batch as a section of the shop rather than the next five.
- **Android low-importance completion channel.** Closed **by decision, not by
  test**: Android is out of scope, there is no completion card there, and an
  Android device turning up does not reopen it. On iOS the card is
  `interruption-level: passive`, which is per notification and needs no channel.
- ~~**The trip's own stop conditions.**~~ **Both built** — the 90-minute expiry
  in `0.4.6` (it needed no stored state: `this.attributes.last_triggered` holds
  the previous run's time) and the 8-push cap in `0.5.0`, with `max_pushes` now
  a real input, 3–20, default 8. Mike settled where the count lives: *"I think HA
  should store itself."* Not a household `counter` helper, and **not Calendora's
  database** — the pushes start in Home Assistant and never touch Calendora, so
  that route meant a new public API surface maintained forever for a counter.
- **`MOVE_TODO_ITEM`.** Never. Calendora's list sections are *shops*; dragging in
  Home Assistant's flat list would silently change where something is bought.
- **Presence.** Blocked on unmade product decisions, and the scope is not
  grantable. Do not unblock it from this side.
- **A `leave_by` sensor.** No route exists, and `travelMinutes` is a property of
  the event rather than a route from where the person actually is.
- **A `busy` binary sensor.** A calendar entity is already `on` during an event;
  a second entity saying the same thing is two sources for one truth.

## Blocked on a physical phone, not on effort

0. **The cold deep link — card #197, and it is the iOS app's, not this
   repository's.** Tapping the shopping card on a **cold-started** iPhone opens
   Calendora on its default screen instead of the list; warm has always worked.
   The readings live on the card; `v2608.0155` is the last trustworthy one and
   showed the URL arriving fully formed and the app landing on `/` anyway. What
   is pending is a **bisect build** from the iOS side, not another fix. **It does
   not block a shop**: the tick buttons go through Home Assistant and never touch
   the app, so what is lost is only the tap-through to the full list.

1. **Does per-action `action_data` come back on a tap?** The blueprint sends item
   ids that way. If the platform omits them the tick falls back to the slice the
   card showed — which is correct while one message carries the whole list and
   **stops being correct the moment batching lands**. Note that this fallback was
   itself broken until 2026-08-09: it raised instead of falling back, so a tap on
   such a phone ticked nothing and sent nothing. Fixed and tested; still
   unanswered on a device.
2. ~~Two Android notification channels from one automation.~~ **Closed by
   decision**, not by test. Android is out of scope; see above.

## What is still worth a person's hands

**One button press in an aisle.** Tick something on the card and see whether a
replacement comes back with a smaller number. Everything around it is now proved
on real hardware; this is the piece that is not. The watch glance and quantities
are the other two, and all three are one trip's work.

**Why this sat for so long, which is the part worth keeping:** it read as
"nobody has got round to it" for days, and it was **not runnable**. Until
2026-08-09 the automation could not load; until 2026-08-10 the blueprint had
never been imported into any household; and until `0.4.7` the list was never
actually read, so the card could not send at all. A trip taken in that window
would have produced silence, and silence reads as a wrong zone or a wrong dwell
— the wrong place to look. **Before any trip: update in HACS, restart, and
import the blueprint again over the top.**

## Uncommitted work sitting in the tree

**Card #198 — `verify the artifact, not the commit`.** Built 2026-08-14, proven
against the published `0.5.0` archive, and **deliberately not committed**: Mike
stood the session down before it went in, and it has been waiting on his word
since. Four files:

| File | What it is |
|---|---|
| `scripts/verify_release_artifact.py` | fetches the published release and checks it: the tag has a release at all, the archive unpacks, `manifest.json` equals the tag, `hacs.json` matches the real layout, the blueprint is inside, and the `IMPORT_URL` compiled into **the downloaded copy** still resolves and serves a blueprint |
| `.github/workflows/release-artifact.yml` | runs it on publication, on demand, and weekly — then runs the archive's **own** tests from inside the unpacked tree |
| `tests/test_release_artifact.py` | 17 tests, each handing a check a broken tree, because a control that only runs on a real release is one nobody has watched fail |
| `docs/SHOP-ARRIVAL-BUILD-LOG.md` | the entry describing all of it |

**Why it exists:** every other check in this repository reads the working tree.
If a tag shipped with the blueprint missing, with `manifest.json` naming a
different version, or with the Repairs notice pointing at a file renamed on
`main`, **nothing here would look any different.** It is the third of the three
mitigations `#169` named, and the only one that had never been built.

**If you are picking this up:** `git status` shows them as untracked. They add no
shipped code — the integration is untouched — so committing them changes only
what happens after a tag.

## Working rhythm that earned its place

- **Verify, never recall.** Read the installed Home Assistant source rather than
  remembering its API; probe the live server rather than assuming. Anything that
  cannot be checked gets labelled unverified in the report *and* in the code.
- **The suite runs locally now.** `.venv` in the repository root (gitignored,
  built with the system Python 3.14 and `requirements_test.txt`);
  `.venv/bin/pytest -q` is the whole suite in about 25 seconds. Earlier sessions
  quoted CI numbers because nothing local could run pytest at all — if `.venv` is
  missing, rebuild it rather than reporting someone else's green tick.
- **Read the automation trace, not the entity.** `last_triggered` says a run
  happened; the trace says what the run *did* — which conditions passed, what
  the list actually contained, what the push budget answered. Every real fact
  about the three shop trips above came out of traces, and the absence of a
  tap-triggered run is what proves nobody has tapped.
- **Three verification layers beyond the unit tests**, and each has found bugs
  fixtures cannot: `scripts/verify_api.py` against the live API; installing into
  a real Home Assistant before every release; and **executing rather than reading
  anything Home Assistant interprets**. The install check found a debounce bug no
  unit test could see. The third layer is newer and has the best hit rate so far
  — `tests/test_shop_blueprint_behaviour.py` found two shipped bugs on its first
  run, after every YAML-reading test had passed over both. **A fourth is written
  and uncommitted** (`scripts/verify_release_artifact.py`, above): it checks the
  released artifact rather than the commit, which is the one layer none of the
  other three cover.
- **A structural test on a document proves it is the document you meant to
  write.** Only running it proves Home Assistant agrees. That distinction cost
  three releases.
- **A declined capability is a gap.** Choosing not to build something because
  the API cannot support it honestly is exactly as reportable as being blocked.
  Both produce the same silence upstream, and the silence is the failure.
- **Never declare a capability you cannot honour.** This was broken once, on
  member calendars, and a real household found it.
