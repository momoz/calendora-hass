# Calendora for Home Assistant

A Home Assistant integration for [Calendora](https://calendora.app) — the family
calendar, lists and assistant.

> **Status: pre-release, and it does not do anything yet.** The integration
> installs, asks for your Calendora calendar feed URL, checks that the URL works,
> and then creates **no entities** — the calendar entities land in v0.1.0. See
> `CHANGELOG.md` for what has shipped so far.

## Install

This is **not** in the HACS default store. Add it as a custom repository:

1. HACS → ⋮ → **Custom repositories**
2. Repository: `https://github.com/momoz/calendora-hass`
3. Category: **Integration**
4. Download, then **restart Home Assistant**
5. Settings → Devices & Services → **Add Integration** → Calendora

You will be asked for your **calendar feed URL**. In Calendora, open Settings →
Calendar feed, turn the feed on, and copy the address it gives you.

> That URL is a password in disguise — anyone who has it can read your family's
> calendar without logging in. Don't paste it into a bug report, a screenshot, or
> a support chat. If it ever gets out, regenerate it in Calendora; the old one
> stops working immediately.

## Known limits

**iOS monitors a maximum of 20 geofences.** The Home Assistant Companion App
registers one for every zone you have defined. Past roughly twenty, iOS stops
monitoring the extras and arrival detection degrades — silently, with no error
anywhere. If you rely on zone-based automations, keep the zone count small and
delete ones you no longer use.

**There is no CarPlay or Bluetooth-connection sensor on iOS.** That sensor is
Android-only. Use `sensor.<device>_activity` == `Automotive` to detect driving.

**Background location is coarse.** iOS significant-location-change updates are
roughly every 500 metres or 15 minutes. Precise arrival timing needs a real zone
crossing, not a background fetch.

## If you regenerate your feed

Regenerating the calendar feed in Calendora is the right thing to do if the URL
ever leaks — but the old address stops working the instant you do it, and this
integration will go unavailable with a message saying exactly that.

**Use Reconfigure, not remove-and-re-add.** Settings → Devices & Services →
Calendora → ⋮ → **Reconfigure**, then paste the new URL. Your entities, automations
and history stay as they are. Removing the integration and adding it again would
create a second, separate entry, because from the outside a new feed URL looks
like a different household.

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

> **The brand assets are vendored, not authored here.**
> `custom_components/calendora/brand/` holds Calendora's real mark, rendered from
> the icon the app itself ships. Treat it exactly like `docs/API-SURFACE.md` — do
> not redraw or "improve" it here. Changes are re-rendered from source and
> re-vendored by the maintainer.

## Licence

MIT. See `LICENSE`.
