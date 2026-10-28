# Calendora `/api/v1` — the third-party surface

**Source:** `momoz/calendora` @ `4a7fb28` (this change is the commit after it)
**Contract fingerprint:** `f8375a71c1f25f78` — see §10
**Regenerated:** 2026-10-28

This is the whole of what a third-party client is promised. Nothing outside this
file and `fixtures/api-v1/` is a contract: if something you need is not written
down here, that is a gap to file rather than a behaviour to discover.

**Hand-built for a public repository.** It deliberately omits the first-party
route inventory, the sync protocol, and anything unsettled.

---

## What changed since the last extract

- **An item says whether it is a chore** (GAP-019; fixtures changed,
  fingerprint changed). Every item from `GET /lists/{id}/items` carries
  `repeats: boolean`. A chore is an item that repeats: ticking it moves `due` to
  the next time rather than finishing it (§7). So "chores due today" is the
  items with `repeats: true` whose `due` is today or earlier, read in the key
  owner's zone from `GET /whoami`. Read-only, as `repeats` is on events: the
  rule itself is never returned, so it cannot be written either. The
  `list-items` pair now has a repeating item (`Bins out`) and a one-off
  (`Return the school form`) due the same day; `repeats` is the only field that
  tells them apart.

- **`listId` on each item is now written down** (GAP-021; it was always
  returned). It is the list the item is on, and `PATCH` takes it to move the
  item to another of the household's lists (§7).

- **Fixtures for tags, drive times and leave-by** (GAP-020; fixtures added,
  fingerprint changed; no behavior changed). `events` now has an occurrence
  with two tags, one `fromCalendar`, and drives from `"home"` and from a typed
  address. New pairs: `event-leave-by`, `event-leave-by-none`,
  `write-event-tag`, `write-event-untag` and `error-untag-from-calendar`.

- **An imported event takes a drive time** (web v2610.0451; no fixture
  changed, so the fingerprint did not). `PATCH /events/{id}` on an event with
  `readonly: true` now accepts a body whose only fields are `travelMinutes` and
  `travelFrom` (with `scope`). Anything else in the same body, `attendeeIds`
  included, is still the `400` it always was, and nothing is applied. On a
  repeating imported event the drive is on every occurrence, so `scope` must be
  `"all"`. When the calendar moves the meeting somewhere else, the next refresh
  clears both fields.

- **Every event carries `tags`** (web v2610.0450; fixtures changed, fingerprint
  changed). `tags: [{ id, name, color, fromCalendar }]` on every occurrence
  from `GET /events` and `GET /events/{id}`: **the key owner's own tags** (an
  event's tags are personal, so nobody else's are ever returned), in name
  order, and `[]` when there are none — never absent. `fromCalendar: true`
  marks the tag a subscribed calendar puts on everything it brings in. A tag
  is on the series, so every occurrence of a repeat carries it. New writes,
  allowed on imported events too: `POST /events/{id}/tags` and
  `DELETE /events/{id}/tags/{tag}` (§7). **Nothing to change** unless you want
  tags; an unknown field is ignorable.

- **An event says where its travel time is from: `travelFrom`** (web
  v2610.0446; fixtures changed, fingerprint changed). `"home"` when the drive
  was worked out from the household's home address, the address or place it
  was worked out from, or `null` — which includes every number typed by hand.
  Returned on every event and occurrence, and writable: send it with
  `travelMinutes`. **Sending `travelMinutes` without it clears it** (the new
  number is not from anywhere), and a `travelFrom` with `travelMinutes: null`
  is a `400`. `GET /events/{id}/leave-by` returns it too, and its `words` now
  say where from: `"Leave home at 10:40 AM · 20 min drive"` from home,
  `"Leave by 10:40 AM · 20 min drive from 1431 Orange Camp Rd"` from anywhere
  else, and the old sentence, unchanged, when `travelFrom` is `null`.
  **Nothing to change** if you only show `words`; if you parse it, stop.

- **Equal positions come by id** (web v2610.0435; no fixture changed, so the
  fingerprint did not). `GET /lists/{id}/items` sorts `sections` and `items`
  by `position` as a plain string, then by `id` — the rule both apps sort by.
  Before this, rows sharing a `position` came in whatever order the database
  returned them, so the same list could read differently twice.

- **Appended positions are longer** (web v2610.0434; one fixture value,
  fingerprint changed, no new field). A `position` the server mints at the end
  of a list now ends in a short random tail (`"n"` became `"niii"` in
  `list-items-after-check`), so two clients appending at the same moment no
  longer get the same key. Nothing to change if you already treat `position`
  as an opaque string and compare it as a string; do not parse it or expect a
  fixed length.

- **Dinner, Phase 3** (`DINNER-SPEC.md` §5; web v2610.0432; fixture added,
  fingerprint changed). New, under `meals:read`: **`GET
  /dinner/suggestions`** (`?day=`, today in the key owner's zone by default)
  — up to four ideas from the household's favorites, ideas, recipes and fresh
  leftovers, each `{ key, source, title, reason }` with one reason that is a
  fact a person can check, best first; `busyUntil` is how late the key
  owner's own afternoon runs. Reasons about the pantry need `pantry:read` and
  recipes need `recipes:read`; without them those are left out, never
  guessed. **Each dinner on the card gains** `timeline` (`steps` — preheat,
  start, rest and serve, each with a wall `time` like `"5:40"` — plus
  `untimed`, the dishes nobody gave minutes, and `conflicts`, plain
  sentences; null without a serve time), `nextStep` (on the key owner's
  today), `rating` (`again`, `fine`, `not_again` or null — already writable
  on a meal), `askRating`, and `rain` ("Rain likely around 6" — only for a
  dish on outdoor gear, from the digest's forecast; otherwise null). A line
  that names a saved place by its name now
  sets `placeId`; sending `placeId` still wins. Fixture: `dinner-suggestions`.

- **Dinner, Phase 2** (`DINNER-SPEC.md` §5; web v2610.0430; fixtures added,
  fingerprint changed). A meal gains `placeId` (a saved place) and a dish
  `gearId` (the household's gear), both read and written. New, all under
  `meals:*`: **`GET|POST /places`**, `POST /places/{id}/archive`;
  **`GET|POST /gear`**, `POST /gear/{id}/archive`; **`GET|POST
  /favorites`**, `POST /favorites/{id}/plan`; **`GET /meals/ideas`** (dinners
  with no day); **`GET /meals/{id}/check`** (each dish have / need / unknown,
  with why); `POST /meals/{id}/add-to-list` (needs `lists:write`; `dryRun`);
  `POST /meals/{id}/prep/{prepId}/complete`. **The dinner card gains** `away`
  (who the calendar says is away tonight, with why — a suggestion), and each
  meal `place` (phone, order link), `orderBy` ("6:00": serve time less the
  place's lead) and `prep` (thaw and start-by reminders, server-computed).
  Fixtures: `places`, `gear`, `favorites`, `meals-ideas`.

- **Dinner, and meals get their own scopes** (`DINNER-SPEC.md` §5, ask
  §10.3–10.4; web v2610.0421; fixtures added, fingerprint changed). **The meal
  routes now need `meals:read` / `meals:write`** instead of `recipes:*`.
  Every existing key holding `recipes:read` was granted `meals:read`, and
  `recipes:write` was granted `meals:write`, once, so no integration lost
  access; a key without them gets **403 naming `meals:read`**
  (`error-meals-scope`). A meal now also carries the dinner: `kind` (cook,
  quick, takeout, leftovers, out, skip, or null when nobody said), `title`,
  `dishes`, `serveAt` (a wall time, `"18:30"`) with `serveTz`,
  `ownerMembershipId`, `dinerIds` (null = the household's usual diners),
  `placeText`, `orderText`, `fulfillment`, `notes`, `rating`, `idea`, and the
  derived `line`, `headline`, `sourceLine` and `plannedBy`. `recipeId` and
  `text` keep their old meaning for every meal: words-only meals read exactly
  as before. **`GET /dinner?day=`** (`meals:read`) is the dinner card — the
  object the Today page draws; its `headline` is the string every surface
  shows, `"Not planned"` when nothing is. That is the sensor's state. See §6a.
  `/stream` fires `changed` for meal writes, as for every write.

- **What the pantry holds answers a recipe by the ingredient match rule**
  (`PANTRY-PLAN.md` §13; web v2609.0402; no fixture change). "Smoked paprika"
  in the pantry now answers a recipe's "paprika" as have; "paprika" answers
  "smoked paprika" as a **substitute**, as do curated pairs (chicken broth for
  chicken stock). A substitute is never missing, and never "have".
  `GET /pantry/missing` and `/pantry/can-make` stop counting such a line in
  `missingCount` and name it in a new `substitutes` array, `[{ item, using }]`
  ("chicken stock", using "Chicken broth"). `POST /recipes/{id}/add-to-list`
  leaves it off by default under `have`, with `reason` `substitute` and note
  "Can use Chicken broth instead"; `skipped[].reason` can now be
  `substitute`, and `lineIds` still puts it on. **Nothing the Home Assistant
  integration calls changes**, though a `missingCount` sensor can now read
  lower for the same pantry.

- **The meal plan** (`MEAL-PLAN.md` §5; web v2609.0400; no fixture change,
  fingerprint unchanged). Recipe scopes: a plan is recipe data.
  **`GET /meals?week=YYYY-MM-DD[&weekStart=0-6]`** (`recipes:read`) answers
  every day of that week (Sunday-start unless `weekStart` says otherwise) with
  its `meals` and the `lines` each reads as ("Dinner: Chili").
  **`POST /meals`** (`recipes:write`) `{ day, slot?, recipeId | text,
  servings?, cookedAt?, leftoverOf?, id? }` plans one: a recipe OR words
  ("leftovers", "out"), never both; `slot` is breakfast, lunch, dinner or
  snack, dinner by default; `day` is a date, never a time.
  **`PATCH /meals/{id}`** changes only what is sent (a new `day` moves it);
  **`DELETE /meals/{id}`** takes it off the plan. A meal reads as `{ id, day,
  slot, recipeId, text, servings, cookedAt, leftoverOf }`, exactly what it
  may write. **`GET /meals/shop?week=…&listId=…`** (`recipes:read` +
  `lists:read`) is "Shop for this week": the week's recipes merged and scaled
  per meal against a list, with what would be added, combined and left off —
  it writes nothing. **Your integration needs no change.**
- **Two new routes for the shop-arrival Live Activity, behind a server flag**
  (`38` §6b; web v2609.0398; no fixture change,
  fingerprint unchanged). `lists:write`. **`POST /shop-trips`** `{ listId,
  shopName, membershipId? }` on arrival — the key's owner when no member is
  named — answers `201 { tripId, started: true, delivered }`, or `200 { tripId,
  started: false, reason }` where `reason` is `off` (the Live Activity is not on
  for that person), `no-account`, `nothing-to-buy` or `already-shopping` (and
  `tripId` is the trip already running). **`POST /shop-trips/{tripId}/end`**
  when they leave the zone: `200 { tripId, ended: true }`, `404` if it is not
  running. **`GET /shop-trips/{tripId}`** (`lists:read`) answers `{ tripId,
  status, listId, membershipId, shopName, startedAt, endedAt, remaining }` —
  `status` is `active`, `stopped` (STOP on the phone's Live Activity), `done`
  (the list was cleared) or `ended`; `remaining` is every unticked item in list
  order as `{ itemId, text, quantity }`. Check it before any further
  notification on a trip: anything but `active` means stop. A list or member outside the key's household is `404`. Nothing else
  changes, and the notification flow runs as before whichever way these answer.
  **Your integration needs no change**; calling these on arrival and leaving is
  opt-in.
- **A pantry scan estimates a use-by date when no label can be read**
  (`58` §5; web v2609.0397; no fixture change, fingerprint unchanged). In
  `POST /pantry/scan`'s proposal, an item new to the space with no readable
  date can now carry `expires` with `expiresSource: "default"` — USDA
  FoodKeeper's days for that kind of food in that kind of space, counted from
  today in the household owner's zone. An item already in the space keeps its
  date, a label's date is still `"label"`, and with no zone set there is no
  estimate. Show a `"default"` date as an estimate ("about Oct 4"). **Your
  integration needs no change.**
- **Merging two ingredients moves pantry items too.**
  `POST /ingredients/{id}/merge` already moved recipe lines and list items to
  the ingredient kept; pantry items pointing at the one removed were left on
  it. They now move as well, and `moved` counts them. **Your integration
  needs no change.**
- **An event's `color` and `status` are readable and writable; an item's
  `listId` is readable, and writable to move it** (`#230`; web v2609.0395;
  fixtures changed, fingerprint `d0838b728e4070a2`). `color` is `"hue:tone:chroma"` (tone
  `light|mid|deep`, chroma `grey|soft|vivid`, e.g. `"241:mid:vivid"`) or `null`
  for no choice — anything else is a `400` naming the form. `status` is
  `confirmed|tentative|cancelled`. **`PATCH /lists/{id}/items/{itemId}`
  with `listId`** moves the item to another of the household's lists (an
  archived or unknown list is refused); its section stays behind unless you
  name a `sectionId` on the new list in the same write. Each item in
  `GET /lists/{id}/items` now says its `listId`. **Your integration needs no
  change.**

- **`POST /events` can make a series: `repeat`**, and **every occurrence now
  carries `repeat`** — the pattern it was made with (web v2609.0395; the
  fixtures changed). Send
  `{ "frequency": "daily"|"weekly"|"monthly"|"yearly", "interval": 2,
  "weekdays": ["TU","TH"], "endsOn": "2026-12-15" }` (or `"count": 10` instead
  of `endsOn`; `weekdays` is weekly only, defaulting to the start's day; monthly
  falls on the same date). The rule is built by the same code the apps' repeat
  editors use. On read, `repeat` is `null` for a one-off, the same object for a
  series, or `{ "frequency": "custom", … }` for a pattern `repeat` cannot
  express (a subscribed calendar's, or "the first Saturday") — never a nearest
  reading. **`repeat` is create-only**: changing a series' pattern splits it,
  which is the app's; `PATCH` refuses it as an unknown field. **Your
  integration needs no change**; `repeats` (boolean) is unchanged.

- **A recipe's photo is writable: `POST /recipes/{id}/photo` and `DELETE
  /recipes/{id}/photo`** (`recipes:write`; web v2609.0395). POST takes
  `{ "imageUrl": "https://…" }`: the image is fetched (public addresses only),
  checked and stored like any upload, and REPLACES any photo the recipe had;
  the answer is the recipe, with its new `photoUrl`. An address that is not an
  image is a `400` and changes nothing. DELETE clears it. These are the MCP
  tools `attach_recipe_photo` and `remove_recipe_photo`.

- **`GET /events/{id}/leave-by` is new** (web v2609.0395; §4). When to leave
  for an event, from its `travelMinutes`: `leaveAt`, `passed`, and the words
  the app shows. Null when no travel time is set. A plain id of a repeating
  event means its next occurrence. This is what a `leave_by` sensor would
  read; `docs/HANDOVER.md` listed it as having no route.

- **A multi-day event is in every window it touches** (since web v2609.0387).
  `GET /events?from=&to=` returned an event only if it STARTED inside the
  window, so a trip from the 8th to the 11th was missing from a request for
  the 9th alone. It now comes back for every day it covers. **Your integration
  needs no change**: if you de-duplicate by `id`, a trip that spans two of
  your requests now appears in both, as it always should have.
- **An all-day event's `start_date`/`end_date` are its dates, read the same
  way everywhere** (since web v2609.0388). They come from one shared rule: the
  first date is the day its start falls on in its own zone, and the exclusive
  end is the nearest midnight to its end. A row saved by an older phone with
  zone `UTC` but New York midnights now reads as the dates people see in the
  app. Nothing you send changes meaning.
- **`GET /pantry` without `?today=` uses the key owner's day, not the
  server's** (web v2609.0393). It used the server's UTC date, which was
  already tomorrow every evening in the Americas. It now uses the day in the
  key owner's home zone, then the household owner's; `todayFrom` names the
  zone it used. **If nobody has a zone set, it answers `400` and asks for
  `today`** rather than guess. Sending `today` works exactly as before and
  is still the way to count in your own day.

- **A spice rack decides spices** (PANTRY-PLAN §12). A pantry space can be
  of kind `spices`. When a household has one, `POST /recipes/{id}/add-to-list`
  judges spices and dried herbs by it: a row's `reason` can now be
  `notInRack` (note "Not in your spice rack"), and such a line goes on the
  list. `GET /pantry/missing` counts it as missing, and names a spice in the
  rack under `have` with the rack as `where`. Households without a spice
  space see no change. **Nothing the Home Assistant integration calls
  changes.**
- **`POST /recipes/{id}/add-to-list` leaves off what the household probably
  has** (`docs/57-RECIPES.md`, RECIPES-PLAN §16). By default, only "Need to
  buy" goes on. Left off, each with why: what the pantry holds, staples, food
  bought but not yet seen in the pantry, and kitchen basics (salt, pepper,
  spices, spice-rack herbs unless the line wants them fresh, oils, vinegars,
  baking staples). A staple or basic the
  pantry says is running low or out goes ON. The answer gains `rows`: one per
  ingredient line, with `lineId`, `name`, `section` (`need` | `have`), `added`,
  `reason`, and `note`, the words the apps show ("Kitchen basic: spice"). **`lineIds` now means exactly these
  lines go on**, overriding the default — pass a basic's line id to add it.
  `notAdded` sentences are reworded ("Staples: Salt", "Kitchen basics:
  pepper"), and `skipped[].reason` can now be `have`, `staple`, `bought`,
  `basic`, `optional` or null. `GET /pantry/missing` and `/pantry/can-make`
  no longer count kitchen basics as missing, and name them in a new `basics`
  array beside `staples`. **Nothing the Home Assistant integration calls
  changes.**
- **A recipe's tags are the household's** (`docs/57-RECIPES.md` §7). `tags`
  on a recipe, the `tag` filter on `GET /recipes`, `POST /recipes/{id}/tags`
  and `DELETE /recipes/{id}/tags/{tag}` now use the household's shared recipe
  tags, not the key owner's own. Every key in a household sees the same tags on
  a recipe. Event and list tags are unchanged. **The Home Assistant integration
  calls none of these.**
- **A list is written as `shopping` or `todo` only** (§7, `POST` and `PATCH
  /lists`). `packing`, `checklist` and `custom` are now a 400. They were
  accepted before, but no screen shows those lists, so a list made that way
  existed and nobody in the household could see it. **Breaking only for a
  caller that sent one of the three**; none exist in production. Reads still
  report the column as stored.
- **Ticking a repeating chore moves it to next time** (§7, `PATCH
  /lists/{id}/items/{itemId}`). `isChecked: true` on an item that repeats no
  longer leaves it checked: its `due` moves to the next time it comes round and
  it reads back unchecked, exactly as it does in the app. **The Home Assistant
  integration needs no change** — a chore ticked from a todo entity now comes
  back instead of disappearing. An item that does not repeat, or whose repeat
  has run out, is ticked as before.
- **The pantry, and two new scopes: `pantry:read` and `pantry:write`**
  (`docs/58-PANTRY.md` §7). `GET /pantry` (every space and its items, plus
  `useSoon`; send `?today=YYYY-MM-DD`), `GET /pantry/spaces/{id}`,
  `POST /pantry/items`, `PATCH` and `DELETE /pantry/items/{id}`,
  `POST /pantry/items/{id}/move` (`{spaceId}`), `GET /pantry/missing?recipeId=`
  and `GET /pantry/can-make?maxMissing=` (both also need `recipes:read`), and
  `POST /pantry/scan` (`{spaceId, imageUrls}` → a proposal; nothing is saved).
  Writable item fields: `name`, `brand`, `size` (`"500 g"`), `quantityKind`,
  `quantityValue`, `quantityLevel`, `expires`, `barcode`, and `unconfirmed`
  (to `false` only). Quantity is one of four shapes — count, atLeast, present,
  level — and any other combination is refused saying what to send.
  **Nothing the Home Assistant integration calls changes, and it needs neither
  scope.** A ticked shopping item still becomes an unconfirmed pantry item on
  the server, whoever ticks it.
- **Recipes, and two new scopes: `recipes:read` and `recipes:write`**
  (`docs/57-RECIPES.md` §15). `/recipes`, `/recipes/{id}` and its
  `ingredients`, `sections`, `steps`, `tags`, `view` and `add-to-list`
  sub-resources, plus `/ingredients` and `/staples`. **Nothing the Home
  Assistant integration calls changes, and it needs neither scope.** The one
  endpoint that touches a list, `POST /recipes/{id}/add-to-list`, needs
  `lists:write` AND `recipes:read`, and writes list items through the same
  path as everything else — so an item it adds arrives in your todo entity
  like any other, with `quantity` as free text (`"1 (15 oz) jar"`).
- **Lists can be created, renamed, archived and deleted** (§7). `POST /lists`,
  `PATCH /lists/{id}`, `DELETE /lists/{id}`. Writable fields: `name`,
  `description`, `type`, `color`, `icon`, `isArchived`. `position` is
  server-computed and `shareToken` is not writable by anyone.
  **Nothing you already call changes.**

  **`isArchived` and `deletedAt` are not the same act.** Archiving is
  reversible and keeps every item; you already skip archived lists, so a list
  archived through the API will simply leave your integration the way one
  archived any other way does. Deleting tombstones the list, and there is no
  undo through this API. The items are not themselves tombstoned — they stay
  in the database and become unreachable, because every read of an item is
  scoped through its list.
- **`GET /lists` now says how many items each list holds** (§6). Two new
  fields, `itemCount` and `openCount`. `itemCount` is every item that has not
  been deleted, completed ones included; `openCount` is the ones not ticked
  off. Both are read-only — they are a property of the items, not a setting on
  the list. **Nothing you send today changes meaning**, and nothing you already
  read has moved. Added because a client that called `GET /lists` and stopped
  saw names with nothing to say items existed, which is indistinguishable from
  an empty list.
- **An event id may contain a colon, and `POST /events` will no longer mint
  one that does** (§7). One occurrence is addressed as `{eventId}:{date}`, and
  the path used to split at the FIRST colon — so an id like `mobrains:probe:1`,
  accepted on create and returned verbatim, could never be read, changed or
  deleted afterwards. The separator is now the LAST colon and only when a date
  follows it, which reaches those rows; `POST` answers 400 for an `id`
  containing a colon, so no more are made. **Nothing you send today changes
  meaning** — a UUID has no colon in it, and `{uuid}:{date}` still names one
  occurrence.
- **`GET /events/{id}` is new** (§5). The path took `PATCH` and `DELETE` and
  not `GET`, so you could change and remove an id you had no way to read back.
  Same family as `GAP-007`: an identifier accepted on one verb and refused on
  another.
- **`GET /whoami` is new** (§3). It reports the key's own scopes, the member it
  acts as, the household and the timezone. Nothing else changes; every route
  you already call is untouched.
- **`DELETE /events/{id}` takes `scope`, and a repeat is no longer refused
  outright** (§7). It used to turn away every repeating event, because the id
  could not say whether you meant one Tuesday or a year of them. `scope` says
  which. Nothing you send today changes meaning: a one-off event still deletes
  with no body.
- **`GET /events` is filtered to the calendars the key owner may see** (§4).
  A calendar somebody subscribes to can now be added *for one person* rather
  than for the household — Calendora asks who it is for at the time it is
  added. This endpoint returned all of them to every key, so an integration
  connected by one member answered with another member's work calendar, which
  is an answer no screen in the app would give. It now returns a personal
  calendar only to the member it belongs to, and returns nothing at all from a
  calendar hidden for the whole household. `GET /events/{id}` answers `404` for
  one you may not see — the same reply as an id from another household, because
  a refusal would confirm the event exists. **Breaking if you were counting on
  every event in the household:** you will see fewer, and the ones that
  disappear are the ones the key's owner cannot see either.
- **`GET /people` is filtered to what the key owner can see** (§4). It returned
  every contact in the household, including ones private to other members —
  names, relationships and birthdays a member cannot see on any screen in the
  app. **Breaking if you were counting on a full roster:** you will see fewer
  people than before, and the ones that disappear are the ones you were never
  meant to have.
- **Occurrences carry `readonly`, and a write to one is now refused** (§4, §7).
  An event that came from a calendar somebody subscribed to belongs to that
  feed. Calendora's own Update control re-fetches the feed and writes every
  matched event straight over the local row, so an edit you make against one
  disappears on the next refresh — no error, nothing linking the loss to the
  cause. The app stopped offering that edit in `v2608.0301`; **this API went on
  accepting it until now**, which was the same defect one surface along.
  `PATCH` and `DELETE` answer `400` with a sentence saying so. `readonly` is on
  the read shape so you can tell before you try. **Breaking only if you were
  editing imported events, in which case those edits were already being lost.**
- **A refused write now answers `409 conflict` rather than `400 bad_request`**
  (§2, §7). Retry-safety is machine readable: `conflict` is the only code you
  should retry on.
- **`PATCH /events/{id}` now accepts the occurrence id it was already handing
  out** (§7). It previously refused that form, so a client could read
  "gym, Tuesday the 16th" and had no way to edit that Tuesday. `GAP-007`.
- **`scope` is now required on every `PATCH`** — including a bare series id and
  an event that does not repeat. **Breaking.**
- **`due` replaced `dueAt`** on list items (§6). **Breaking.** `GAP-002`.
- **The 400-day range limit accepts exactly 400** (§5). It used to refuse it.
  `GAP-005`.
- **Types for every field** (§9). `GAP-006`.

---

## 1. Authentication

`Authorization: Bearer cal_…`

A key names **exactly one household**. No route takes a household id, because a
client that could name one could name somebody else's.

**Scopes are exact**: `calendar:read` does **not** imply `calendar:write`.

| Scope | Allows |
|---|---|
| `household:read` | The household, its members, and people |
| `calendar:read` | Reading events |
| `calendar:write` | Creating, changing and removing events |
| `lists:read` | Reading lists and their items |
| `lists:write` | Creating, changing and removing list items |

There is no wildcard scope, and there will not be one. A key that can do
everything is indistinguishable from a password, and it is handed to software
running in somebody's house.

**A key is not a member.** Changes made through one are recorded as the
integration — never as the person who created it.

---

## 1a. Rate limit

**120 requests per minute per key, with a burst of 240.**

**Every response carries your allowance**, not just the refusals:

```
RateLimit-Limit: 240
RateLimit-Remaining: 238
RateLimit-Reset: 1
RateLimit-Policy: "bucket";q=240;w=120
```

**`Limit` and `Remaining` describe the same thing** — the 240-request bucket —
so `Limit - Remaining` is what you have spent and a percentage means what you
would expect. The sustained rate is in `Policy`: 240 per 120 seconds is the
same as 120 a minute.

`Remaining` is floored, so it is a promise: told 1, you may send 1 more.
`Reset` is seconds until the bucket is full again — which is not the same
question as how long to wait after a refusal, and is usually larger.

Over the limit, every route answers **429** with `code: "rate_limited"` and an
**`x-retry-after`** header giving whole seconds. Retry the identical request
after that many seconds — this is not `forbidden`, nothing is wrong with your
request or your permissions, and changing either will not help.

```json
{ "error": "too many requests — try again in 3s", "code": "rate_limited" }
```

**One client request costs one token**, including an MCP tool call that fans
out to several handlers internally. The number describes what you can plan
against.

The bucket refills continuously rather than resetting on the minute, so there
is no edge to sit on and no advantage to aligning your polling to the clock. A
key that has been idle accumulates up to the 240 burst, which is there for a
reconnect that re-reads everything.

**A request carrying an INVALID key is not rate limited at all**, and that is
worth knowing rather than discovering. The bucket is charged after the key
resolves, so a wrong or revoked key answers **401 immediately, every time,
however fast you send.** Do not read a 401 as backpressure and sleep before
retrying: a misconfigured key would then look like a slow limiter instead of
an auth problem, and never surface as one.

**No consumer that exists comes close.** This is a ceiling on a runaway loop
and a leaked credential, not a budget to manage. If you are near it, the
change to make is fewer, larger reads — or `GET /stream`, which is one
connection rather than a poll.

---

## 2. Errors

Every route answers the same shape.

```json
{ "error": "a human sentence", "code": "bad_request" }
```

**Branch on `code`, never on the sentence.** Sentences change; codes do not — and
`bad_request` and `conflict` need opposite responses, so telling them apart by
reading English would break the first time a message is reworded.

| `code` | Status | Means |
|---|---|---|
| `unauthenticated` | 401 | No key, unknown, revoked, or expired — **deliberately indistinguishable** |
| `forbidden` | 403 | Valid key, missing scope. Names the scope, because re-issuing is actionable |
| `not_found` | 404 | No such thing — **or it belongs to another household** |
| `bad_request` | 400 | Your request is wrong. Says which part. **Do not retry unchanged** |
| `conflict` | 409 | Your request was **correct** and somebody else got there first. **Retry it** |
| `server_error` | 500 | Ours. File a gap |

A list or event in another household answers **404, not 403**: "that exists but
is not yours" is how ids get enumerated.

---

## 3. Reads

```
GET /whoami           household:read
GET /household        household:read
GET /members          household:read
GET /people           household:read
GET /events           calendar:read
GET /events/{id}      calendar:read
GET /events/{id}/leave-by  calendar:read
GET /lists            lists:read
GET /lists/{id}/items lists:read
GET /stream           household:read   (SSE)
```

### `GET /whoami`
```json
{ "key":       { "name": "Home Assistant",
                 "scopes": ["household:read", "calendar:read", …] },
  "household": { "id", "name" } | null,
  "member":    { "id", "name", "role" } | null,
  "timezone":  { "value": "Europe/London", "source": "key-owner" } }
```

**What this key is**, so you never have to find out by trying. Until now the
only way to discover your own scopes was to attempt a write and read the 403 —
which means learning what you may do by doing something you may not, and leaves
no way to hide a control that will always fail.

`member` is the household member your key acts as, and it is what `attendeeIds`
and `assignedMembershipId` are ids of. It is `null` when the person who created
the key has since left the household: the key still works for household-wide
reads, and a null is a better answer than a name that is no longer real.

**No email address and no user id, here or anywhere.** The membership id and
name say which member you are, which is all an integration needs.

### `GET /household`
```json
{ "household": { "id", "name", "description", "color" },
  "timezone":  { "value": "Europe/London", "source": "key-owner" } }
```

There is **no household timezone** — it is a per-person preference, so this
reports whose it is rather than pretending otherwise. Key your configuration on
`household.id`.

### `GET /members`
```json
{ "members": [ { "id", "name", "kind", "color", "role", "avatarId", "personId" } ] }
```

`name` is **already resolved** — a display-name override beats the stored name
server-side. Making a client work that out is how two clients call the same
person different things.

### `GET /people`
```json
{ "people": [ { "id", "name", "firstName", "lastName", "kind",
                "relationship", "birthday", "color" } ] }
```

**Not every contact in the household.** A contact can be private to the member
who added it, or shared with a named few. You get exactly the ones the person
who created your key can see in the app — their own, the household's, and any
shared with them. A private contact belonging to another member is absent, and
absent is indistinguishable from not existing; that is deliberate.

If the key's owner leaves the household, this narrows to the household's own
contacts rather than widening to all of them.

### `GET /stream`

Server-sent events. `event: ready` on connect, `event: changed` when something
changes, `: keep-alive` every 25 seconds.

**The payload is always `{}`.** It says that something changed, never what. On
`changed`, re-read whatever you care about.

---

## 4. Events are occurrences

One object per occurrence, not per rule.

```json
{ "occurrences": [ {
    "id": "{eventId}:{occurrenceKey}", "eventId", "occurrenceKey",
    "title", "description", "location", "icon",
    "isAllDay": false,
    "start": "2027-03-02T07:00:00.000Z", "end": "…", "timezone": "Europe/London",
    "repeats": true,
    "repeat": { "frequency": "weekly", "interval": 1, "weekdays": ["TU"], "endsOn": null, "count": null },
    "readonly": false, "importance", "travelMinutes", "travelFrom", "color": null, "status": "confirmed",
    "attendeeIds": ["membershipId", …],
    "tags": [ { "id", "name": "Personal", "color": null, "fromCalendar": false } ],
    "updatedAt": "2027-03-01T18:22:04.113Z"
} ] }
```

**`tags` are the key owner's own**, in name order, and `[]` when there are none
— an empty list is a statement, not a gap. An event's tags are personal in
Calendora: two members can tag the same event differently, and a key sees only
its owner's. A tag is on the event row, so every occurrence of a repeat carries
the series' tags. `fromCalendar: true` is the tag a subscribed calendar puts on
everything it brings in; it cannot be taken off one event (§7).

**`updatedAt` is the SERIES row's stamp**, so every occurrence of a repeat
carries the same one — an occurrence is computed from the rule rather than
stored, so there is no per-occurrence write to stamp. A per-day change writes
an override or detaches that day into its own event, and both move a row with
its own `updatedAt`.

It is what lets you tell an event you wrote from one you wrote and somebody has
since edited. If you offer an undo for something you created, compare this
before deleting: a stale undo that cannot tell those apart removes the person's
edit rather than your creation. Not writable — see §9.

**`readonly: true` means the event came from a subscribed calendar** and cannot
be changed through this API — see §7. It is a fact about where the event came
from, not a setting: you cannot make an imported event editable by asking, and
there is no lock to apply to a native one.

**Not every subscribed calendar reaches every key.** One added for a single
member is returned only to that member's key, and one hidden for the whole
household is returned to nobody. So two keys in the same household can
legitimately see different calendars, and an event missing from your answer is
not necessarily missing from Calendora.

Sorted by `start`. **The RRULE is never exposed** — `repeats` is a boolean, and
`repeat` is the pattern in the same shape `POST /events` takes (§7), or `null`
for a one-off, or `{ "frequency": "custom" }` for a rule that shape cannot say.

**`start` and `end` are always instants, including when `isAllDay` is true.**
`timezone` is the event's own authored zone. An all-day event must be rendered
as a *date* derived using that zone — not the viewer's, and not UTC. Converting
in the viewer's zone is how a birthday moves a day.

**An all-day `end` is EXCLUSIVE** — the first instant not in the event. One day
on 10 August is `2027-08-10T00:00:00` → `2027-08-11T00:00:00`. This is the RFC
5545 `VALUE=DATE` convention, so no translation is needed in either direction.

**`attendeeIds` is resolved per occurrence.** Somebody who dropped out of one
Tuesday is absent from that Tuesday and present on the others.

**An occurrence with an empty `attendeeIds` belongs to the whole household** and
is never filtered out by `?member=`.

### `GET /events/{id}` → `200 { "occurrence": { … } }`

One occurrence, in **exactly** the shape the list returns — same fields, same
values, from the same code. List a day, open one event out of it, and nothing
changes under you.

`{id}` is either an occurrence id (`{eventId}:{date}`) or a bare event id, which
means the series' own first occurrence. A date the series does not fall on is a
**400**, not a 404: the event exists, and that day is simply not one of its
occurrences — it may have been cancelled, or guessed.

This is the read that matches the writes on the same path. It did not exist
before, so an id could be changed and removed but not read back.

---

### `GET /events/{id}/leave-by` → `200 { eventId, occurrence, start, travelMinutes, travelFrom, leaveAt, passed, words }`

When to leave, from the event's own `travelMinutes`: `leaveAt` is `start`
minus it, `passed` says whether that moment has gone, and `words` is the line
the app's Today card shows ("Leave by 2:35 PM · 25 min drive", or "Leave home
at 2:35 PM · 25 min drive" when `travelFrom` is `"home"`), written in the key
owner's zone. **No travel time, or an all-day event, is `travelMinutes`,
`leaveAt` and `words` all `null`** — not a guess, and not an error. It is not a
route from wherever the person is: Calendora does not know that.

The id is an event or one occurrence (`{event}:{date}`). A plain id of a
**repeating** event answers for its **next** occurrence (the first one still to
end), and `occurrence` says which; `404` when a repeat has none left.

## 5. Asking for a range

`GET /events?from=YYYY-MM-DD&to=YYYY-MM-DD&member={membershipId}`

`from` and `to` are **days, not instants**, resolved in the key owner's
timezone. An instant is rejected: it would mean a different day depending on the
zone it was written in.

**Both ends are inclusive**, and the limit is the difference between them:

| | |
|---|---|
| `to = from + 400 days` | accepted |
| `to = from + 401 days` | 400 |
| `from = to` | a single day |

A longer range is **rejected rather than truncated** — a client that asked for
five years and got one would believe the calendar was empty after that.

---

## 6. Lists

### `GET /lists`
```json
{ "lists": [ { "id", "name", "description", "type", "color", "icon", "isArchived",
               "itemCount", "openCount" } ] }
```

`itemCount` counts every item that has not been deleted, ticked-off ones
included. `openCount` counts the ones still open. Neither is writable.

### `GET /lists/{id}/items`
```json
{ "listId",
  "sections": [ { "id", "name", "position" } ],
  "items": [ { "id", "text", "quantity", "notes", "isChecked",
               "sectionId", "position", "due", "repeats", "listId",
               "assignedMembershipId", "assigneeName", "completedAt",
               "updatedAt" } ] }
```

**`repeats` says whether the item is a chore.** A repeating item is ticked off
by moving its `due` to the next time it comes round, not by finishing it (§7).
Chores due today are the items with `repeats: true` and a `due` on or before
today in the key owner's zone (`GET /whoami`). The rule is not returned, so
`repeats` is not writable either; a repeat is set in the app.

**`listId` is the list the item is on**, the same as the one in the path. It is
there so an item read on its own still says where it lives, and `PATCH` takes
it to move the item (§7).

**`assigneeName` is the assignee's name, resolved for you**, and `null` when
nobody is assigned. It is here and there is deliberately no `sectionName`,
under one rule: **a name is denormalized onto the item only when the id cannot
be resolved from the same response.** `sections` is right there beside the
items with every id and name, so grouping by shop is a walk over that array.
The roster is household-scoped, is not in this payload, and never will be — so
`assignedMembershipId` is the one id here you could not otherwise resolve
without a second call. Not writable; see §9.

`updatedAt` is the server's clock on the last write to that row, and
`completedAt` is when it was ticked — `null` while it is open. They are the two
a merging consumer needs: without `updatedAt` there is no way to tell which
items have not moved since you last looked, so every pass has to re-reason
about the whole list. Neither is writable; see §9.

Both arrays arrive **pre-sorted by `position`, which is a fractional index — a
STRING.** Compare it as a string; parsing it as a number gives an order nobody
arranged. Two rows can share a `position`; they come **by `id`**, compared as a
plain string — the order both apps show. Sort the same way if you re-sort.

### `due` carries day-versus-moment in its FORM

| Value | Means |
|---|---|
| `"2027-09-03"` | due that **day** |
| `"2027-09-03T14:30:00.000Z"` | due at that **moment** |
| `null` | no due date |

**This replaced `dueAt`, and the replacement is the point.** An instant cannot
say which it is: `2027-09-03T22:00:00Z` is either "due on the 4th" or "due at
22:00". The write takes the same two forms, so an item read and written back
unchanged really is unchanged.

There is no separate boolean. A boolean beside the value has a state where the
two disagree, and a field that can contradict itself eventually will.

---

## 6a. Meals and dinner

`meals:read` / `meals:write`. A meal is not a calendar event — nobody is
invited and nothing reminds — and never appears in `/events`.

### `GET /meals?from=YYYY-MM-DD&to=YYYY-MM-DD` (or `?week=`, `&weekStart=0-6`)

Every day in the range (inclusive, at most 400 days, refused rather than
truncated) with its `meals`, the `lines` each reads as on the calendar
(`"Dinner: Chili"`, `"Dinner (takeout): Pizza, wings"`) and the `headlines`
each reads as on Today. A meal: `id`, `day`, `slot`, `recipeId`, `text`,
`servings`, `cookedAt`, `leftoverOf`, `kind`, `title`, `line`, `headline`,
`sourceLine`, `serveAt`, `serveTz`, `ownerMembershipId`, `dinerIds`,
`placeText`, `orderText`, `fulfillment`, `notes`, `rating`, `idea`, `dishes`
(`id`, `name`, `role`, `recipeId`, `recipeTitle`, `servings`, `gear`,
`method`, `cookMinutes`, `restMinutes`, `frozen`, `thawHours`,
`ingredientId`) and `plannedBy` (`{ type, name }`). Fixture: `meals-range`.

### `GET /dinner?day=YYYY-MM-DD` → `200 { "dinner": { … } }`

The dinner card for a day, today in the key owner's zone when `day` is left
out. `state` (`unplanned` | `planned` | `done`), `headline` (the sensor's state;
`"Not planned"`), `digestLine`, `meals[]` (each with `headline`, `line`,
`label`, `ownerPhrase` — "Mike's cooking" — `diners { ids, names, source }`,
`serveAt`, `serveTz`, `dishes`, `placeText`, `notes`, `cookedAt`, `sentence`
for a voice answer), and `phase` / `placement` / `tomorrow` for today only
(null on other days). Fixtures: `dinner-cook`, `dinner-quick`,
`dinner-takeout`, `dinner-leftovers`, `dinner-out`, `dinner-skip`,
`dinner-words-only`, `dinner-unplanned`.

**`serveAt` is a wall time, not an instant.** To make the sensor's `serve_at`
attribute an instant, read `serveAt` in `serveTz` on that `day`.

### `POST /dinner` → `201 { saved, meal, parsed, doubts, dinner }`

Plan a dinner from one line: `{ day, line, onExisting?, dryRun?,
idempotencyKey?, confirmedByPerson?, … }`, with any meal field beside the line
overriding what was read. `onExisting` is `refuse` by default — a day that
already has a dinner is left alone, `200 { saved: false, existing }`
(`write-dinner-refused-existing`). `replace` replaces **only a dinner this key
planned** unless `confirmedByPerson: true`; otherwise `403`. The same
`idempotencyKey` is the same dinner: a retry is `200 { saved: false,
replayed: true }` and writes nothing. Fixtures: `write-dinner-plan`,
`write-dinner-plan-doubts`.

### Also

`GET /dinner/parse?line=` (the parser alone, nothing written; `dinner-parse`) ·
`POST /meals` (now also takes `line`, `dishes` and the dinner fields;
`write-meal-legacy-text` pins that words alone never become dishes) ·
`PATCH /meals/{id}` (`dishes` REPLACES the whole set) · `DELETE /meals/{id}` ·
`POST /meals/{id}/dishes` · `PATCH|DELETE /meals/{id}/dishes/{dishId}` ·
`POST /meals/{id}/dishes/{dishId}/move` `{ beforeId | afterId }`.

Phase 2: `GET|POST /places` and `POST /places/{id}/archive` (`places`),
`GET|POST /gear` and `POST /gear/{id}/archive` (`gear`), `GET|POST
/favorites` and `POST /favorites/{id}/plan` (`favorites`), `GET /meals/ideas`
(`meals-ideas`), `GET /meals/{id}/check`, `POST /meals/{id}/add-to-list`,
`POST /meals/{id}/prep/{prepId}/complete`.

Phase 3: `GET /dinner/suggestions?day=` (`dinner-suggestions`): at most four,
each with one checkable reason; nothing is planned. The card's `timeline`
is computed from the minutes the household entered (a recipe's own times,
else a dish's `cookMinutes`, plus `restMinutes`) and a gear's
`preheatMinutes`; a dish with none is listed in `untimed`, never guessed.

---

## 7. Writes

```
POST   /events                        calendar:write
PATCH  /events/{id}                   calendar:write
DELETE /events/{id}                   calendar:write
POST   /lists/{id}/items              lists:write
PATCH  /lists/{id}/items/{itemId}     lists:write
DELETE /lists/{id}/items/{itemId}     lists:write
```

**Semantics, everywhere:** partial. An omitted field is untouched, an explicit
`null` clears, and the server never reads-merges-writes on your behalf. An
unknown field is a **400 that names it** — never a silent drop, because a third
party cannot notice one and files it against the wrong project.

**`position` never appears in a write body.** Ordering is server-owned; see §8.

### `POST /events` → `201 { "id" }`

```json
{ "id": "optional — yours to choose",
  "title": "Bin day",
  "start": "2027-08-11"  |  "2027-08-11T07:00:00.000Z",
  "end":   "2027-08-12"  |  "2027-08-11T07:15:00.000Z",
  "timezone": "Europe/London",
  "description": null, "location": null, "icon": null,
  "importance": 5, "travelMinutes": 20, "travelFrom": "home",
  "attendeeIds": ["019fd7…"] }
```

**`attendeeIds` puts the event on somebody's calendar. This is new** — it was
returned by every read and refused by every write, so an event created through
this API belonged to the whole household whichever person the caller meant.

- Omit it and the event belongs to the household. That is the old behaviour and
  it is unchanged for callers that never send the field.
- Send `[]` to say "everybody" deliberately.
- Ids come from `GET /members`. **An id that names nobody is a 400 that names
  it** — never silently dropped, because an event on no one's calendar looks
  exactly like a successful create.

**Send an `id`.** It is optional and honoured. A request that times out cannot
be told from a reply that was lost, and a retry without an id creates the event
twice; with one, the retry lands on the same row.

**An id must not contain a colon, and that is a 400.** `{eventId}:{date}` is
how one occurrence is addressed, so a colon inside the id itself competes with
the API's own composite form. It used to be accepted and returned unchanged,
after which nothing could name the event again — a real household ended up with
two events on its calendar that no caller could remove. If you mint ids with a
prefix, use a hyphen.

**`start` and `end` say whether they are days or moments by their FORM.** A date
is a day, an instant is a moment, and `isAllDay` follows. Sending `isAllDay`
that disagrees with the form is a 400, as is mixing a date with an instant.

That is not a nicety. A client meaning "all day on the 11th" naturally sends
`2027-08-11T00:00:00Z`; resolved in a New York event's own zone that instant is
the evening of the **tenth**, and the event lands a day early with no error
anywhere. A date has no such reading.

### `PATCH /events/{id}` → `200 { "id", "scope", "result" }`

**`{id}` takes two forms**, and they mean different things:

```
PATCH /api/v1/events/019fd9…                the series
PATCH /api/v1/events/019fd9…:2027-03-16     one occurrence of it
```

The second is exactly the `id` `GET /events` returned. **This is new** — it was
previously refused, which meant the API handed out an identifier it would not
accept back.

**The split is at the LAST colon, and only when a date follows it.** Anything
else is read as an event id in one piece, so a row whose own id contains a
colon is still reachable. If both readings are possible, the occurrence one is
tried first and the whole string second.

`attendeeIds` is accepted here too, and `scope` decides what it means:

| `scope` | What changing `attendeeIds` does |
|---|---|
| `all` | Changes the roster for the whole series, every occurrence |
| `this` | Records one day's answer, WITHOUT taking that day out of the repeat |
| `following` | Splits the series; the new one carries the roster you sent |

Omitting `attendeeIds` leaves the roster alone — the same partial rule as every
other field. Sending `[]` clears it.

#### `scope` is a BODY FIELD, and it is required

Not a query parameter. It sits alongside the fields being changed:

```json
{ "scope": "this", "location": "The pool" }
```

| `scope` | Means |
|---|---|
| `"this"` | Only this occurrence. It is taken out of the repeat and changed on its own |
| `"following"` | This one and every one after it. The old repeat ends the millisecond before |
| `"all"` | The whole series, shifted by however far this occurrence moved |

**Required on every `PATCH`** — including a bare series id, and including an
event that does not repeat. On a one-off all three mean the same thing and it is
still required, so the same client code keeps working when somebody makes the
event repeat. The server never guesses which occurrences you meant.

Omitting it is a 400 naming `scope`.

#### The reply, and the field carrying the new id

```json
{ "id": "019fdcd4-72d2-7f60-994f-2437297f7d03",
  "scope": "this",
  "result": "this one was taken out of the repeat and changed on its own" }
```

**`id` is the row to address next.** For `scope: "this"` and
`scope: "following"` the server **creates a row**, and `id` is that new row's
id — **not** the id you sent. A client that kept using the series id afterwards
would aim its next request at the wrong row.

| `scope` | `id` in the reply | `result` |
|---|---|---|
| `"this"` | the **new** standalone event | `this one was taken out of the repeat and changed on its own` |
| `"following"` | the **new** series | `the repeat was ended and a new one started from this occurrence` |
| `"all"` | the same series id you sent | `the whole series was changed` |

`result` is prose and may be reworded. **Branch on `scope`, not on `result`.**

After `"this"`, the original series gains an exception for that date and the new
row stands alone. After `"following"`, the original series ends the millisecond
before this occurrence and the new one carries the rule forward. In both cases
a subsequent `GET` returns occurrences from both rows, with different `eventId`s.

#### Failures particular to `PATCH`

| Case | Response |
|---|---|
| No `scope` | 400 naming `scope` |
| Body with only `scope` | 400 — a well-formed request that changes nothing |
| A date the series does not fall on | **400, not 404** — the event exists; that day is not one of its occurrences |
| An id with something other than a date after the colon | 400 |
| An event id that does not exist | 404. **A `PATCH` never inserts** |
| Somebody else changed the event between your request arriving and it being written | **409 `conflict`. Nothing was applied.** See below |

#### When somebody else got there first

```json
{ "error": "somebody else changed this a moment ago, so nothing was saved",
  "code": "conflict" }
```

**Status 409, `code: "conflict"`.** This is the *only* code you should retry on,
and it is deliberately not `bad_request`: that one means the request was wrong
and sending it again will fail the same way. Here the request was right.

Two facts, and both are contract rather than implementation:

1. **Nothing was applied — not part of it.** `scope: "this"` and
   `scope: "following"` each write two rows: the original series changes and a
   new row appears. If the first is refused, the second is never attempted. A
   detach that half-applied would leave the series without its exception while
   the standalone row existed, and that day would show **twice**.
2. **Retrying is the correct response**, and it is safe. The second attempt
   reads the event as it now stands, so it either succeeds or refuses again for
   the same reason. There is no state to clean up and no partial write to
   reconcile.

It means the household edited that event in the same moment. Retrying once
immediately is reasonable; retrying in a loop is not, because the other writer
may still be going.

**This is deliberately different from the ordinary conflict behaviour.** Two
devices editing one row through the sync protocol resolve by last-write-wins
and nobody is told, because the loser pulls the winner's version a moment
later. A request that answers once has nobody to pull anything, so it is told.

### Imported events are refused by both writes

`PATCH` and `DELETE` on an event with `readonly: true` answer `400` with a
sentence naming the reason. **The one exception is the drive:** a `PATCH`
carrying only `travelMinutes` and `travelFrom` is applied, because the drive
time is the household's, not the calendar's. On a repeat it needs
`scope: "all"`. Not `404`: "not found" would send you looking for a
bad id, when the id is fine and the event is simply not yours to change. The
calendar it belongs to is the source — remove or hide that calendar in
Calendora instead.

### `POST /events/{id}/tags` → `201 { "eventId", "tag", "tagId" }`

`{ "tag": "Personal" }` — one of the key owner's own tags, by name
(case-insensitive) or id. A name the owner has no tag for is a `400` listing the
ones they have; this never creates a tag. Tagging twice is one tag (`200` the
second time). `{id}` may be an occurrence id; the tag goes on the series.

**Allowed on imported events.** The refusal above is about an event's fields,
which a feed refresh writes over. A tag is its own row, and a refresh leaves it.

### `DELETE /events/{id}/tags/{tag}` → `200 { "eventId", "removed", "tag"? }`

`{tag}` is the tag's id or name. Removing a tag the event does not have is
`removed: 0`, not an error. A `fromCalendar` tag is a `400` saying which
calendar applies it: it cannot come off one event.

### `DELETE /events/{id}` → `200 { "id", "deleted": true }`

A tombstone, so the removal reaches every device.

Body, when the event repeats:

```json
{ "scope": "this" | "following" | "all" }
```

**`scope` is required when the event repeats, and unnecessary when it does
not.** An event that happens once is entirely gone whichever scope you name, so
a bare `DELETE` on one keeps working exactly as it did — this adds nothing you
have to send. A repeat with no scope is a `400` naming the three: which of them
you meant is not in the id, and each is a different write.

Only one of the three is a delete:

| scope | what happens | the row |
|---|---|---|
| `this` | that one occurrence is cancelled | series stays, date added to its exceptions |
| `following` | the repeat stops from that occurrence on | series stays, end date set to a millisecond before it |
| `all` | the series is removed | tombstoned |

`following` on the **first** occurrence removes the series instead of capping
it there: a repeat that ends before it starts generates no days, appears
nowhere, and could never be reached again.

All three answer `{ "deleted": true }`. That is deliberate — from your side all
three removed what you named, and the distinction between an exception, an end
date and a tombstone is not one you should build on.

**`this` and `following` are reversible in the app; `all` is not.** A cancelled
day can be restored and a stopped repeat resumed, because the series row is
still there. Nothing restores a tombstone.

### `POST /lists/{id}/items` → `201 { "id" }`

```json
{ "id": "optional", "text": "Milk", "quantity": "2", "notes": null,
  "isChecked": false, "due": "2027-09-03" | "2027-09-03T14:30:00.000Z" | null,
  "sectionId": null, "assignedMembershipId": null }
```

`due` takes the two forms of §6. A day is stored anchored at **9am** in the
caller's zone, not midnight — "due Thursday" means during Thursday, and a
midnight deadline is late the moment Thursday starts.

**`assignedMembershipId` is checked against your household's roster**, on both
this and `PATCH`, and an id that names nobody in it answers **400** rather than
being stored:

```json
{ "error": "no member of this household has the id …", "code": "bad_request" }
```

This is the same rule `attendeeIds` has always had, and it arrived here later.
Use a `member.id` from `GET /members`. `null` is always fine and clears the
assignment — nobody's job is a real answer.

The refusal does not distinguish an id that exists nowhere from one belonging
to another household. Saying which would confirm that an id is real, and that
is how rosters get enumerated one guess at a time.

### Sections — the shops on a list

```
GET    /lists/{id}/sections          → { "listId", "sections": [ { "id", "name", "position" } ] }
POST   /lists/{id}/sections          { "name" }            → 201 { "id", "name" }
PATCH  /lists/{id}/sections/{sid}    { "name" }            → 200 { "id", "name" }
DELETE /lists/{id}/sections/{sid}    { "reassign_to"? }    → 200 { "id", "deleted", "moved", "movedTo" }
POST   /lists/{id}/sections/reorder  { "order": [ … ] }    → 200 { "listId", "sections" }
```

`GET /lists/{id}/items` still returns the sections beside the items, and that
is the call to use for a read. The collection is here so there is somewhere to
POST, and for a client that wants a shop picker without fetching every item.

**A list cannot hold two sections with the same name**, compared ignoring case
and spacing. Create or rename onto an existing one answers **409** naming it.
Renaming a section to a different spelling of its own name is allowed — that is
how you fix the capitals on a heading.

**Reorder takes the WHOLE order**, every id exactly once. A partial order is
refused naming what is missing; a repeat is refused naming what is repeated.
You say the order and the server mints the keys — the same reason `position`
never appears in a write, and what lets two clients reorder at once and agree.

**DELETE refuses while the section holds items**, with the count. Send
`reassign_to` with another section id to move them, or `null` to ungroup them
on purpose. **The items are never deleted with the section**, and the reply
says how many moved and where.

### `POST /lists/{id}/items` — the shop by NAME

Send `sectionName` instead of `sectionId` and it resolves against the sections
this list already has. Sending both is a 400.

```json
{ "text": "Oat milk", "sectionName": "TRADER JOE'S" }
→ 201 { "id", "sectionId": "…", "sectionName": "Trader Joe's" }
```

**It never creates one.** A name matching nothing answers 400 **naming the
sections that exist**, so the answer to a typo is inside the error. Creating on
a miss would make "Publx" a shop that only somebody in the household can
remove, reached by failing to name a narrower outcome.

Matching ignores case and collapses whitespace. **Punctuation is significant**
— `Sam's` and `Sams` are two shops. On a match you get the household's own id
and its own spelling back, as above: the string you sent is never written.

### `POST /lists` → `201 { "id" }`

```json
{ "id": "optional", "name": "Chores", "type": "todo",
  "description": null, "color": null, "icon": null, "isArchived": false }
```

`type` is `shopping` or `todo` and defaults to `shopping` — the kinds of list
the app shows. The column also holds `packing`, `checklist` and `custom`, which
no screen renders yet, so writing one is a 400 rather than a list nobody sees. `name` is required and is trimmed. `position` is
computed here — the new list goes at the end — and is never accepted in a
body, the same rule items follow (§8).

### `PATCH /lists/{id}` → `200 { "id" }`

Same fields minus `id`. Partial: an omitted field is untouched, an explicit
`null` clears `description`, `color` and `icon`. Set `isArchived` to put a list
away or bring it back.

### `DELETE /lists/{id}` → `200 { "id", "deleted": true }`

A tombstone. **There is no undo through this API.** The list stops being
readable and its items go with it — they are not themselves deleted, but every
read of an item is scoped through its list, so they are unreachable. If the
list might be wanted again, `PATCH` with `isArchived: true` instead.

### `PATCH /lists/{id}/items/{itemId}` → `200 { "id" }`

Same fields, minus `id`. A body of `{}` is a 400.

Setting `isChecked` stamps the checked time with it — two halves of one fact.

**Except on a repeating chore.** `isChecked: true` on an item that repeats moves
its `due` to the next time it comes round and leaves it unchecked — done until
next time, as in the app. Read it back to see the new `due`; the response is the
same `{ "id" }`.

**`listId` moves it** to another of the household's lists. A section that
belonged to the old list is cleared, because shops are per list.

**Both ids are checked, and against each other.** An item that exists but is on
a **different list** answers 404.

### `DELETE /lists/{id}/items/{itemId}` → `200 { "id", "deleted": true }`

A tombstone.

---

## 8. Two capabilities deliberately absent

Recorded with reasoning so they are not raised as oversights.

**Reordering list items.** There is no move endpoint and there will not be one.
Calendora's list sections are shops — PUBLIX, COSTCO — and a flat surface
dragging an item has two possible outcomes: it silently moves between shops, or
it snaps back. The information needed to choose is not in the request.
Reordering is the only capability whose absence costs nothing a user can
perceive: the list still shows every item and still checks off.

**But GROUPING is not reordering, and grouping has always been allowed.**
`sectionId` is writable on both item routes (§7) and always has been. Setting
it says *which shop this belongs to* — the caller names the destination
outright, so the ambiguity above is simply not present. What stays refused is
saying *"put this above that"*, where the destination is implied by a
neighbor and a flat surface cannot say which section it meant.

If your surface can show sections, moving an item between them is a supported
write today. If it cannot, do not synthesize one from a drag.

**Changing who is coming, per occurrence.** Writable: `PATCH /events/{id}`
with an occurrence id and `scope` — see §7 for what each scope does to
`attendeeIds`. (This paragraph said "not writable here yet" after that shipped.)

---

## 9. Types

Every field, derived from the handlers rather than from intent.

| Field | Type | Notes |
|---|---|---|
| every id, `eventId`, `listId`, `sectionId`, `personId`, `avatarId`, `assignedMembershipId`, `attendeeIds[]` | `string` | Opaque. **Do not parse one** |
| `name`, `title`, `text` | `string` | Never null, never empty |
| `description`, `location`, `notes`, `quantity`, `icon`, `color`, `relationship`, `firstName`, `lastName` | `string \| null` | Null means not set |
| `kind` | `"person" \| "pet" \| "other"` | Members and people alike |
| `role` | `"owner" \| "admin" \| "member" \| "guest"` | |
| `type` (lists) | `"shopping" \| "todo" \| "packing" \| "checklist" \| "custom"` | Read as stored. Written as `shopping` or `todo` only |
| `isAllDay`, `repeats`, `isChecked`, `isArchived` | `boolean` | Never null. On an item, `repeats` means a chore |
| `importance` | `integer 1–10 \| null` | **Null is not zero and not "normal"** — nobody set one |
| `travelMinutes` | `integer ≥ 0 \| null` | Whole minutes |
| `travelFrom` | `string \| null` | `"home"`, the address the drive was worked out from, or null. Sent only with `travelMinutes`; a `travelMinutes` without it clears it |
| `color` (events) | `string \| null` | `"hue:tone:chroma"`; null means no choice made |
| `status` (events) | `"confirmed" \| "tentative" \| "cancelled"` | Never null |
| `repeat` | `object \| null` | `{ frequency, interval, weekdays[], endsOn, count }`; `frequency: "custom"` when the pattern cannot be said this way. Create-only |
| `start`, `end` | `string` | ISO 8601 instant, always — even when `isAllDay` |
| `timezone` | `string` | IANA name, the event's own |
| `birthday` | `string \| null` | `YYYY-MM-DD` **or** the year-less `--MM-DD`. Never an instant |
| `due` | `string \| null` | `YYYY-MM-DD` **or** an ISO instant — the form is the meaning |
| `position` | `string` | A fractional index. Compare as a string |
| `occurrenceKey` | `string` | `YYYY-MM-DD`, in the event's own zone |
| `scope` | `"this" \| "following" \| "all"` | Request only |

**On a read, every documented field is always present** — absent and null are
the same thing. On a **write** they are not: omitted means untouched, `null`
clears.

### Why "do not parse one" is the hard rule in that table

Most of our ids are UUIDv7, whose first twelve hex characters are a 48-bit
millisecond timestamp. **So they really are time-ordered, and that is the
problem**: the property is true, which makes reading one feel like evidence
rather than like a guess. A rule that only says "opaque" reads as a caution
about coupling, and gets set aside the moment somebody has a question the
prefix appears to answer.

Concretely, and from a real mistake made while auditing this very calendar:
`01a06c14…` and `01a06c15…` look adjacent. They are **93 seconds apart**. That
eighth hex digit is worth 65,536 ms, so two ids differing only there are
between roughly one and two minutes apart — never "the same moment". The wrong
reading turned two people doing the same errand a minute and a half apart into
a single suspicious event, and it took a database query to undo.

What a shared prefix **does** tell you: the two rows were created in the same
rough window, of a size that depends on which digit differs.

What it **does not** tell you: that they were created together, by one action,
by the same actor, in either order, or that the gap is small in human terms.

If you need to know when something was made or last changed, read `updatedAt`.
That is what it is for, and it is a real answer rather than an inference.

---

## 10. Fixtures

`fixtures/api-v1/` in the Calendora repository — **76 request/response pairs**,
generated by replaying real requests through the real handlers, covering every
endpoint above and every failure in §2 and §7.

Vendor that directory and test against it. Calendora replays every case on its
own build too, so a contract change breaks the build of whoever made it before
it reaches you.

The pairs for this release's change:
- **Chores:** `list-items` and `list-items-after-check` carry `repeats`, and `lists`
  counts the new item.
- **Tags and drives:** `events`, `event-one`, `events-filtered-by-member` and
  `events-max-range` have the tagged client dinner and the drives.
- **New pairs:** `event-leave-by`, `event-leave-by-none`, `write-event-tag`,
  `write-event-untag` and `error-untag-from-calendar`.

`Bearer cal_<key>` and `<new-id>` are placeholders. **No fixture contains a
working credential**, and a server-minted id is redacted because it differs on
every generation — what is pinned is that the reply carries a *new* id, not its
value.

**The fingerprint at the top of this file covers that directory.** If it does
not match the fixtures you have, one of us is out of date — file a gap rather
than guessing which.

**How it is computed**, so you can check it yourself: take every `*.json` file
in `fixtures/api-v1/`, sorted by file name as plain strings. Feed one SHA-256
the file NAME, then the file's raw bytes, for each in that order. The
fingerprint is the first 16 hex characters of the digest. `README.md` is not
included. Calendora's build runs the same computation against this file.

---

## 11. When something disagrees with this file

**File it in `docs/API-GAPS.md` rather than adapting to it.** Adapting silently
is how two ends drift apart with both builds green, and it is the failure this
document and the fixtures exist to prevent.

Eleven gaps have been filed this way: GAP-001 to GAP-008, and GAP-019 to
GAP-021, which this extract closes. Two of them were defects in Calendora that
no internal test had caught.
