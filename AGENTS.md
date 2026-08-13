# calendora-hass — standing rules

A Home Assistant custom integration for **Calendora**, distributed via HACS as a custom
repository (not the default store). Python, async, HA entity platforms.

The rule that outranks everything else here: **you may not work around a missing API.**
This integration is a third-party client of Calendora's public API and nothing else. If the
API cannot do something, that is a finding to report — never a thing to route around.

---

## Gaps are wider than endpoints

A gap is **anything you need from Calendora and do not have** — not just a missing route.
Brand assets, product copy, a token, an unmade decision. Raise it with the maintainer the
moment you notice, in the same breath as the work it blocks. The failure mode is not a badly
worded report; it is a need that arrives as a footnote at the end of a long one, or not at
all.

**Declining to build something is also a gap.** A capability you *chose* not to ship because
the API cannot support it honestly is exactly as reportable as one you were blocked on.
"I couldn't build this" and "I decided not to build this" produce the same silence upstream,
and the silence is the failure — from inside this repo an API limitation reads as a fixed
property of the world, so a closed-looking question never reaches the person who could
reopen it. If you wrote a paragraph explaining why an entity does not exist, that paragraph
is a gap entry. File it.

**A labelled placeholder is not a workaround.** When you are blind to something and say so
— visibly provisional artefact, disclosed everywhere it appears, replaced the moment the
real thing arrives — that is the correct behaviour, and its gap entry reads
`Workaround used: none`. A workaround is reaching a surface you were told not to reach, or
quietly shipping something that *looks* finished and is not. The distinction is the honesty,
not the fact that a stand-in existed.

---

## Your training data about Home Assistant is stale. Assume it.

HA moves fast and several things you "know" were removed or replaced in the last few
releases. These are verified as of **August 2026**. When this file and your instincts
disagree, this file wins — and when neither is certain, read
`https://developers.home-assistant.io` rather than guessing.

| You may think | Actually, as of 2026 |
|---|---|
| `person` has `entered_home` / `left_home` device triggers, `is_home` conditions | **Removed in 2026.5.** Use a `state` trigger `to: home`, or the zone-scoped purpose-specific triggers below |
| Presence triggers are person-scoped | **2026.7**: `zone.entered`, `zone.left`, `zone.occupancy_detected`, `zone.occupancy_cleared`, using `target:` + `options:` blocks with area/floor/label targeting |
| `ConversationEntity.async_process()` | Superseded by `_async_handle_message(user_input, chat_log)` |
| `OptionsFlowWithConfigEntry`, assigning `self.config_entry` | Deprecated. Subclass **`OptionsFlowWithReload`**; `self.config_entry` is provided |
| State lives in `hass.data[DOMAIN]` | Use **`entry.runtime_data`** |
| Icons come from the `home-assistant/brands` repo | **2026.3**: ship them in `custom_components/calendora/brand/`. Brands-repo PRs for custom integrations are auto-closed |
| Integrations can only add actions | **2026.7**: integrations register their own **triggers and conditions** via `trigger.py` / `condition.py` + `triggers.yaml` / `conditions.yaml` |
| "Add-ons" | Renamed **"Apps"** in 2026.2 (Supervisor only — HACS terminology is unchanged) |

---

## Platform facts that will cost you a day if you miss them

**Calendar update and delete have no service.** `calendar.create_event` and
`calendar.get_events` exist; **update and delete are WebSocket-only**. The HA calendar UI can
edit and delete, an automation cannot. Register our own `calendora.update_event` /
`calendora.delete_event` services for scripted use.

**Todo is the more capable platform.** Every mutation has a service (`todo.add_item`,
`todo.update_item`, `todo.remove_item`, `todo.get_items`, `todo.remove_completed_items`), and
it inherits `HassListAddItem` / `HassListCompleteItem` / `HassListRemoveItem` intents for
free — "add milk to the family shopping list" works through Assist with no code from us.
**Build todo before calendar write.**

**`async_get_events` must return expanded recurrence instances**, not master rules.

**`CalendarEvent.uid` is required** for any mutation to work. `start` and `end` must be the
same type — both `date` or both `datetime` — and datetimes must be tz-aware.

**`event` entities must declare every `event_type` up front.** Firing an undeclared type
raises `ValueError`.

**Declare feature flags honestly.** Service field filters and the UI key off them. Note
`SET_DUE_DATE_ON_ITEM` and `SET_DUE_DATETIME_ON_ITEM` are separate flags.

**iOS monitors a maximum of 20 geofences.** The Companion App registers one per HA zone;
past ~20 detection silently degrades. A family app wants many zones — document this
prominently rather than letting users discover it as flakiness.

**There is no CarPlay or Bluetooth-connection sensor on iOS** (Android only). "They're in the
car" is `sensor.<device>_activity` == `Automotive`.

**Background location is coarse** — significant-location-change is ~500 m and ≥15 minutes.
Precise arrival needs a real zone crossing.

**The webhook endpoint is unauthenticated — the id *is* the secret.** Generate it with
`webhook.async_generate_id()`. Never derive it from a household id, a user id, or anything
guessable. Prefer a cloudhook when the user has Nabu Casa.

---

## Architecture — non-negotiable

- `iot_class: cloud_push`, `integration_type: service`, `config_flow: true`
- **`DataUpdateCoordinator` in push mode** where possible — no `update_interval`; call
  `coordinator.async_set_updated_data()` from the stream/webhook handler. Poll only as a
  fallback.
- Entities subclass `CoordinatorEntity`; override `_handle_coordinator_update()`.
- **Every subscription's unsubscribe is registered** — `entry.async_on_unload(unsub)` for
  config-entry lifetime, `self.async_on_remove(unsub)` for entity lifetime. Leaking these is
  the classic custom-integration bug and it only shows up as a slow leak on someone else's
  box.
- Reauth (`async_step_reauth`) and reconfigure (`async_step_reconfigure`) are **required, not
  optional**. Raise `ConfigEntryAuthFailed` to trigger reauth; raise `UpdateFailed` for
  transient errors.
- One config entry per household. `async_set_unique_id` on the household id — never on a
  hostname or an IP.
- `PARALLEL_UPDATES` set in every platform module.
- **`entity_id`, never `device_id`**, anywhere a user-configurable entity is referenced.

## Blueprints we ship

- `source_url` **always set** — it is what lets users re-import updates in place.
- **Typed selectors, never free text** for an entity, device, area or target. A `text`
  selector for an entity lets a typo through and fails silently at runtime.
- `target` selector when the value flows into a service call's `target:`; `entity` selector
  when you need the id itself for a trigger or template.
- **`!input` is a YAML tag, not a template value.** Bind it to a `variables:` entry first,
  then use the variable. `{{ !input x }}` is the single most common blueprint bug.
- **Input keys are a public API.** Renaming or removing one breaks every automation built
  from it. Add new inputs with `default:` instead.
- Set `homeassistant.min_version` when using a version-gated feature.
- Presence blueprints use the **current** syntax from the table above, not the removed
  device triggers.

## HACS

- Layout: `custom_components/calendora/` — exactly one integration directory.
- `hacs.json` at the repo root; `manifest.json` needs `version` (HACS errors without it).
- **Ship GitHub releases.** Without them HACS installs from the default branch as a rolling
  install and update detection is unreliable. Tag name must equal `manifest.json`'s
  `version`.
- CI runs `home-assistant/actions/hassfest` and `hacs/action` on every PR. Both green before
  any release.
- **This repo is public.** Nothing from the private Calendora repo is copied here except
  deliberately vendored artefacts — currently `docs/API-SURFACE.md` and the brand assets in
  `custom_components/calendora/brand/`. Each records its origin in a header and is
  **re-copied from source, never edited here.** No credentials, no internal URLs, no schema
  dumps, no screenshots containing real family data.

## How to report

Reports are read by the product owner, not by another engineer. Format, every time:

1. **First line: one word — `GREEN`, `BLOCKED`, or `DECIDE`.**
   - `GREEN` — shipped, nothing needed.
   - `BLOCKED` — something is needed from the other repo. Include the request verbatim,
     ready to paste.
   - `DECIDE` — a product decision only the owner can make.
2. **Then three sentences at most**, in plain language. What changed, and what it means for
   the family using the app. No file paths, no symbol names, no version numbers.
3. **If `DECIDE`:** name the options, give each a one-line consequence, and say which you
   recommend and why. Never ask an open-ended question, and never hand over a technical
   trade-off without translating it into something a user would feel.
4. **Then a line of dashes.** Everything technical goes below it — file names, test output,
   reasoning. Assume nobody reads below the line, and that this is fine.

The same applies to a gap entry: its summary line must make sense to somebody who has never
opened this repository.

## Mistakes ledger — `MISTAKES.md`

**Mike's standing rule, 2026-08-13, for every agent in this project.** Keep `MISTAKES.md` at
this repo's root. Every time you make a mistake — a wrong assumption, code that shipped broken,
time spent down the wrong path, a fix that turned out not to be the fix — add an entry before
moving on. Two things per entry, nothing else:

- **What the mistake was.** Concrete: what you assumed or did, what actually happened, what it
  cost. Not a general lesson — the next reader needs the specific wrong turn, not a maxim they
  already agree with.
- **The actual fix.** What really solved it — not the first thing you tried if that one didn't
  work.

Read it before starting work in an area it already covers. The point is not paying for the same
mistake twice.

## Never block on CI

Push, then check **once**:

```bash
gh run list --limit 1 --json databaseId,headSha,status,conclusion
```

If it is `queued` or `in_progress`, **stop and report** — "pushed `<sha>`, CI running" is a
complete and correct status. Do not poll, do not `gh run watch`, do not sleep in a loop.
Waiting is not work. **Idle is fine** — inventing work to avoid waiting is worse.

When a run has finished and failed, the command that helps is:

```bash
gh run view <id> --log-failed
```

Read the failure, fix it, push again. `watch` blocks a whole turn to tell you what one
`list` would have.

## Writing

Comments explain **why**, not what. The Calendora repo's house style is a short reasoned
block above anything non-obvious, especially where a simpler approach was tried and failed —
match it. A comment that restates the code is noise; a comment that records the failure that
shaped it is the thing worth having.
