# Shop arrival — build log

What was built, what was found, and what is still not true. This file belongs to
this repository.

**Why it exists.** Build status and specification have different lifetimes and
belong in different files. `docs/DESIGN-shop-arrival.md` says what the shop
notification should be; this says what was built, what was found, and what is
still not true.

It began for a sharper reason: that file arrived as a vendored copy whose first
line said *"do not edit here; re-copy from the design source"*, sessions of this
agent were recording build status inside it anyway, and a vendored copy people
amend stops being a vendored copy. **That is resolved.** The named source
(`HomeAssistantNotify v2.dc.html`) exists nowhere reachable — checked across
`calendora/docs/design/` and every repository under `~/dev` on 2026-08-09 — which
made the instruction unenforceable and the document permanently uncorrectable.
Mike relabelled it on 2026-08-10: it is this repository's own document now, and
its header says so.

The split stands regardless, for the reason in the first paragraph rather than
because anything forbids editing the design.

---

## 2026-08-13 — the push cap, the other half of #151

§6 caps a trip at eight pushes and §0 declares a `max_pushes` input, 3–20,
default 8. **Neither had ever been built**, and the input was a promise the
blueprint's form never made.

**Deferred earlier the same day, and the deferral was right at the time:** every
send after the arrival card answers a tap, so a cap would have bounded a person's
own thumb. It is built now because Mike settled the storage question — *"I think
HA should store itself"* — and a decision about where a counter lives is not one
you make for a counter you do not want.

**Where it lives, and why not the two alternatives.** `homeassistant.helpers.
storage.Store`, in the integration, behind a response-only service the blueprint
calls before each send.

- **Not a script variable**, because a blueprint has nowhere to keep a number
  between runs.
- **Not a household `counter` helper**, because that is setup work pushed onto
  every family for a backstop most trips never reach.
- **Not Calendora's database** — the first answer, and the expensive one. The
  pushes originate in Home Assistant and never touch Calendora, which has no
  other reason to know how many notifications a blueprint sent. That route meant
  a new public `/api/v1` surface, maintained forever, for a counter.

**The test that is the requirement rather than arithmetic** is
`test_the_count_survives_a_restart`. A restart-scoped counter reads as enforced
and is not — Home Assistant restarts on updates, config reloads and power cuts —
which is the silent-success shape inside a control whose only job is to be a
limit. Mutation-tested by dropping the save: it fails.

**And the blueprint has to ask.** A counter that counts while nothing consults it
is the same defect wearing the opposite sign, so
`test_a_trip_goes_quiet_once_it_has_spent_its_budget` drives a real trip through
nine taps and asserts the ninth card never arrives. Mutation-tested by removing
`budget.allowed` from the send condition.

**Silence, not an apology.** §6: *"The eighth is a hard stop with no explanatory
ninth."* The refusal is logged for whoever goes looking and nothing reaches the
phone. Ticking still works — going quiet must not mean going dead.

## 2026-08-13 — the primary action opened a 404

Mike tapped the first card this feature has ever sent, and got **404: Not
Found**.

`deep_link` was `/lists/<listId>?mode=shopping` — **the path §4 writes**, copied
verbatim into `clickAction`. The Companion app reads a relative path as a
navigation target inside **Home Assistant's own frontend**, which has no
`/lists/…`. Fixed by making it absolute against the same host as the
integration's `API_BASE_URL`, with a test asserting the two cannot drift.

**§4 calls the deep link "the iPhone's primary action"** — the buttons sit behind
an expand gesture unreliable enough that tapping the card *is* the designed path.
So the single interaction the design leans on hardest was broken by copying a
spec written as a path into a field that needs a URL.

**Nothing in this repository could have caught it. No test opens a link.** It
took a person tapping a real card, which is the same lesson as the four before
it: the gates catch regressions, and the first proof that something works at all
still comes from a person using it.

## 2026-08-13 — the diagnostic that could never answer

Mike updated everything, pressed **Run actions**, and got nothing. He expected it
to simulate the trigger. It does not.

`automation.trigger` passes `trigger: {platform: None}` — **defined, but with no
`id`**. Every branch of the `choose` opens with `condition: trigger`, so all of
them are false and the whole thing falls through. `skip_condition` does not help:
it skips the automation's top-level `conditions:`, and these live inside the
actions.

**So the one tool a person reaches for to ask "is this working?" was the one
tool that could never answer** — across four releases in which the answer was
"no" for four different reasons.

`default:` now makes the button a dry run: it sends the **real** card via the
same `&shop_card` anchor, so a correctly configured phone gets the real thing
rather than a simplified stand-in that proves only that the stand-in works. If it
cannot send, it raises a persistent notification naming the reason — not opted
in, or nothing outstanding.

**Guarded on `trigger.id is not defined`**, which no real trigger can satisfy.
That guard is the whole safety of a `default:` branch, and mutation-testing
proves it: without it, another household's tap and an expired card both send a
card.

Quiet hours and the revisit window are deliberately **not** applied to a dry
run — they are rules about a trip, and a diagnostic that stays silent because it
is 22:15, or because you pressed the button twice, is the problem this exists to
solve.

## 2026-08-13 — the list was never read

**Found while answering "how do I test this", which is the only reason it was
found at all.**

The blueprint read the shopping list as `state_attr(list_entity, 'items')`.
**No Home Assistant to-do entity publishes an `items` attribute.** The state is a
count; the attributes are whatever the integration adds — here `list_id`,
`list_type`, `section_count`. Items come from the **`todo.get_items` action with
a response variable**, and nothing else.

So `outstanding` was always `[]`. The arrival card is gated on
`outstanding | count > 0`, so **it could never send**; a tap ticked nothing
because `ticking` fell back to an empty slice. **Every release that has ever
contained this blueprint has been silent**, including the four shipped in the two
days spent fixing everything else about it.

Verified against the live instance before and after: `todo.shopping_list` carries
no `items` attribute, and `todo.get_items` on the same entity returns two real
items with `uid`, `summary` and `status`. Fixed by calling the action and reading
`todo_result[list_entity]['items']`.

### The third instance of the same shape in three days

The tests published the to-do state by hand — `hass.states.async_set(entity, n,
{"items": [...]})` — **inventing an attribute the integration one directory away
does not produce.** The blueprint read it, the fixture supplied it, and the two
agreed with each other.

- `0.4.4`: the author supplied the wrong input **value** (a service-name string
  where the selector yields an action sequence).
- `0.4.5`: the wrong input **location** (a blueprint path Home Assistant never
  uses).
- `0.4.7`: the wrong input **shape** — and this one is the worst of the three,
  because the correct shape was available in this repository the whole time. The
  integration's own `extra_state_attributes` says exactly what it publishes.

**The repair is structural rather than another assertion.** The behaviour tests
now stand up the **real Calendora integration** against mocked HTTP and drive the
**real to-do entity**, so a fixture can no longer invent a state shape the
integration does not produce. Ticks are asserted against the outgoing API request
rather than a service spy — `todo.update_item` now reaches the real entity, and a
spy in front of it would prove only that something was asked for.

Mutation-tested: restoring the attribute read fails all ten behaviour tests.

## 2026-08-11 — the trip can stop itself

§6's stop conditions, filed as `#151`. **The expiry is built. The push cap is
not, and the reason is worth more than the feature would have been.**

### The severity was overstated, and checking said so

`#151` was promoted on the grounds that two live automations now exist, so an
uncapped push loop is reachable on two real phones. **It is not.** Parsing the
shipped blueprint gives two triggers, `arrived` and `tapped`, and every send sits
under one of them: one push on arrival, and everything after it inside a branch
that only runs when the shopper taps. **Nothing can push uncaused.** The rows in
§6's matrix that would — somebody adding an item while you are in the zone,
somebody else's tick emptying your batch — are unbuilt.

So a cap of eight would today bound a person's own thumb. It is filed, not
abandoned, and it should land **with** the uncaused sends, because that is the
point at which it governs anything.

### The expiry, and what made it cheap

A card left in the shade after an abandoned trip keeps its buttons. Tap *Got
these* the next morning and it ticks **tomorrow's list** off yesterday's card,
silently. That is the real defect in the missing stop condition, and it is now
closed.

**It needed no stored state, which is why it could ship tonight.**
`this.attributes.last_triggered` is the time of the *previous* run:
`Script.async_run` stamps it when the action script starts, and `this` is
captured before that. So a tap branch can ask how long ago this trip last did
anything.

**That fact was load-bearing already and had never been tested.** The revisit
window — "nothing within two hours at this shop" — rests on exactly the same
behaviour, in shipped code, unverified. A probe confirmed it: first arrival
sends, a second arrival twenty minutes later does not.

**The deviation, stated rather than absorbed:** §6 says 90 minutes from arrival;
this measures 90 minutes from the last trip activity. Both tests are in
`test_shop_blueprint_behaviour.py` — a card tapped 91 minutes after the trip went
quiet ticks nothing, and a slow shop with a tap every 50 minutes keeps working
past the two-hour mark. Frozen clock, never a real wait.

### A correction to the tests, which were testing an impossible state

Every tap test fired a tap with no preceding arrival — a state no household can
be in. They passed because nothing had ever cared. The expiry cares immediately:
it refuses a tap when the automation has never run. So the tap tests now walk the
person into the zone and wait out the dwell first, which is what a real tap is
always preceded by.

## 2026-08-10 — the notice that could never be satisfied

`0.4.3` added a Repairs notice for a household that has the integration and not
the blueprint. **It rendered correctly on a live instance — the first proof of
that, and it had been the release's one tests-only claim — and it was wrong.**

Home Assistant files an imported blueprint under the **GitHub owner**:
`blueprints/automation/momoz/shopping_list_on_arrival.yaml`. The check looked
under `blueprints/automation/calendora/`, reasoning from this repository's own
folder layout. That folder never exists in a user's config, so the check could
**never pass**: a household that had done exactly what the notice asked was told
to do it again, forever.

Shipped in `0.4.3` and `0.4.4`. Fixed in `0.4.5` by asking Home Assistant which
blueprints it has and matching on the blueprint's own `source_url`, which points
at this repository — identity rather than location. Where Home Assistant files
things is its business and not this integration's to predict.

**Why the test suite said it was fine.** `test_blueprint_check.py` covered both
states, including "already imported" — by installing the blueprint **at the path
the check was looking in**. The author supplied the location as well as the
value, so the two agreed with each other and neither agreed with Home Assistant.
That is the judge-fed-by-the-defendant shape again, wearing a different coat: the
first time it was the input *value*, this time the input *location*.

Caught by reading a live instance. The tests now install at the real path and at
an unrelated one, and mutation-testing the old path-matching logic back in fails
three of them.

## 2026-08-10 — it loaded and could not be configured

`0.4.3` fixed loading. A real household then filled the form in, pressed save,
and Home Assistant answered:

```
Message malformed: value should be a string for dictionary value
  @ data['actions'][1]['choose'][0]['sequence'][0]['action']
```

**Reproduced locally with an exact string match** on the same path and wording,
by substituting three shapes and validating each through Home Assistant's
automation schema: an action-sequence list fails, a bare dict fails, a plain
service-name string passes.

**The mechanism, and it is worse than a type mismatch.** `notify_service` used
`selector: action:`. In `homeassistant/helpers/selector.py`, `ActionSelector` is
*"Selector of an action sequence (script syntax)"* and its validator is
`return data` — **it validates nothing**, so it accepts any shape and hands it
straight through. The first thing that objects is the automation schema, at save
time, in front of the user. Do not assume a selector checks its own output.

**And no selector yields a service name.** All 43 registered types were listed —
`action addon app area … target template text theme time trigger` — and none is
service-shaped. So this was never fixable by swapping selectors: `text` produces
the right type and is forbidden, rightly, because a mistyped service fails
silently at send time.

**The fix is Home Assistant's own**, from `notify_leaving_zone.yaml`: a `device`
selector filtered to `integration: mobile_app`, invoked as a **device action**
(`domain: mobile_app`, `type: notify`, `device_id:`). `mobile_app/device_action.py`
accepts `message`, optional `title` and optional `data` (`cv.template_complex`),
and resolves the notify service from the device's webhook — so the rich payload
survives and there is no name to mistype. Applied at all three call sites; the
`&shop_card` anchor covers only one of them, and the other two were changed
explicitly rather than assumed covered.

### The gate that did not exist, and why the one that did was useless

A substitution test **already existed** —
`test_shop_blueprint.py::test_the_anchor_survives_home_assistant_s_own_loader`,
written the day before — and it passed throughout. It passed because the values
were chosen by the person who wrote the code: `notify_service:
"notify.mobile_app_test_iphone"`, a plain string, the shape the code wants.

**A judge fed by the defendant.** The author is the one participant guaranteed to
supply inputs the code already handles. The `action` selector produces a list,
and no test had ever fed it one, because nobody who believed it was a service
name would think to.

`tests/test_blueprint_configures.py` is the repair. Its rule: **input values are
derived from the selector each input declares**, never written by hand — and an
input whose selector it does not recognise **fails** rather than being skipped.
It validates through `async_validate_config_item`, the same call the UI makes on
save, so a failure is the message the user would have seen.

It needed a real `mobile_app` device in the registry and seven extra test
dependencies, listed in `requirements_test.txt` with the reason: without them,
device-action validation fails with *"Integration 'mobile_app' does not support
device automation actions"*, which reads like a Home Assistant limitation and is
actually a missing import.

**Mutation-tested both ways.** Restoring `action: !input` fails the gate with the
household's own error text.

## 2026-08-09 — the feature had never run

**Everything in the design describes a blueprint Home Assistant refused to
load.** Two bugs, both present from the day the blueprint was written, both
shipped in **0.4.0, 0.4.1 and 0.4.2**, and both invisible to a test suite that
read the YAML rather than running it.

**1. `for: "{{ dwell_minutes }}"` on the arrival trigger.** `for` is validated
with `cv.positive_time_period` — a duration, and no template, ever. The generated
automation failed config validation and was discarded with one line in the log,
so the symptom was not a wrong dwell but *nothing ever happening*, which is
indistinguishable from nobody having been to a shop yet.

Fixed by making `dwell_minutes` a duration selector and passing `!input` straight
into `for`. The input **key** is unchanged, so §0's frozen interface holds — the
same latitude `calendora_member` took when its selector moved from a text box to
an entity picker.

A note on why the existing warning did not prevent it: the blueprint already
carried a comment saying an input a template needs must be bound to a variable
first. That is true and it was not enough. A *trigger* cannot see `variables:`
either, and this particular field could not have taken a template even if it
could. There was no version of the template approach that worked here.

**2. `trigger.event.data.action_data.item_ids | default(...)`.** With no
`action_data` on the event, the attribute lookup raises before `default` is
reached and the branch aborts — so the fallback written for the case where the
platform omits `action_data` was broken by that exact case. A tap would tick
nothing and send nothing. Fixed with `.get('action_data', {}).get('item_ids')`.

### The finding underneath both

Every guard on this blueprint asserted things about parsed YAML: which sends
exist, which are passive, which Android channels appear. All of it was true, and
all of it was true of a file that could not run. **Structural tests on a
blueprint prove it is the blueprint you meant to write; only executing it proves
Home Assistant agrees.**

`tests/test_shop_blueprint_behaviour.py` builds the automation inside Home
Assistant, walks a person into a zone, waits out the dwell, taps the buttons and
reads what came out. Both fixes are mutation-tested against the exact line that
was wrong.

### A claim withdrawn

The dwell was documented as *"Verified on a real Home Assistant: arriving and
leaving after thirty seconds never sends, and stepping outside restarts the clock
rather than firing early."* Whatever was verified, it was not this blueprint,
because this blueprint did not load.

**The dwell is verified in a Home Assistant test and unverified on a phone.** The
test covers both halves — nothing at ninety seconds, the list at two and a half
minutes — which is the useful part of that claim, but it is not a device.

---

## 2026-08-09 — step 3, first half: the replacement on your own tap

Approved by Mike as a split of the design's step 3: build the replacement loop,
leave batching open.

The tap dismissed the card, so something comes back — the same card, against the
list as it stands after the tap, immediately and with no debounce (§6).

**It is one card sent twice, not two cards.** The arrival send carries a YAML
anchor, `&shop_card`, and the ticking branch aliases it. Two payloads written
separately pass every check on the day they are written and drift on the first
edit that touches one of them, and the drift reaches a person as a button missing
from the replacement mid-shop. The tests assert the two sends are the *same
node*; removing the replacement and expanding the alias into a valid copy were
both mutation-tested.

- The branch rebinds `outstanding`, `showing` and `remaining` by subtracting what
  the tap ticked, then sends the anchor. Re-reading the list entity would race
  the state machine — `todo.update_item` returning does not mean the entity has
  settled — and a card that arrives only sometimes is worse than one that never
  arrives, because nobody chases it.
- **Not gated on quiet hours.** §7 exists to stop noise the person did not cause;
  this answers a tap made a second ago. A shopper still in the shop at 21:31 has
  not stopped shopping.
- `interruption-level: active`, per §8 — the list card is active, the completion
  card is passive.

**Batching stays open, and the earlier correction stands.** On a list longer than
`batch_size` this does produce tap → next five → tap → next five, which is the
batching experience under another name. It ships that way knowingly: a
replacement that fires only when the remaining list happens to fit one card works
on short lists and goes silent on exactly the long ones the batching question is
about. What is open is §5's *shape* — whether a batch should be a section of the
shop rather than the next five in list order.

**Not built with it, and now more load-bearing than before:** §6's trip-stop
conditions. Nothing implements the 8-push cap or the 90-minute expiry. Every
replacement is caused by the shopper's own tap, so the loop is bounded by taps
rather than unbounded, but §6 states a hard stop at eight and there is none.
Filed as a card: a counter needs state a blueprint cannot hold without asking the
household for a helper entity, and which way to go is a product decision.

---

## 2026-08-08 — step 4, first half: the completion card

Shipped ahead of step 3, inverting the build order deliberately. When a tap
empties the list, the trip is over and something has to come back. That case
needs no batching decision and no device.

- `interruption-level: passive`, no buttons (§6), no Android channel (§10.3).
- **Off by default.** A blueprint cannot detect the platform, and defaulting it
  on would hand an Android household the exact send §10.3 forbids.

**Still unbuilt from step 4:** the failure card (a tick that did not save).
