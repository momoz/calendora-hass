# Shop arrival — build log

What was built, what was found, and what is still not true. This file belongs to
this repository.

**Why it exists.** `docs/DESIGN-shop-arrival.md` is a vendored copy and its first
line says *"do not edit here; re-copy from the design source"*. Sessions of this
agent have been recording build status inside it anyway, and a vendored copy that
people amend stops being a vendored copy — it disagrees with its source silently,
which is the failure the whole contract exists to prevent, pointed at a design
doc instead of a register. Build status goes here from 2026-08-09.

> **Outstanding, and it needs somebody with access to the design source.** The
> annotations added to `DESIGN-shop-arrival.md` before this file existed are
> still in it, and they cannot be removed from this side: restoring a vendored
> copy means re-copying it, and this repository does not have the original. A
> fresh copy of the design package would let the vendored file go back to being
> a vendored file, with everything below staying here. Requested rather than
> done.

---

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
