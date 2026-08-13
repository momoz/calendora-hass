# Changelog

All notable changes to this integration are recorded here. Versions match the
`version` field in `custom_components/calendora/manifest.json` and the GitHub tag
they were released under.

## 0.4.8 — 2026-08-13

### Added

- **"Run actions" now works as a dry run.** Home Assistant's *Run actions*
  button is the first thing anyone presses to ask whether an automation is set
  up correctly, and on this one it did nothing at all — the button skips the
  trigger, and every branch of the automation is keyed to one, so it fell
  straight through.

  It now sends the real shopping card, buttons and all, so you can check the
  whole thing from your armchair without driving anywhere. **And if it cannot
  send, it says why** — a notice appears telling you whether the person is not
  opted in or the list is empty, instead of the silence that made the last week
  hard to diagnose.

  Nothing is ticked off by a dry run, and a real trip is unaffected: the button
  only reaches this path because no trigger fired.

## 0.4.7 — 2026-08-13

**Every version before this one sent nothing.** The shopping notification read
your list in a way that always came back empty, so the card could never arrive
and a tap could never tick anything off. If you had driven to the shop you would
have got silence, and the natural conclusion would have been that the zone or the
dwell time was wrong.

### Fixed

- **The shopping list is actually read now.** The blueprint asked Home Assistant
  for the list's items in a way that has never worked — a to-do list does not
  publish its items that way, and the request quietly returned nothing rather
  than failing. It now fetches them properly.

  **Import the blueprint again** after updating, from the same address, and
  accept the overwrite. Nothing else you have set up changes.

## 0.4.6 — 2026-08-11

### Fixed

- **A shopping notification left over from an abandoned trip no longer ticks
  things off.** The card stays in your notification shade with its buttons
  working, so a tap the next morning would quietly tick items off *that day's*
  list. A trip now stops ninety minutes after the last thing you did on it, and
  a card older than that does nothing when tapped.

  A long shop is not cut off: ninety minutes is measured from your last tap, not
  from when you arrived, so a slow trip with steady ticking keeps working.

## 0.4.5 — 2026-08-10

### Fixed

- **The "blueprint not imported" notice would not go away, even once you had
  imported it.** Home Assistant files an imported blueprint under the name of
  whoever published it, and the check was looking under the integration's own
  name — a folder that never exists — so it could never find the blueprint and
  never stop asking. Found on a real installation, not in testing.

  It now recognises the blueprint by where it came from rather than by where
  Home Assistant chose to put it, so importing it clears the notice, wherever it
  landed.

## 0.4.4 — 2026-08-10

**0.4.3 could be installed and imported, and then could not be saved.** Filling
in the shopping blueprint and pressing save gave `Message malformed: value should
be a string`. This fixes that. Nothing else about 0.4.3 was wrong; you just could
not get past the form.

### Fixed

- **You can now actually create the shopping automation.** The field that asks
  which phone to notify was the wrong kind of field — it collected a whole action
  rather than naming a phone, and Home Assistant rejected the result when you
  pressed save.

  **It is now a device picker**, listing the phones running the Companion app.
  If you had got as far as filling the old form in, you will be asked for the
  phone again; nothing else you chose has changed.

## 0.4.3 — 2026-08-10

**Get this one.** Every previous version shipped a shopping blueprint that Home
Assistant refused to load. Nothing about it worked, anywhere.

Numbered `0.4.3` rather than `0.5.0` on Mike's call: the point of this release is
to put the fix where HACS can deliver it, and a patch number says that better
than a minor one, even though two features ride along with it.

### Fixed

- **The shopping automation never ran at all.** On 0.4.0, 0.4.1 and 0.4.2,
  arriving at the shop did nothing and there was no sign of why — Home Assistant
  rejected the automation when it loaded and wrote a single line about it to the
  log. Import the blueprint again from this version and it works.

  You will be asked for the dwell time as a duration now rather than a number of
  minutes; two minutes is still the default, and the setting means the same
  thing.
- **The "confirm when the list is done" switch is named correctly.** If you had
  turned it on, turn it on again after importing. Renaming it costs nothing today
  and would have broken working automations later.
- **"Got these" could tick nothing and say nothing.** On a phone that does not
  send the item list back with the button press, the tap failed silently instead
  of falling back to the items on the card. It now ticks what the card showed.

### Added
- **Calendora now tells you if the shopping blueprint was never set up.** A
  notice appears under Settings → System → Repairs with the address to paste.
  Installing this integration has never installed the blueprint — Home Assistant
  only knows about one once you import it by hand — and nothing said so, which is
  how a blueprint that could not load went unnoticed through three releases.
  Dismiss it if you do not want the shopping notification.
- **A tap now gets an answer.** Tick items off from the notification and a fresh
  card comes straight back with what is left, instead of the card simply
  disappearing and leaving you to open the app to find out whether the tap
  worked. Nothing to turn on — this is how the shopping notification works now.

  It arrives on the same card as before rather than stacking up a new one, so
  there is never more than one shopping notification waiting for you, and the
  buttons are in the same places every time.
- **The shop now ends with an answer.** Tick the last thing off your list and a
  single quiet card confirms it, instead of the list card simply vanishing and
  leaving you wondering whether the tap took. No buttons, no sound, and on a
  watch it does not raise the screen.

  **Off by default, and on purpose.** Turn it on in the blueprint's options if
  the phone is an iPhone. On Android this card cannot be sent silently — the
  quiet notification channel it would need has an importance that is fixed the
  first time the channel is created and cannot be corrected afterwards — so the
  card would arrive with a buzz to announce that the shop is over, which is
  worse than no card at all. The blueprint cannot tell which phone it is
  sending to, so the default is the one that is safe on either.
- **Shopping notifications now keep to their own thread on iPhone and Apple
  Watch**, so a trip does not interleave with the door sensor and the washing
  machine in your notification centre.

## 0.4.2 — 2026-08-07

### Added
- **Adding an event to one person's calendar now puts it on theirs.** Calendora
  can say who an event is for, so the add button is back on each person's
  calendar and the event lands where you chose. Adding on the household calendar
  still gives everybody the event, as before.

## 0.4.1 — 2026-08-07

### Fixed
- **Adding an event to one person's calendar no longer adds it for everybody.**
  Calendora has no way to say who a *new* event belongs to, so anything created
  from a person's calendar arrived with nobody on it — which means the whole
  household. Person calendars no longer offer an add button; create the event on
  the household calendar, or in Calendora where you can say who it is for.
  Editing and deleting from a person's calendar still work.

## 0.4.0 — 2026-08-07

**The shopping trip.** Arrive at a shop, and a couple of minutes later your
list is on your phone — and on your watch, which is where it is meant to be
read — with buttons to tick things off. Tapping one ticks it in Calendora, so
everyone else's list updates while you are still in the aisle.

> **None of this worked.** Found on 2026-08-09 and fixed in 0.4.3: the
> automation was rejected by Home Assistant when it loaded, in 0.4.0, 0.4.1 and
> 0.4.2 alike, so arriving at a shop did nothing at all. The claim below that the
> dwell was verified on a real Home Assistant was not true of this blueprint.
> Left standing rather than rewritten, because what was believed at the time is
> part of the record — but do not read the rest of this section as describing
> something that ran.

### Added
- **A blueprint for the shopping trip.** Import it once per person per shop:
  Settings → Automations → Blueprints → Import blueprint.
- **It waits before it fires.** Two minutes at the shop by default, so a red
  light outside, a petrol stop next door or a drop-off in the car park never
  set it off. Verified: arriving and leaving after thirty seconds never sends,
  and stepping back outside restarts the clock rather than firing early.
- **It knows when to say nothing.** An empty list, a list already ticked, a
  second trip to the same shop within a couple of hours, anything outside
  07:00–21:30, and anything at all after you tap **Not shopping** — which mutes
  that shop until midnight.
- **Each person opts in for themselves**, in the Calendora integration's
  options. Nobody is included by default, and the automation checks before it
  sends. A shopping list that follows you around is not a household decision.
- **A clash warning per person** — on when two of today's timed events overlap,
  naming both.
- Your Calendora lists now expose which list they are, so the notification can
  open the right one ready to tick.

### Known limitations
- **One message per trip, not batched by aisle.** A long list shows the first
  few and counts the rest. Splitting a big shop into a message per section is
  the next piece of work.
- **You cannot reorder list items**, deliberately — Calendora's sections are
  shops, and dragging in Home Assistant's flat list would move an item to a
  different shop without saying so.
- **On Android there is no quiet completion card.** Whether one automation can
  write to two notification channels is untested for want of a device, and a
  guess would be permanent on that phone.

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
