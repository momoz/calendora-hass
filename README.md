# Calendora for Home Assistant

A Home Assistant integration for [Calendora](https://calendora.app) — the family
calendar, lists and assistant.

> **Status: early, and read-only.** You get your household calendar in Home
> Assistant, updating live, and nothing can change it from here. See
> `CHANGELOG.md` for what has shipped so far.

## Install

This is **not** in the HACS default store. Add it as a custom repository:

1. HACS → ⋮ → **Custom repositories**
2. Repository: `https://github.com/momoz/calendora-hass`
3. Category: **Integration**
4. Download, then **restart Home Assistant**
5. Settings → Devices & Services → **Add Integration** → Calendora

You will be asked for an **API key**. Create one in Calendora's settings — it
needs permission to read your household and your calendar.

> The key is a password. Don't paste it into a bug report, a screenshot, or a
> support chat. If it ever gets out, revoke it in Calendora and use
> **Reconfigure** here to enter a new one.

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

> **The brand assets are vendored, not authored here.**
> `custom_components/calendora/brand/` holds Calendora's real mark, rendered from
> the icon the app itself ships. Treat it exactly like `docs/API-SURFACE.md` — do
> not redraw or "improve" it here. Changes are re-rendered from source and
> re-vendored by the maintainer.

## Licence

MIT. See `LICENSE`.
