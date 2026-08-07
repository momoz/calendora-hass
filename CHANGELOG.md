# Changelog

All notable changes to this integration are recorded here. Versions match the
`version` field in `custom_components/calendora/manifest.json` and the GitHub tag
they were released under.

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
