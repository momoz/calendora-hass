# Mistakes — calendora-hass (Agent B)

One entry per mistake, added by the agent as it happens. Format and rule: `AGENTS.md`'s
"Mistakes ledger" section. What the mistake was, then the actual fix — nothing else.

---

## Backfilled 2026-08-09 to 2026-08-13

Written after the rule landed, from the days that produced them. Everything below shipped or
cost real time.

### Tested the shopping blueprint by reading it, never by running it

Every guard on the blueprint asserted things about the parsed YAML — which sends exist, which
are passive, which Android channels appear. All of it was true of a file Home Assistant refused
to load. `for: "{{ dwell_minutes }}"` on the arrival trigger was rejected at config validation,
so the automation was discarded with one line in the log. **Shipped in 0.4.0, 0.4.1 and 0.4.2** —
three releases of a feature that had never executed anywhere.

**The actual fix:** `tests/test_shop_blueprint_behaviour.py`, which builds the automation inside
Home Assistant, walks a person into a zone, waits out the dwell and taps the buttons. The
blueprint change was `for: !input dwell_minutes` with a duration selector. **Not** binding the
input to a variable first, which was the obvious repair and cannot work — a trigger cannot see
`variables:`, and `cv.positive_time_period` takes no template in any form.

### Wrote a Repairs check that could never pass, and a test that agreed with it

The "blueprint not imported" notice looked for
`blueprints/automation/calendora/shopping_list_on_arrival.yaml`. **Home Assistant files an
imported blueprint under the GitHub owner** — `momoz/` — so that folder never exists in a
user's config. The notice could not clear, for anyone, ever. Shipped in 0.4.3 and 0.4.4. The
test covering the "already imported" case installed the file **at the path the check was looking
in**, so check and test agreed with each other and neither agreed with Home Assistant.

**The actual fix:** ask Home Assistant which blueprints it has
(`automation.helpers.async_get_blueprints`) and match on the blueprint's own `source_url`.
Identity, not location — where a third party files something is its business, not ours to
predict.

### Read the shopping list from a state attribute that has never existed

`state_attr(todo_entity, 'items')` returns `None`. **No Home Assistant to-do entity publishes an
`items` attribute** — the state is a count, and items come from the `todo.get_items` action. So
`outstanding` was always empty, the arrival card was gated on it being non-empty, and **nothing
could ever send, in any version**. The tests hid it by publishing the state by hand with a
fabricated `items` attribute, inventing a shape the integration one directory away does not
produce.

**The actual fix:** call `todo.get_items` with a `response_variable`. And structurally — the
behaviour tests now stand up the **real integration** against mocked HTTP and drive the **real**
to-do entity, so a fixture cannot invent a state shape again. Ticks are asserted against the
outgoing API request rather than a service spy.

### Put a path where a URL was required

`deep_link` was `/lists/<listId>?mode=shopping` — the path the design writes — copied straight
into `clickAction`. The Companion app reads a relative path as a page inside **Home Assistant's**
frontend, which has none, so tapping the card gave a 404 from Home Assistant itself. It is the
interaction §4 calls the iPhone's primary action.

**The actual fix:** an absolute URL, with a test pinning its host to the integration's
`API_BASE_URL` so the two cannot drift. Nothing in this repo could have caught it — no test
opens a link — and it took a person tapping a real card.

### Changed two variables at once while diagnosing the deep link

Investigating why the card opened the app instead of the list, I compared a minimal payload
against the full card — but the minimal ones were tapped **warm** and the full ones **cold**. I
was one message from reporting "notifications with action buttons don't route on tap", which
would have sent the iOS agent hunting in the wrong place.

**The actual fix:** hold the app state constant and re-run. Mike force-quitting between taps is
what turned it into a controlled test; the payload was irrelevant and cold start was the whole
variable.

### Built four conclusions on an instrument that could only print one value

A diagnostic line read `url=NONE`, and I concluded the URL never reached the process, the auth
gate was innocent, `push-links.ts` was innocent, and the previous fix had aimed at the wrong
stage. **The line was written only on cold launch, so it had never been observed printing
anything else.** All four were wrong: the URL does arrive, and the gate was the overwriter, as
originally diagnosed.

**The actual fix:** prove the instrument first — a warm tap that must print a real URL — and
then **re-take** the cold measurement rather than grandfathering the old reading. I raised this
objection an hour after already violating it.

### Credited the wrong step for making HACS offer a release

Reported that `homeassistant.update_entity` made HACS surface 0.4.3. For 0.4.4 the entity did
not move until the HACS **repository record** was refreshed from GitHub first; `update_entity`
alone did nothing.

**The actual fix:** refresh the repository record, *then* the update entity. Recorded in
`docs/HANDOVER.md` as a correction rather than only as a fact, because the wrong version is the
intuitive one.

### Called a card closed on a warm success

Marked the deep-link gap verified when Mike tapped a card and it opened the list. He had the app
running. Cold — the normal case for this feature — it still failed.

**The actual fix:** none available in code; the fix was to stop reporting a pass from a single
observation whose conditions I had not established. Cold start is the case that matters and
"it worked" needs to say under what conditions.

### Over-engineered a test fixture and had to throw it away

Wrote a `_TickedItems` list subclass that lazily re-read an HTTP mock through overridden
`__eq__`, `__iter__` and `__len__`. It broke in three different ways and obscured what the tests
were asserting.

**The actual fix:** a plain fixture returning a function that lists the ticked ids, with
`.clear` attached. Readable, four lines, worked first time.

### Reported a UI bug that was not one

Told the iOS side the diagnostic line did not wrap and needed fixing. It wraps — I had read a
longer line and assumed a layout problem.

**The actual fix:** withdrew it in the next message rather than leaving it in the queue. A
retraction costs one paragraph; a commit spent on an imaginary bug costs a build.

---

## 2026-10-28

### Wrote a tags test that passed with the tags missing

The calendar-trigger test compared `{{ trigger.calendar_event.tags }}` to the
producer's tags joined — which is `""`, because every producer event has none.
An absent key renders as `""` too, so the test passed whether or not the field
reached the trigger at all. Caught only by reverting the field and watching the
test stay green.

**The actual fix:** a second rendered value, `{{ 'tags' in trigger.calendar_event }}`,
asserted `True`. With the field reverted the test now fails. Any test whose
expected value is "empty" needs a separate presence check, or it cannot tell
empty from missing.

### Assumed one time jump would fire a calendar trigger a day away

`freezer.move_to(start)` then one `async_fire_time_changed` fired nothing. Home
Assistant's calendar trigger re-reads the calendar every 15 minutes and
schedules the start from what it read, so a single 23-hour jump skips the read.

**The actual fix:** walk the clock forward in five-minute steps, firing each one.

### Reverted a mutation with `git checkout` and lost uncommitted work

To undo a deliberate one-line break in `calendar.py` I ran
`git checkout -- calendar.py`. The file also held uncommitted work, the new
`next_driven_occurrence`, and that went with it. The suite still imported
cleanly only because nothing had run yet. Re-adding it cost a few minutes. Done
on a file with more uncommitted work, it could have cost an afternoon.

**The actual fix:** copy the file aside before mutating it, and restore from the
copy (`cp f f.orig` … `mv f.orig f`). Never undo a test mutation with git while
the tree holds uncommitted work. Also: the `-k leave` filter on the first try
missed the test that mattered, so that mutation "passed". Choose the `-k`
expression from the test names, not from the feature name.

