# Changelog

All notable changes to this integration are recorded here. Versions match the
`version` field in `custom_components/calendora/manifest.json` and the GitHub tag
they were released under.

## 0.3.0 — 2026-08-07

### Added
- **You can now edit the calendar from Home Assistant** — add an event, change
  one, or remove one. Changing a repeating event asks the question you would
  expect: just this one, or this and all the ones after it. Moving *this*
  Tuesday moves this Tuesday, and leaves the rest alone.
- **A clash warning for each person.** On when two of today's timed events
  overlap, and it names both, so a notification can say *"swimming overlaps the
  dentist"* rather than *"there's a clash"*. All-day events never count — a
  school holiday is not a commitment to be somewhere at ten.
- **A blueprint for the shopping trip.** Arrive at the shop and your list
  arrives on your phone with a button next to each item; tapping one ticks it
  off for everybody, while you are still in the aisle.

### Fixed
- **Something you just added is there immediately.** Adding an item then ticking
  it used to fail for a few seconds, because the list had not caught up yet.
- **If two people change the same thing at the same moment**, the change is
  quietly retried instead of failing.

## 0.2.0 — 2026-08-07

### Added
- **Your Calendora lists, and you can change them from Home Assistant.** Tick
  something off, add "milk", rename an item, set a due date, clear the completed
  ones. Changes go straight to Calendora and show up on everyone's phone.
- *"Add milk to the shopping list"* works through Assist with no setup from you,
  because Home Assistant's built-in list voice commands work on any to-do list.
- Due dates keep their meaning: "due Thursday" stays a day, "due Thursday at
  half two" stays a time.
- **A calendar for each member of your household**, alongside the household one.
  A person's calendar shows their own events *and* everything shared with the
  whole household — the family trip is on everybody's calendar, not just on the
  household one where nobody looks.
- **`sensor.<household>_<name>_next_event`** for each member: when their next
  event starts, as a timestamp, so a countdown card needs no templating.
- The README's known-limits section now covers the things worth knowing before
  you build automations, rather than after.

### Notes
- **Ticking an item changes only whether it is ticked.** Home Assistant does not
  know about an item's quantity, which shop it belongs to, or who it is assigned
  to — so the integration sends only the fields you actually changed and leaves
  everything else alone. Two people editing one list do not overwrite each other.
- **You cannot drag items into a different order**, and that is deliberate. In
  Calendora a list's sections are shops; dragging in Home Assistant's flat list
  would either move an item to a different shop without saying so, or snap back.
- Archived lists are not shown.
- Pets get a calendar and a sensor, if they are members in Calendora.
- There is no "leave by" sensor. The route that would give a real answer is not
  built, and deriving one from an event's travel time would produce a number
  that looks authoritative and is not.

## 0.1.0 — 2026-08-07

Moved to Calendora's API. **You now sign in with an API key instead of a calendar
feed URL**, and you get your household calendar as a real Home Assistant calendar.

### Added
- `calendar.<your household>` — every event, with repeating events already
  expanded into their individual occurrences by Calendora.
- Updates arrive **as they happen**. Home Assistant holds a live connection to
  Calendora, so a change made on your phone shows up in seconds rather than at
  the next poll. If that connection drops it reconnects itself, and there is a
  slow background check underneath as a safety net.
- If your key is revoked or expires, Home Assistant asks you for a new one
  instead of going quietly stale.
- You can swap your key at any time from the integration's **Reconfigure**
  option, keeping every entity and automation you have built.

### Changed
- **The calendar feed is gone.** 0.0.1 read a feed URL; that path has been
  removed entirely rather than deprecated. If you were on 0.0.1, Home Assistant
  will ask you for an API key — your old feed URL is discarded, not kept.

### Known limitations
- **Read-only.** Calendora's API has no write routes yet, so nothing here can
  create, edit or delete an event — and the integration does not claim it can,
  which is why Home Assistant hides the edit button.
- **One calendar, not one per person.** Per-member calendars need care that
  household-wide events are not silently dropped; that comes later.

## 0.0.1 — 2026-08-06

Phase 0: the scaffold. **This release creates no entities.** It exists so the
install path, the config flow and CI can be proved end to end before there is
anything to get wrong.

### Added
- Config flow that takes your Calendora calendar feed URL and checks it works
  before saving it.
- **Reconfigure** — if you regenerate your feed in Calendora, paste the new URL
  into the existing integration instead of removing and re-adding it. Removing
  and re-adding would have created a second, duplicate entry.
- Options flow for how often the feed is re-read (5–240 minutes, default 15).
- Calendar platform wired up and deliberately empty; entities arrive in 0.1.0.
- Test suite run by CI on every push, including a guard that no failure path can
  ever put your feed token into an error message or a log.

- Calendora's brand mark, vendored from the design repo — see
  `custom_components/calendora/brand/SOURCE.md`.

### Known limitations
- No calendar entities yet. That is Phase 1 (0.1.0).
