# Changelog

All notable changes to this integration are recorded here. Versions match the
`version` field in `custom_components/calendora/manifest.json` and the GitHub tag
they were released under.

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
