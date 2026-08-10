<!-- Vendored design spec, from the shop-arrival design package on 2026-08-07.
     Do not edit here; re-copy from the design source. -->

> ## Two places this document is superseded
>
> Recorded here so the next reader does not restore either of them. Both are
> with design; neither is a deviation taken quietly.
>
> **§6's retry rule is superseded by the API contract.** It specifies "one
> silent retry at 10s", undifferentiated. The server distinguishes the two
> cases and the integration branches on them: `409 conflict` means nothing was
> applied and retrying is correct, so it is retried once with the request
> rebuilt rather than replayed; `400 bad_request` is explicitly
> do-not-retry-unchanged and is surfaced. A blanket retry would re-send
> something already rejected, and a blanket failure card would fire for a
> conflict a retry clears silently. **Do not regress this to match §6.**
>
> **§0's `calendora_member` selector is `text`; the implementation uses an
> entity picker.** The row directly beneath it forbids `text` for
> `notify_service` because a typo fails silently at send time — and that
> reasoning is stronger here, not weaker. A mistyped notify target sends to
> nobody; a mistyped member id resolves to somebody else's opt-in, so a person
> who declined gets a location-triggered shopping list. The key name is
> unchanged, so the frozen interface is intact.
>
> **Verified since this document was written:** ticking an already-ticked item
> does return success rather than an error (§6's claim holds). Two simultaneous
> ticks both succeeded, so the `409` path was *not* reproduced on list items —
> it remains handled but unobserved there.

# Handoff — shop arrival notification

**Design:** `HomeAssistantNotify v2.dc.html` · **Written:** 2026-08-07
**Touches:** the Home Assistant integration (separate public repo), blueprint,
`docs/24-HOME-ASSISTANT.md` §4
**Supersedes:** `HomeAssistantNotify.dc.html` (v1), kept for the reasoning that
changed

Rafi stops at the supermarket and the list arrives on his wrist, tickable
without opening anything. That is the whole pitch for the integration and it is
the part anyone will remember.

Two facts shape every decision below. **Tapping an action dismisses the
notification**, so progress can only be shown by sending a fresh one — this is a
send / tap / re-send loop, not a checklist. And **a locked phone with a watch
present routes to the watch**, so a shopper with a trolley is a watch wearer and
the wrist is the primary surface.

> **Example data throughout is invented.** Rafi and Priya Okonjo, shopping at
> Greenway Market off a list called Family list. No real household names, no
> real list contents. This document is written to go into the public
> integration repo.

---

## 0. Permanent names

**Everything in this section becomes a public interface the day it ships.**
Automations, blueprints and dashboards people build on top of these will break
if they are renamed, so they cannot be improved later. They are picked here, in
one place, deliberately. If any of them is wrong, say so now rather than after
the first release.

### Blueprint input keys — PERMANENT

| Key | Selector | Notes |
|---|---|---|
| `person` | `entity` (person) | The household member's HA identity. Never inferred |
| `calendora_member` | `text` | The Calendora member id the person maps to. Mapping is a user decision made once, per `docs/24-HOME-ASSISTANT.md` §4 |
| `shop_zone` | `entity` (zone) | One blueprint instance per shop |
| `notify_service` | `action` | Not `text`. A text field invites a typo that fails silently at send time, hours after it was saved; the action selector only offers services that exist. Do not restore it to `text` |
| `todo_entity` | `entity` (todo) | The shared list |
| `dwell_minutes` | `number` 1–15 | Default 2 |
| `quiet_from` / `quiet_until` | `time` | Defaults 21:30 / 07:00 |
| `revisit_hours` | `number` 0–12 | Default 2 |
| `batch_size` | `number` 1–5 | Default 5 |
| `max_pushes` | `number` 3–20 | Default 8 |
| `send_completion_card` | `boolean` | Default true. See §11.3 |

Defaults are **not** permanent and may be tuned. The keys are.

### Action identifiers — PERMANENT

| Identifier | Button |
|---|---|
| `CALENDORA_SHOP_GOT_BATCH` | Got these |
| `CALENDORA_SHOP_GOT_ALL` | Got the rest |
| `CALENDORA_SHOP_OPEN` | Open list |
| `CALENDORA_SHOP_STOP` | Not shopping |

The item ids a tap applies to travel in the action's payload, not in the
identifier. This is what lets the batch change while the identifier does not.

### Notification tag — PERMANENT

```
calendora_shop_<person_slug>
```

**One tag for the whole trip**, including the completion card and the failure
card. Every send replaces the last, so a shopper never has more than one of
these in the shade. `<person_slug>` is the person entity's object id.

### Android channel ids — PERMANENT

| Channel id | Name the user sees | Importance |
|---|---|---|
| `calendora_shopping_list` | Shopping list | Default |
| `calendora_shopping_list_quiet` | Shopping list (silent) | Min |

Channel **ids** are permanent and channel **importance is frozen at creation** —
changing either later requires the user to delete the channel by hand. The
displayed names can be changed.

### Not permanent

Every copy string, every `sfsymbols:` icon, the batch size, the dwell default,
the push cap, the section ordering. Change these freely.

---

## 1. When it fires

**Dwell of 2 minutes**, per person, per zone. Not on zone entry.

Long enough that a red light outside the shop, a petrol stop next door and a
drop-off in the car park never fire. Short enough that on a fifteen-item shop
the list is on the wrist before the second aisle.

Three minutes was the alternative and is safer against spurious exits restarting
the clock. Two wins because the person this is for is doing a big shop, and
because a late notification and no notification cost the same amount of trust. A
five-minute dash for milk is a case this loses deliberately — the app is faster
for one item anyway.

A Home Assistant restart mid-dwell cancels the timer silently. We do not detect
or apologise for this. See §7.

Opt-in is **per member**, in the options flow, not per household.

---

## 2. Copy rules

| Slot | Rule |
|---|---|
| Title | `<Shop> — <n> things` on arrival · `<Shop> — <n> left` after · `<Shop> — last one` at one. Shop name truncated to 18 chars on a word boundary. |
| Subtitle | The list's own name. iOS/watchOS only; Android has no equivalent and drops it. |
| Body, sentence 1 | `<Section> (<n>): a, b, c.` |
| Body, sentence 2 | `Then <sections> — <n> more.` |

**The title must stand alone.** It is the entire short look on the watch, and on
a locked iPhone with previews hidden it is not shown at all. Nothing
load-bearing lives in the body that isn't in the title or recoverable by opening
the list.

**Sentence 2 is designed to be cut off.** Android collapses to one line and the
watch long look cuts around there. It is a separate sentence rather than a
clause for exactly that reason.

**Quantities only when greater than one**, in brackets after the item.
Quantity is operational — it changes what you pick up.

**No attribution by default.** Who added a thing is not useful while standing in
front of it. A name appears in exactly two cases:

- someone ticked items you were about to look for — *"Priya got the bakery things."*
- someone added an item while you were in the shop — *"Priya added birthday candles."*

In both the name is the explanation for why the list changed under you, not a
credit.

**Never:** the word Calendora, an emoji, an exclamation mark, "don't forget", a
greeting, or a count of what you have already done.

### Worked copy

```
Greenway Market — 15 things
Family list
Fruit and veg (5): apples, spinach, tomatoes, lemons, bananas.
Then dairy, bakery, household, cupboard — 10 more.
```

```
Greenway Market — 5 left
Family list
Household (3): bin bags, washing-up liquid, kitchen roll.
Then cupboard — 2 more.
```

```
Greenway Market — last one
Family list
Cupboard: tinned tomatoes (4).
```

```
Greenway Market — list clear
Nothing left on the family list.
```

```
Greenway Market — didn't save
Family list
Those three are still on the list. Tap again when you have signal, or tick
them in the app later.
```

---

## 3. The button set

Four identifiers, fixed labels, same order every send, on every state including
the failure card. **Labels never name their contents** — the body does that —
which is what keeps the set stable while the batch changes.

Listed in shipped order, because the order is part of the contract — the table
previously read `OPEN_LIST` third and said "fourth slot" two lines later.

| id | Label | Icon | Does |
|---|---|---|---|
| `GOT_BATCH` | Got these | `sfsymbols:checkmark` | Ticks the items named in the body |
| `GOT_ALL` | Got the rest | `sfsymbols:checkmark.circle.fill` | Ticks everything outstanding, ends the trip |
| `STOP` | Not shopping | `sfsymbols:xmark` | Ends the trip, suppresses this zone for this person until midnight. Ticks nothing |
| `OPEN_LIST` | Open list | `sfsymbols:list.bullet` | Deep link into shopping mode. **iOS only**, fourth slot |

Android shows the first three; it caps at 3 and drops `OPEN_LIST`, because
tapping the body already does that and a third of three visible buttons is too
expensive for a redundancy. Android actions take no icons.

**Icons are fixed even though they can vary per send.** Device testing showed
they are not cached, but a button that changes appearance between sends
reintroduces the ambiguity the fixed labels remove. One exception: on the
failure card `GOT_BATCH` takes `sfsymbols:arrow.clockwise`. The label still says
the same thing; the glyph says try again.

On a single-message list `GOT_BATCH` and `GOT_ALL` are the same action. That
redundancy is the price of a stable set and it is worth paying.

---

## 4. Which surface does what

One payload, three renderings, two different jobs.

**Watch — it is the list.** Buttons appear on a scroll with no gesture to fail.
The whole loop is designed to happen here; a fifteen-item shop clears without
the phone leaving a pocket.

**iPhone — worth opening the list for.** Actions are behind an expand gesture
unreliable enough that we cannot build the flow on it. The buttons stay for
whoever finds them; the designed path is tapping the card.

**Android — either.** Three buttons visible with no gesture, so it behaves like
the watch.

> **Engineering consequence.** The deep link is not a convenience, it is the
> iPhone's primary action. `/lists/<listId>?mode=shopping` must open ready to
> tick — from cold start, offline, on a phone that hasn't opened Calendora in a
> month.

The watch mirrors the phone's payload; we cannot write different words for each.
The watch therefore sets the ceiling on length. That is not a compromise —
everything the phone would have used the extra room for was context the shopper
already has. They know which shop they are standing in.

---

## 5. More items than buttons

The list is never mapped onto buttons. One button ticks a **batch**, and a batch
is **one section of the shop, capped at five items**. Fifteen items becomes four
or five messages in the order the sections are walked.

- Section order is the list's own order, which is already the order a family
  types it in.
- Uncategorised items form a final batch called **Anything else**.
- A section of more than five splits and keeps its name across both messages.

This is the whole design. A batch is a thing a person completes in one place, so
the button matches the trip to the shelf. Fifteen individual buttons would match
the data.

**Fallback if lists turn out not to carry sections** (open, §9): first five items
in list order, section name drops out of the body. Flag it before building —
the body copy wants rewriting rather than degrading.

---

## 6. State transitions and the push budget

Progress after every tap is affordable, so the budget is not what is being
optimised. What is being optimised is **the number of times the phone makes a
noise for something the person did not just do.** A push you caused is expected.
A push you did not cause, at the shelf, twice in a minute, is what gets this
switched off.

### Sends

| Trigger | Timing |
|---|---|
| Your own tap | Replacement immediately, always, no debounce. The tap dismissed the card; something has to come back |
| Someone adds an item while you're in the zone | Debounced 3 min. **Max 3 per trip**, then additions go quiet and ride your next tap |
| Someone else's tick empties the batch on your screen | Immediately, debounced 3 min — else you go looking for things already in a trolley |
| List cleared | One card, no buttons, silent (§8) |
| A tick failed to save | After one silent retry at 10s |

### Does not send

- Someone else ticks something **outside** your current batch — rides your next replacement, where the count is already changing.
- Someone deletes an item or edits a quantity — never its own push.
- You leave the zone with items outstanding — the card stays and expires after 90 minutes. No parting message.
- Anything at all after `STOP`, at that zone, that day.

### The trip stops

At whichever comes first: list cleared · `GOT_ALL` · `STOP` · 90 minutes since
arrival · **8 pushes**.

The eighth is a hard stop with no explanatory ninth. If a trip has taken eight,
the design has already failed and a message about it is not the repair.

A fifteen-item shop costs five. **What we give up:** a shopper who wants live
confirmation that their partner at home is keeping up doesn't get it
push-by-push. They get it the next time they tap, which at the shelf is a few
seconds later.

### Two people, one list

Both get their own notification, at the same shop or different ones. Both loops
run independently against one list. **Ticking something already ticked is a
no-op, never an error.**

---

## 7. Silence rules

An automation that cries wolf gets switched off and never switched back on.

| Case | Behaviour |
|---|---|
| Empty list | Nothing. Never announce an absence of work |
| Already all ticked | Nothing |
| Driving past | Handled by the 2-minute dwell. No further rule |
| Same shop again | Nothing within 2 hours at that zone, unless the list has gained an item since |
| Late or early | Nothing outside 07:00–21:30 local. A shop open at midnight is a shop you are at on purpose |
| Said *Not shopping* | Silent at that zone until midnight. Other zones unaffected |
| Two people at the same shop | Both get one. Suppressing either is worse |
| Delivery suppressed by Focus, or HA restarted mid-dwell | **No retry, no catch-up, no "you may have missed one."** We cannot know, and guessing is how this gets uninstalled |

The recovery for a notification that never arrived is that the list is still the
list. Everything this does, the app does too, and the person is standing in a
shop with a phone in their hand.

---

## 8. Delivery

Sent by the Home Assistant Companion app, so **the sender name and app icon are
Home Assistant's** on both platforms and cannot be changed. Nothing in the copy
works around that. To the person holding the phone this is their smart home
talking, and that is a fine position to be in — the smart home is a trusted
messenger.

**Calendora appears in exactly two places**, both of them places somebody has
gone looking rather than places we pushed it: the Android channel name, and the
app you land in when you tap. On a lock screen at a supermarket a brand prefix
would cost a quarter of the title to answer a question nobody is asking.

### Android

- `channel: "Shopping list"` — visible on long-press and in notification
  settings. **This is the mute switch**, and that is the point: a family can turn
  this off without turning off their smart home.
- `notification_icon: "mdi:cart"` with `color` set to the brand accent.
  Distinguishes this from every other HA notification in the status bar.
  Function, not branding.
- `group` and `tag` per person per trip.
- Importance is fixed at channel creation. Pick it once; changing it later
  requires deleting the channel.
- **Completion card: not sent on Android. Decided 2026-08-08, not degraded into.**
  The intent was a second low-importance channel so it makes no sound. That was
  never verified, Android is out of scope for months, and §10.3 is now the
  decision rather than the fallback. Silent or nothing — and on Android it is
  nothing. **Never a compromise at normal importance with quieter copy.**

### iOS and watchOS

- No channel equivalent. The only granular control is a Focus filter. Document
  it, because the alternative is muting Home Assistant entirely.
- `subtitle` carries the list name.
- Thread id per person per trip, so these stack apart from other HA
  notifications.
- Actions carry `sfsymbols:` glyphs, fixed per action.
- Interruption level **active** for the list, **passive** for the completion
  card — which solves on iOS what the second channel was for on Android, and
  needs no verification.
- Not time-sensitive. A shopping list is not allowed to break a Focus.
- No accent colour, no custom icon, no sender name. Nothing is written twice to
  cover the difference.

### Previews

iOS hides notification content on a locked phone by default: the card reads
"Home Assistant · Notification" and nothing else.

**We never ask anyone to change this.** The setting is per app, and the app is
Home Assistant — turning previews on for a shopping list also puts every door
sensor, camera alert and alarm message on the lock screen in front of whoever is
standing next to you in the queue. We would be asking a family to weaken their
phone's privacy for our convenience, and some can't say yes anyway on a
work-managed device.

No prompt, no onboarding step, no banner explaining what they are missing. The
wrist shows content on a raise, is more private, and is the surface the shopper
is using. Design for the restricted state; let the unrestricted one be a bonus.

---

## 9. Open

**Android is out of scope — weeks to months out, not a target platform (decided
2026-08-08).** Design for iOS and the watch. Where a decision has an Android
branch and an iOS branch, **the iOS branch is the product and the Android branch
is a note for later.** Nothing here waits on an Android device any more.

1. **Do real lists carry sections?** §5 leans on it. If the proportion is low,
   flag before building — the body wants rewriting, not degrading.

### Settled on device — closed

Action buttons dismiss the notification. A same-tag replacement re-alerts and
updates in place rather than stacking. `sfsymbols:` icons render on iOS actions
and are not cached. A locked phone with a watch present routes to the watch and
leaves the phone silent. iOS hides previews on a locked phone by default.

**The push rate limit is 500 per device per day**, resetting at a fixed UTC time,
counted per phone and separately per platform. A trip capped at eight spends
under 2% of a day, so the budget is not a design constraint. *(Was open question
4. Answered without raising a log level on a production instance, which is worth
remembering next time.)*

**The watch long look does NOT inherit the phone's hidden-previews setting** —
with previews hidden on a locked phone, the lock-screen card is unreadable while
the watch shows full content, so the wrist remains the answer §8 relies on.
**Caveat, and it is the whole of what is unverified here:** watchOS carries its
own notification privacy setting, so this verifies one configuration rather than
the default for every user. Design as though it holds; do not state it as
universal. *(Was open question 3.)*

### Closed by decision, not by test

**Two Android channels from one automation.** Never verified, and now moot:
Android is out of scope, and §10.3 is adopted as the decision rather than kept as
a fallback. No completion card on Android. This does not reopen if an Android
device appears — reopening it is a product decision, not a test result.

---

## 10. Three decisions you asked for

### 10.1 The Apple Watch is first-class

**Decision: first-class, with its own mockups and its own copy budget.** Not an
acknowledged degradation.

A locked phone with a paired watch delivers to the wrist and the phone stays
silent. A shopper with a trolley in one hand is exactly the person wearing one,
and the watch is the only surface where the action buttons appear without a
gesture that fails. The iPhone's expand is unreliable enough that if the watch
were the afterthought, the loop this whole feature is built on would have no
reliable home on iOS at all.

The copy budget follows from that: **the watch sets the ceiling on length and
the phone gets whatever fits it.** We cannot write different words per surface —
the watch mirrors the phone's payload — so the shorter screen wins every
conflict. Concretely: title stands alone for the short look, batch lands in the
first sentence, everything after is designed to be cut off.

**What this costs:** the iPhone lock screen has room we deliberately don't use.
That room would have held context the shopper already has — they know which shop
they are standing in.

### 10.2 Dwell, N = 2 minutes

**Decision: 2 minutes.**

The trade is against 3, which was the serious alternative. Three is safer:
coarse location can register a spurious exit from a stationary phone, which
restarts the clock, and a longer N absorbs one of those without the notification
getting uselessly late. Two is chosen anyway because:

- The person this feature is for is doing a **big shop**, and the value is
  highest when the list arrives before they have walked past the first section.
- A late notification and no notification cost roughly the same amount of trust.
  Being early has upside; being late has none.
- The drive-past problem — the thing N exists to solve — is already fully solved
  at 2. Verified: arrive and leave after 30 seconds never fires.

**What we give up:** the five-minute dash for milk. Someone running in for one
item may be at the till before the notification lands. That case is written off
deliberately — opening the app is faster than waiting for us when the list is
one line long.

`dwell_minutes` is a blueprint input, so a household that finds 2 too twitchy
can raise it without us shipping anything.

### 10.3 No completion card on Android

**Decision, taken 2026-08-08. This is no longer a fallback held in reserve
against a test — it is what the product does.** Android is out of scope for
months, the quiet channel was never verified, and a permanent, unverifiable
guess at a channel importance is not worth carrying.

The completion card is the one send the shopper did not ask for. It exists only
because the alternative is the card silently vanishing after the last tap and
the shopper wondering whether it took. That is worth a silent card. It is not
worth a sound.

**Do not send the completion card on Android at all.** `send_completion_card` is
false for Android targets, and that is the shipped configuration rather than a
degraded one.

The absence is acceptable because Android's shade keeps the trip card
visible throughout — the Android shopper has been watching the count go down in
place, so the absence of a card is a weaker signal there than it would be on
iOS. A buzz at the end of a shop to announce that the shop is over is precisely
the notification that gets this feature switched off in week two.

**Do not** compromise by sending it at normal importance with quieter copy, and
**do not** fold the confirmation into the last list card — that card is dismissed
by the tap that completes the list, so there is nothing to fold it into.

**iOS is where the completion card lives, and it is unblocked.** Interruption
level `passive` does the same job the quiet channel was for, is set **per
notification rather than per channel**, and needs no device verification — so
nothing about the completion card is waiting on hardware any more. It is
unbuilt only because it is step 4 (§11).

**No test is pending against this.** It was closed by decision, not by
measurement; if an Android device turns up, that does not reopen it.

---

## 11. Order to build

1. Dwell trigger, per-member opt-in, and the silence rules (§1, §7). Nothing
   else is safe to test without these.
2. Arrival send: title, subtitle, body, the four actions. One message, no
   batching — a four-item list works end to end.
3. Batching and the replacement loop (§5, §6). This is where the design lives.
4. The completion card and the failure card.
5. Shared-list attribution and the added-item push (§2, §6).
6. Android channel, icon and colour; iOS thread id and passive level (§8).

Steps 1–2 are shippable to one household on their own, and are what ships today.

### Step 3 bundles two things with different blockers — split it

**The replacement loop is not blocked; batching is.** They were written as one
step and they are not one piece of work:

- **Batching (§5)** is stopped on a product question — whether fifteen items
  across four buttons is a problem this household actually has — and its
  correctness depends on the `action_data` device test, because "re-read the
  list" stops meaning "the items on the card you tapped" once more than one card
  is in flight.
- **The replacement on your own tap (§6)** depends on neither. The automation
  already recomputes `outstanding` from the list on every branch, so a
  replacement rebuilds from current state and never needs the tap's payload. It
  is the line §6 calls load-bearing — *the tap dismissed the card; something has
  to come back* — and today, after a tick, nothing does.

Splitting them makes step 4's completion card reachable too: on iOS it is
`interruption-level: passive` and needs no verification (§10.3).

**Correction, 2026-08-08.** The split above is real in terms of *blockers* and
overstated in terms of *outcome*. The arrival card already slices to
`batch_size` and appends "Then N more", so adding the replacement means tap →
next five → tap → next five. **That is the batching experience**, whatever it is
called, and it needs the same product answer rather than only the absence of a
device test. What is genuinely separable is the *terminal* case below.

**Decided, 2026-08-09 (Mike).** The split is approved. Build the replacement on
your own tap; leave batching open on the card rather than letting one unanswered
question park the half that has an answer.

**And the correction above stands as written.** On a list longer than
`batch_size` the replacement does produce tap → next five → tap → next five, and
that is the batching experience arriving under another name. It ships that way
knowingly, because the alternative — a replacement that only fires when the
remaining list happens to fit one card — is a loop that works on short lists and
goes silent on exactly the long ones the batching question is about. What stays
open is §5's *shape*: whether a batch should be a section of the shop rather
than the next five in list order.

### Step 3, first half: BUILT 2026-08-09 — the replacement on your own tap

The tap dismissed the card, so something comes back: the same card, against the
list as it stands after the tap, immediately and with no debounce (§6).

**It is one card sent twice, not two cards.** The blueprint sends a YAML anchor,
`&shop_card`, and the ticking branch aliases it. That is not a tidiness
preference — two payloads written separately pass every check on the day they
are written and drift on the first edit that touches one of them, and the drift
surfaces as a shopper mid-trip tapping a button that the replacement does not
carry. `tests/test_shop_blueprint.py` asserts the two sends are the *same node*,
and both halves of that are mutation-tested: removing the replacement fails, and
expanding the alias into a valid copy fails.

- The ticking branch rebinds `outstanding`, `showing` and `remaining` by
  subtracting what the tap ticked, then sends the anchor. Same reasoning as the
  completion card: re-reading the list entity races the state machine.
- **Not gated on quiet hours.** §7 exists to stop this making a noise for
  something the person did not do; a replacement answers a tap made a second
  ago. A shopper still in the shop at 21:31 has not stopped shopping.
- `interruption-level: active`, per §8 — the list card is active, the completion
  card is passive.

**Not built with it, and now more load-bearing than before:** §6's trip-stop
conditions. Nothing implements the 8-push cap or the 90-minute expiry. Every
replacement is caused by the shopper's own tap, so the loop is bounded by taps
rather than unbounded — but §6 states a hard stop at eight and there is none.
Filed rather than built, because a counter needs state a blueprint cannot hold
without asking the household for a helper entity, and that is a product
decision.

### Step 4, first half: BUILT 2026-08-08 — the completion card

**Shipped ahead of step 3, which inverts the build order deliberately.** When a
tap empties the list — any list that fits one card, and any "Got the rest" on a
list that does not — the trip is over and something has to come back. That case
needs no batching decision and no device.

- `interruption-level: passive`, no buttons (§6), no Android channel (§10.3).
- **Off by default.** A blueprint cannot detect the platform, and defaulting it
  on would hand an Android household the exact send §10.3 forbids.
- Computed as `outstanding` minus what this tap ticked, rather than re-reading
  the list entity. Re-reading races the state machine, and a completion card
  that fires *sometimes* is worse than one that never fires.

`tests/test_shop_blueprint.py` holds the decisions mechanically: the default is
off, the card is passive, it carries no buttons, and no second Android channel
exists anywhere in the blueprint. Each guard was mutation-tested against the
edit it exists to catch.

**Still unbuilt from step 4:** the failure card (a tick that did not save).
