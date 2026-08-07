# What Home Assistant's todo platform needs from `/api/v1`

**Status:** analysis only. Nothing is built, and nothing here is a design.

**Scope, deliberately narrow.** This describes the *shape of the hole* — what
Home Assistant's todo platform requires in order to work, and what it does when
those requirements are not met. It does not propose routes, field names or
payloads. How Calendora fills the hole is Calendora's decision; this document
exists so that decision is made with the constraints visible rather than
discovered afterwards.

Everything below is checked against the todo platform as shipped in Home
Assistant 2026.8 (`homeassistant/components/todo/`), not from memory, and against
`docs/API-SURFACE.md` §4a for the list-item shape as it exists today.

---

## 1. Why this is worth reading before writes are designed

Two of the findings are the kind that get answered by accident:

- **Home Assistant has two separate due-date capabilities**, and today's item
  shape can only express one of them.
- **Home Assistant hands an integration a *complete* item on every update**, not
  a diff — so a naive write path silently destroys the fields Home Assistant has
  never heard of.

Neither is expensive to accommodate while the write routes are being designed.
Both are expensive afterwards, because by then somebody's shopping list has lost
its quantities.

---

## 2. The feature flags

Home Assistant gates its todo services on `TodoListEntityFeature`. There are
seven flags. **The UI and the service field filters key off them**, so a flag we
declare and cannot honour becomes a button that silently does nothing — which is
worse than the button being absent.

| Flag | What it turns on for the user | What it needs | Declare? |
|---|---|---|---|
| `CREATE_TODO_ITEM` | `todo.add_item`, the "add" box in the UI, and the `HassListAddItem` voice intent | Create an item on a list, returning enough to identify it | **Blocked** — needs writes |
| `UPDATE_TODO_ITEM` | `todo.update_item`, ticking an item in the UI, and `HassListCompleteItem` | Update an existing item, including its checked state | **Blocked** — needs writes |
| `DELETE_TODO_ITEM` | `todo.remove_item`, `todo.remove_completed_items`, and `HassListRemoveItem` | Delete a known item by id | **Blocked** — needs writes |
| `MOVE_TODO_ITEM` | Drag-to-reorder in the UI, and the `todo/item/move` WebSocket command | Place an item between two others — see §5 | **Blocked**, and see §5 |
| `SET_DUE_DATE_ON_ITEM` | The `due_date` field on `todo.add_item` / `update_item` — a **day**, no time | Store a due *day* distinguishable from a due *instant* | **Blocked** — see §4 |
| `SET_DUE_DATETIME_ON_ITEM` | The `due_datetime` field — a **timestamp** | Store a due *instant* | **Blocked** — see §4 |
| `SET_DESCRIPTION_ON_ITEM` | The `description` field | Write free text on an item | **Blocked** — needs writes |

**Nothing is declarable today.** `/api/v1` is read-only (§7), so the honest
entity right now declares zero flags and is a read-only list. That is a real,
shippable thing — see §8.

### The two due-date flags are not interchangeable

This is the finding that matters most, because it looks like duplication and is
not. In `homeassistant/components/todo/__init__.py`, `due_date` and
`due_datetime` are two different service fields that write to **one**
`TodoItem.due` attribute, validated with `has_at_most_one_key` so a caller may
send one or the other, never both. `due_date` validates as a `date`;
`due_datetime` validates as a `datetime` and is converted to local time.

So `TodoItem.due` is `date | datetime | None`, and which one it holds is
meaningful: "due Tuesday" and "due Tuesday at 16:00" are different states a user
can express and see. Declaring only `SET_DUE_DATE_ON_ITEM` removes the time field
from the service and the UI; declaring only `SET_DUE_DATETIME_ON_ITEM` forces
every due date to carry a time it may not have.

---

## 3. The item shape

`TodoItem` has five fields. Mapped against §4a's item shape:

| `TodoItem` | Type | §4a item field | Fit |
|---|---|---|---|
| `uid` | `str` | `id` | Clean |
| `summary` | `str` | `text` | Clean |
| `status` | `needs_action` \| `completed` | `isChecked` (bool) | Clean — a boolean is exactly two states |
| `description` | `str \| None` | `notes` | Clean |
| `due` | `date \| datetime \| None` | `dueAt` (ISO instant or null) | **See §4** |

Reading is unblocked. Note that **the flags gate writing, not reading**: an
entity with no features at all still returns `due` and `description` from
`todo.get_items` and shows them in the UI. A read-only list loses nothing except
the ability to change things.

### Fields Calendora has that Home Assistant does not

`quantity`, `sectionId`, `position`, `assignedMembershipId`. Home Assistant's
todo model has no equivalent for any of them, and there is nowhere honest to put
them — folding `quantity` into `text` would corrupt the item the first time it
round-trips.

This creates the hazard in §6. It is not an argument for adding them to Home
Assistant's model, which is not ours to change.

---

## 4. `dueAt` needs the same treatment events just got

§4a defines `dueAt` as "an ISO instant or null". Home Assistant needs to know
whether a due date is a **day** or an **instant**, and an instant alone cannot
answer that: `2026-08-10T22:00:00Z` is either "due on the 11th" or "due at 22:00
UTC", and nothing in the value says which.

**This is the same problem the calendar just solved.** Events carry `start`/`end`
as instants plus an `isAllDay` boolean plus the event's own `timezone`, and the
integration derives a `date` in that timezone when the flag is set. That
arrangement works and is now settled. List items need the equivalent distinction;
what it is called and how it is carried is Calendora's call.

Without it, the integration must choose one of:

- Declare only `SET_DUE_DATETIME_ON_ITEM`, so every due date carries a time.
  "Due Tuesday" becomes "due Tuesday at 00:00", which then displays as a time the
  user never entered.
- Declare only `SET_DUE_DATE_ON_ITEM` and discard the time on every write. Lossy
  in the other direction, and invisible until someone notices their 16:00
  reminder became "sometime Tuesday".
- Declare neither and drop due dates from the write path entirely.

All three are wrong in a way a user eventually reports. The third is the only one
that is *honestly* wrong, and it is what would ship.

---

## 5. Moving an item

`MOVE_TODO_ITEM` gives the user drag-to-reorder. Home Assistant expresses a move
as `async_move_todo_item(uid, previous_uid)` — "put this item after that one",
where `previous_uid=None` means "make it first". It never sends a position value,
and it has no concept of a fractional index.

§4a's `position` is a fractional-index **string**, pre-sorted, compared as a
string. That is a good design for concurrent reordering and it does not
correspond to anything Home Assistant exposes.

So the requirement is: **the integration must be able to place an item between
two identified neighbours.** Whether that happens by sending a computed position,
by naming the neighbours, or some other way is Calendora's decision — but the
integration cannot compute a fractional index itself without knowing the
generation scheme, and reverse-engineering one from observed values would be
building on undocumented behaviour.

**Sections complicate this and should be decided deliberately.** Home Assistant's
todo list is flat; §4a's items have a `sectionId`. A user dragging an item in
Home Assistant is expressing an order within a flat list, which may or may not
imply moving it between sections. Whichever answer is right, the integration
should not be the thing that decides it by accident.

---

## 6. The round-trip hazard, and it is the sharpest edge here

`todo.update_item` performs its partial merge **inside Home Assistant, not in the
integration**. It reads the existing item, overlays only the fields present in
the service call, and then calls `async_update_todo_item()` with a **complete
`TodoItem`**.

The consequence: on every single update — including a user simply ticking a
checkbox — the integration is handed an object containing `uid`, `summary`,
`status`, `due` and `description`, **and nothing else**. It has no way to know
which of them the user actually changed.

If the write path replaces an item wholesale with what it is given, then ticking
a checkbox erases `quantity`, `sectionId`, `assignedMembershipId` and the item's
place in the list — because Home Assistant never knew those existed and the
integration cannot tell "unchanged" from "cleared".

**The need: an update that leaves unmentioned fields alone.** The integration can
hold a cached copy of the full item and send back what it thinks the other fields
were, but that is a lost-update race the moment two clients touch one list —
which is exactly the scenario a family shopping list is *for*.

---

## 7. Services, and what each one implies

| Service | Requires | Notes |
|---|---|---|
| `todo.get_items` | *nothing* | Works on a read-only entity today |
| `todo.add_item` | `CREATE_TODO_ITEM` | |
| `todo.update_item` | `UPDATE_TODO_ITEM` | Carries the §6 hazard |
| `todo.remove_item` | `DELETE_TODO_ITEM` | Resolves items to ids first, then deletes |
| `todo.remove_completed_items` | `DELETE_TODO_ITEM` | Home Assistant collects the completed ids and deletes them **as one call per list of uids** — so this is N deletions, not a "clear completed" operation. Worth knowing before it becomes N HTTP requests on a long list |

### Voice comes free, but only with the flags

`HassListAddItem`, `HassListCompleteItem` and `HassListRemoveItem` are inherited
from the platform — *"add milk to the family shopping list"* works through Assist
with no code from this integration. They map onto create, update and delete
respectively, so each intent is gated on the corresponding flag. No flags, no
voice.

---

## 8. What is shippable before any of this is answered

A **read-only todo list**: one `TodoListEntity` per list from `GET /api/v1/lists`
and `GET /api/v1/lists/{id}/items`, declaring **zero feature flags**, exposing
`uid`, `summary`, `status` and `description`, plus `due` if and when §4 is
settled.

That is genuinely useful — a dashboard card showing the shopping list, and
automations that read it — and it is honest, because a user is never offered a
control that does nothing. It is also the same discipline the calendar shipped
under, and for the same reason.

Whether it is worth shipping ahead of writes is a product call, not this
document's.

---

## 9. Summary of what is needed

1. Write access to list items at all — create, update, delete. *(Blocked on the
   actor migration; not a gap, a schedule.)*
2. A way to distinguish a due **day** from a due **instant**, as events now do.
3. An update that preserves fields the caller did not mention.
4. A way to place an item between two identified neighbours.
5. A decision on what reordering means when items live in sections.
