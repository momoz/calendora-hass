# Calendora for Home Assistant

A Home Assistant integration for [Calendora](https://calendora.app) — the family
calendar, lists and assistant.

> **Status: early.** Your household calendar and your lists, live in Home
> Assistant — and you can tick things off and add to lists from here. Calendar
> events are still read-only; see [Known limits](#known-limits) for why. What has
> shipped so far is in `CHANGELOG.md`.

## Install

This is **not** in the HACS default store. Add it as a custom repository:

1. HACS → ⋮ → **Custom repositories**
2. Repository: `https://github.com/momoz/calendora-hass`
3. Category: **Integration**
4. Download, then **restart Home Assistant**
5. Settings → Devices & Services → **Add Integration** → Calendora

You will be asked for an **API key**. Create one in Calendora's settings. It
needs permission to **read** your household and calendar, and to **read and
write** your lists — the write permission is what lets you tick things off from
Home Assistant. Without it everything still appears; only editing fails.

> The key is a password. Don't paste it into a bug report, a screenshot, or a
> support chat. If it ever gets out, revoke it in Calendora and use
> **Reconfigure** here to enter a new one.

## What you get

**A calendar for the household, and one for each person in it.**

| Entity | What it shows |
|---|---|
| `calendar.<household>` | everything the household has on |
| `calendar.<household>_<name>` | one person's events, **plus everything shared** |
| `sensor.<household>_<name>_next_event` | when that person's next event starts |
| `todo.<household>_<list>` | one of your Calendora lists, editable |
| `binary_sensor.<household>_<name>_has_a_clash_today` | on when two of their events overlap today |

Pets get a calendar too, if they are members of your household in Calendora —
vet appointments are events like any other.

Use them like any other Home Assistant calendar. Put one on a dashboard, or
trigger an automation:

```yaml
automation:
  - triggers:
      - trigger: calendar
        entity_id: calendar.our_house_robin
        event: start
        offset: "-00:30:00"
    actions:
      - action: notify.mobile_app_robins_phone
        data:
          message: "Starting in half an hour: {{ trigger.calendar_event.summary }}"
```

The next-event sensors are timestamps, so a countdown card works with no
templating and an automation can compare them directly:

```yaml
      - condition: template
        value_template: >
          {{ 0 < (states('sensor.our_house_alex_next_event') | as_datetime
                  - now()).total_seconds() < 3600 }}
```

Repeating events arrive already expanded, so a weekly swimming lesson triggers
every week, an occurrence you skipped stays skipped, and one you moved shows at
its new time.

## The shopping-trip blueprint

Arrive at the shop, your list arrives on your phone, and tapping an item ticks
it off for everybody.

Settings → Automations → Blueprints → **Import blueprint**, and paste:

```
https://github.com/momoz/calendora-hass/blob/main/blueprints/automation/calendora/shopping_list_on_arrival.yaml
```

You will need a zone for the shop, the Companion app on the phone, and one of
your Calendora lists. Nothing is ticked automatically — the buttons are yours to
press.

**Three items by default.** iOS stops showing buttons past about three; Android
manages more. The rest are counted in the message rather than dropped silently.

## Before the shopping notification will look right on an iPhone

Two iOS behaviours will make this feature look broken when it isn't. Both are
worth checking before you decide it doesn't work.

**Turn on notification previews for Home Assistant.** By default iOS hides the
contents of a notification on a locked phone — you get the app name and nothing
else until you unlock. The shopping list is *entirely* content, so without this
it arrives as a blank card. On the phone: **Settings → Notifications → Home
Assistant → Show Previews → Always**.

**If you wear an Apple Watch, the notification goes there, not to your phone.**
With the phone locked and a paired watch nearby, iOS delivers to the watch and
the phone stays silent. That is normal, and it is the usual reason someone says
"it never arrived" while standing in the shop with it on their wrist.

## Known limits

Worth knowing before you build automations on this, rather than discovering
later as flakiness.

### Shared events appear on everybody's calendar

Deliberate, and it surprises people. In Calendora, an event with nobody
specifically attached belongs to the whole household — the bin collection, the
school holidays, a family trip. Those appear on **every** person's calendar as
well as the household one.

There is no "only Robin's own events" calendar, on purpose: the alternative
silently hides half of family life from each person's view. If you need to tell
them apart, a shared event shows `shared_with_household: true` on that person's
next-event sensor.

### Editing a repeating event asks which ones you mean

Change a repeating event and Home Assistant asks: just this one, or this and
everything after? Both do what they say — moving *this* Tuesday leaves the other
Tuesdays alone.

There is no third option for "including the ones that already happened", because
Home Assistant has no way to offer it and this integration will not guess.

**Deleting a repeating event is refused**, by Calendora rather than by us, and
the message says so and tells you to delete it in Calendora instead. Deleting a
one-off works normally.

### You cannot reorder list items

Deliberate. In Calendora, a list's sections are shops. Home Assistant's list is
flat, so dragging an item would either move it to a different shop without
telling you or snap back to where it was. Order comes from Calendora, already
sorted.

### Changes usually arrive in seconds, occasionally in half an hour

Home Assistant holds a live connection to Calendora, so a change made on
someone's phone normally shows up within seconds. If that connection drops it
reconnects on its own, waiting longer between attempts up to five minutes.
Underneath it all there is a slow check every 30 minutes as a safety net — so in
the worst case, where the live connection is broken and cannot re-establish, you
are looking at data up to half an hour old rather than at nothing.

If you are timing something tightly, build on the calendar trigger rather than
on polling a sensor.

### The next-event sensor skips what is already happening

`next_event` is the next event to **start**. An event already under way is not
upcoming, so it is not reported — otherwise a countdown card would count upward.
For "what is on right now", use the calendar entity, which is `on` during an
event.

### How much calendar is loaded

Roughly the last month and the next year are kept ready. Browse further out in
the UI and that window is fetched on demand, up to 400 days per request —
Calendora refuses a longer range outright rather than quietly returning part of
it and letting you believe the rest is empty.

### Removing someone from your household

Their calendar and sensor become **unavailable** rather than vanishing. If an
automation names an entity, a silent disappearance becomes a confusing error
much later. Delete them yourself from Settings → Devices & Services → Entities
once you are sure nothing depends on them.

### Updates arrive on HACS's schedule

HACS checks custom repositories for new versions roughly every **48 hours**, and
nothing changes until you apply one. Assume you may be a version behind for a
couple of days.

### Phone presence, if you automate on arrival

**iOS monitors a maximum of 20 geofences.** The Home Assistant Companion App
registers one for every zone you have defined. Past roughly twenty, iOS stops
monitoring the extras and arrival detection degrades — silently, with no error
anywhere. A family app tempts you into a lot of zones; keep the count small and
delete the ones you no longer use.

**There is no CarPlay or Bluetooth-connection sensor on iOS.** That one is
Android-only. Use `sensor.<device>_activity` == `Automotive` to tell that
somebody is driving.

**Background location is coarse.** iOS significant-location-change updates are
roughly every 500 metres or 15 minutes. Precise arrival timing needs a real zone
crossing, not a background fetch.

## If you replace your API key

Rotating a key is the right thing to do if it ever leaks, and it costs you
nothing here.

**Use Reconfigure, not remove-and-re-add.** Settings → Devices & Services →
Calendora → ⋮ → **Reconfigure**, then paste the new key. Your entities,
automations and history stay exactly as they are.

If Calendora stops accepting your key — because it was revoked, or it expired —
Home Assistant notices and asks you for a new one rather than going quietly
stale. It will never keep retrying a rejected key.

## Repository layout

| Path | What |
|---|---|
| `custom_components/calendora/` | the integration |
| `tests/` | the test suite, run by CI on every push |
| `AGENTS.md` | standing rules for anyone — human or agent — working here |
| `CHANGELOG.md` | what changed in each release |
| `docs/API-SURFACE.md` | the Calendora API surface this integration is allowed to use |

## Development

```bash
pip install -r requirements_test.txt
pytest
```

The suite runs against a real Home Assistant, pinned by
`requirements_test.txt`. CI runs it alongside `hassfest` and the HACS action;
all three must be green before a release is tagged.

### Before a release: install it into a real Home Assistant

Tests prove the integration agrees with the API. They cannot tell you it
**loads** — that the config flow completes, that entities appear, that a reload
does not leave a subscription behind. Do this every release; perform it, do not
reason about it.

With a container runtime:

```bash
docker run --rm -p 8123:8123 \
  -v "$PWD/custom_components/calendora:/config/custom_components/calendora:ro" \
  -v "$(mktemp -d):/config" ghcr.io/home-assistant/home-assistant:stable
```

Without one, a Home Assistant installed from PyPI works, but note it needs
`home-assistant-frontend` installed alongside it — **without the frontend
package Home Assistant aborts start-up before it sets up any config entry**,
which looks exactly like the integration failing to load and is not.

What to check, in order:

1. Settings → Devices & Services → Add Integration lists **Calendora**
2. Pasting a key completes the flow and creates an entry in the `loaded` state
3. Entities appear: one calendar per member plus the household, a next-event
   sensor and a clash sensor per member, and one to-do list per active list
4. Reload the entry three times. The entity count must be **identical** each
   time and nothing may go unavailable — a climbing count means a subscription
   is being leaked on unload
5. The log carries no errors from this integration

Use a throwaway Home Assistant, and never commit anything it produced.

### Checking the API against its documentation

```bash
python scripts/verify_api.py          # reads ~/.config/calendora-hass/api-key
```

The test suite proves this integration matches `docs/API-SURFACE.md`. Calendora's
own tests prove its server matches its implementation. **Nothing else tests the
document against the server** — so a wrong field name in the document means a
green build on both sides and a broken integration in production, invisible to
everyone. This script closes that gap, and found four real mismatches the first
time it ran.

Run it against your own household. It reports **structure only** — field names,
types, counts, and whether documented promises hold. It never prints an event
title, a person's name, a date, or your key, so its output is safe to paste into
a bug report. Put your key in `~/.config/calendora-hass/api-key` (or set
`CALENDORA_API_KEY`); keep it outside this repository.

It exits non-zero when the server and the document disagree. When that happens
the fix is to report it, **not** to change the integration to match what was
observed — that is how a document quietly stops being a contract.

> **The brand assets are vendored, not authored here.**
> `custom_components/calendora/brand/` holds Calendora's real mark, rendered from
> the icon the app itself ships. Treat it exactly like `docs/API-SURFACE.md` — do
> not redraw or "improve" it here. Changes are re-rendered from source and
> re-vendored by the maintainer.

## Licence

MIT. See `LICENSE`.
