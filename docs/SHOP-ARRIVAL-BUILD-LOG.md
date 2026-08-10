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
