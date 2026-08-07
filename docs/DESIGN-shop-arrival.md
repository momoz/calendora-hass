<!-- Vendored design spec, from the shop-arrival design package on 2026-08-07.
     Do not edit here; re-copy from the design source. Where this repository's
     implementation deviates, the deviation is recorded in the blueprint's own
     comments and reported as a gap — it is not silently reconciled. -->

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

| id | Label | Icon | Does |
|---|---|---|---|
| `GOT_BATCH` | Got these | `sfsymbols:checkmark` | Ticks the items named in the body |
| `GOT_ALL` | Got the rest | `sfsymbols:checkmark.circle.fill` | Ticks everything outstanding, ends the trip |
| `OPEN_LIST` | Open list | `sfsymbols:list.bullet` | Deep link into shopping mode. **iOS only**, fourth slot |
| `STOP` | Not shopping | `sfsymbols:xmark` | Ends the trip, suppresses this zone for this person until midnight. Ticks nothing |

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
- **Completion card, unconfirmed.** Intent is a second low-importance channel so
  it makes no sound. If one automation cannot write to two channels, **do not
  send it on Android at all.** Silent or nothing — never a compromise at normal
  importance.

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

1. **Two Android channels from one automation.** Unverified — test device
   broken. Design degrades by dropping the completion card on Android (§10.3).
   One test closes it.
2. **Do real lists carry sections?** §5 leans on it. If the proportion is low,
   flag before building — the body wants rewriting, not degrading.
3. **Does the watch long look show content when the phone has previews hidden?**
   watchOS has its own privacy setting. If it inherits the phone's, §8 gets
   considerably worse and the wrist stops being the answer.
4. **The rate limit number.** Eight per trip is comfortable under anything in the
   low hundreds. Worth knowing what a household of four at three shops a week
   actually spends.

### Settled on device — closed

Action buttons dismiss the notification. A same-tag replacement re-alerts and
updates in place rather than stacking. `sfsymbols:` icons render on iOS actions
and are not cached. A locked phone with a watch present routes to the watch and
leaves the phone silent. iOS hides previews on a locked phone by default.

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

### 10.3 If the Android quiet channel doesn't work

**Unverified. Do not build as though it is confirmed.**

The completion card is the one send the shopper did not ask for. It exists only
because the alternative is the card silently vanishing after the last tap and
the shopper wondering whether it took. That is worth a silent card. It is not
worth a sound.

**If `calendora_shopping_list_quiet` cannot be written to by the same
automation, or arrives at normal importance with a sound: do not send the
completion card on Android at all.** Set `send_completion_card` to false for
Android targets and ship it that way.

The degradation is acceptable because Android's shade keeps the trip card
visible throughout — the Android shopper has been watching the count go down in
place, so the absence of a card is a weaker signal there than it would be on
iOS. A buzz at the end of a shop to announce that the shop is over is precisely
the notification that gets this feature switched off in week two.

**Do not** compromise by sending it at normal importance with quieter copy, and
**do not** fold the confirmation into the last list card — that card is dismissed
by the tap that completes the list, so there is nothing to fold it into.

iOS is unaffected: interruption level `passive` does the same job, is per
notification rather than per channel, and needs no verification.

**One test closes this**, on any working Android phone: fire two notifications
from one automation to two channel ids and confirm the second is silent.

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

Steps 1–2 are shippable to one household on their own.
