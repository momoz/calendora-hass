"""To-do platform for Calendora.

One `TodoListEntity` per list, with write-back.

**The rule this whole file is built around is `docs/API-SURFACE.md` §6:
partial, omitted untouched, explicit `null` clears, never read-merge-write.**

That matters more here than anywhere else in the integration, because of how
Home Assistant's update service works. `todo.update_item` performs its partial
merge *inside Home Assistant* and hands the integration a **complete**
`TodoItem` — summary, status, due and description — on every call, including
when a user has done nothing but tick a checkbox. It cannot tell us which field
they touched.

A client that wrote that whole object back would:

- erase `quantity`, `sectionId` and `assignedMembershipId`, which Home Assistant
  has never heard of and therefore cannot send; and
- make itself authoritative over every field it echoed, so a phone edit made a
  second earlier silently loses.

So `_changed_fields` diffs against the item as we last saw it and sends **only
what actually differs**. A checkbox tick becomes `{"isChecked": true}` and
nothing else. This is the difference between merge-patch working for us and
merge-patch being a footgun.

**`MOVE_TODO_ITEM` is not declared and never will be** (§9): there is no move
endpoint, `position` is rejected in a write body, and Calendora's sections are
shops — so a drag would either silently change which shop something is bought at
or snap back.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import uuid4

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import CalendoraConfigEntry
from .api import CalendoraAuthError, CalendoraConflictError, CalendoraError
from .const import DOMAIN, LOGGER
from .coordinator import CalendoraDataUpdateCoordinator

PARALLEL_UPDATES = 0

# Everything Calendora can actually honour. MOVE_TODO_ITEM is absent by
# decision, not omission — see the module docstring.
SUPPORTED = (
    TodoListEntityFeature.CREATE_TODO_ITEM
    | TodoListEntityFeature.UPDATE_TODO_ITEM
    | TodoListEntityFeature.DELETE_TODO_ITEM
    | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
    | TodoListEntityFeature.SET_DUE_DATE_ON_ITEM
    | TodoListEntityFeature.SET_DUE_DATETIME_ON_ITEM
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CalendoraConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one entity per list, including lists added later."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new_lists() -> None:
        new = [
            CalendoraTodoList(coordinator, list_id)
            for list_id in coordinator.data.lists
            if list_id not in known and not known.add(list_id)
        ]
        if new:
            async_add_entities(new)

    _add_new_lists()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_lists))


def _due_to_wire(due: date | datetime | None) -> str | None:
    """Render a due value in the form that carries its own meaning.

    §5: `due` is "date **or** instant — the form is the meaning". A `date` means
    a day; an instant means a moment. This is the one place that distinction is
    encoded, and it is why both due-date feature flags can be declared honestly
    rather than one of them lying.
    """
    if due is None:
        return None
    if isinstance(due, datetime):
        return dt_util.as_utc(due).isoformat().replace("+00:00", "Z")
    return due.isoformat()


def _due_from_wire(due: str | None) -> date | datetime | None:
    """Read a due value back, preserving day-versus-moment."""
    if not due:
        return None
    if "T" in due:
        parsed = dt_util.parse_datetime(due)
        return dt_util.as_local(parsed) if parsed else None
    return dt_util.parse_date(due)


def _as_todo_item(row: dict[str, Any]) -> TodoItem:
    """Convert one Calendora item into Home Assistant's shape."""
    return TodoItem(
        uid=row.get("id"),
        summary=row.get("text") or "",
        status=(
            TodoItemStatus.COMPLETED
            if row.get("isChecked")
            else TodoItemStatus.NEEDS_ACTION
        ),
        description=row.get("notes"),
        due=_due_from_wire(row.get("due")),
    )


def _changed_fields(item: TodoItem, previous: dict[str, Any]) -> dict[str, Any]:
    """Return only the fields that actually differ from what we last saw.

    **This function is why ticking a checkbox does not erase a shopping list.**

    Home Assistant hands over a whole `TodoItem` on every update, so without
    this every write would carry `text`, `notes`, `isChecked` and `due` whether
    or not the user touched them. Under merge-patch that is not destructive to
    fields we never send — but it *is* authoritative over the ones we do, which
    means a concurrent edit from somebody's phone loses for no reason.

    `None` is deliberately preserved rather than skipped: §6 says an explicit
    `null` clears, and clearing a description is a thing a user can legitimately
    do. The comparison is against the previous value, so a genuine clear is sent
    and a field that was already empty is not.
    """
    changes: dict[str, Any] = {}

    if item.summary is not None and item.summary != previous.get("text"):
        changes["text"] = item.summary

    checked = item.status == TodoItemStatus.COMPLETED
    if checked != bool(previous.get("isChecked")):
        changes["isChecked"] = checked

    if item.description != previous.get("notes"):
        changes["notes"] = item.description

    due = _due_to_wire(item.due)
    if due != previous.get("due"):
        changes["due"] = due

    return changes


class CalendoraTodoList(CoordinatorEntity[CalendoraDataUpdateCoordinator], TodoListEntity):
    """One Calendora list."""

    _attr_has_entity_name = True
    _attr_supported_features = SUPPORTED

    def __init__(
        self, coordinator: CalendoraDataUpdateCoordinator, list_id: str
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self._list_id = list_id
        self._attr_name = self._row().get("list", {}).get("name") or "List"
        self._attr_unique_id = f"{coordinator.data.household_id}-list-{list_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.data.household_id)},
            entry_type=DeviceEntryType.SERVICE,
            name=coordinator.data.household_name,
            manufacturer="Calendora",
        )

    def _row(self) -> dict[str, Any]:
        return self.coordinator.data.lists.get(self._list_id, {})

    def _raw_items(self) -> list[dict[str, Any]]:
        return self._row().get("items") or []

    def _raw_item(self, uid: str) -> dict[str, Any]:
        for row in self._raw_items():
            if row.get("id") == uid:
                return row
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="item_not_found"
        )

    @property
    def available(self) -> bool:
        """Unavailable once the list is gone, rather than silently empty."""
        return super().available and self._list_id in self.coordinator.data.lists

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the Calendora list id.

        A blueprint needs it to build the deep link into shopping mode, and it
        is otherwise only present inside `unique_id`, which an automation cannot
        read. `list_type` comes along because the batching design treats a
        shopping list differently from a checklist.
        """
        row = self._row().get("list") or {}
        return {
            "list_id": self._list_id,
            "list_type": row.get("type"),
            "section_count": len(self._row().get("sections") or []),
        }

    @property
    def todo_items(self) -> list[TodoItem] | None:
        """Return the list's items.

        §9: order arrives already sorted by a fractional index. Render it, do
        not compute it — and never parse `position` as a number.
        """
        return [_as_todo_item(row) for row in self._raw_items()]

    async def _async_write(self, make_request: Any, failure_key: str) -> None:
        """Run one write, then reconcile from the server.

        The local update is optimistic only in the sense that the refresh is
        requested immediately rather than waited for by the user; the stream's
        `changed` event will also arrive and reconcile. Both paths converge on
        whatever the server actually stored, which is the only version that
        matters when two people are editing one shopping list.
        """
        try:
            await self._async_attempt(make_request)
        except CalendoraAuthError as err:
            self.coordinator.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="invalid_auth"
            ) from err
        except CalendoraError as err:
            LOGGER.debug("Calendora write failed: %s", err)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key=failure_key,
                translation_placeholders={"detail": str(err)},
            ) from err

        # `async_request_refresh` is debounced by up to ten seconds. That is
        # right for a stream event and wrong for a write the user just made:
        # add an item and it would not appear until the debounce expired, so
        # the next thing they do — tick it — fails with "unable to find item".
        # Found by installing this into a real Home Assistant; no unit test
        # sees a debouncer.
        await self.coordinator.async_refresh()

    async def _async_attempt(self, make_request: Any) -> Any:
        """Send, and retry once if somebody else got there first.

        §2: `conflict` is the only retryable code, and the retry is safe because
        nothing was applied. The request is rebuilt rather than replayed — for an
        update that means diffing against the row as it now stands, so we do not
        re-assert a field the other person just changed.
        """
        try:
            return await make_request()
        except CalendoraConflictError:
            LOGGER.debug("Calendora reported a conflict; re-reading and retrying once")
            await self.coordinator.async_refresh()
            return await make_request()

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Add an item.

        §7: the id is chosen here and sent. A timed-out request cannot be told
        apart from a lost reply, and a retry without an id would create the item
        twice — a duplicate "milk" on a shared shopping list.

        Only fields the user actually supplied are sent. `quantity`,
        `sectionId` and `assignedMembershipId` are omitted entirely, which under
        merge-patch means "not set" rather than "cleared", and leaves them for
        Calendora to default.
        """
        fields: dict[str, Any] = {"text": item.summary or ""}
        if item.description is not None:
            fields["notes"] = item.description
        if item.due is not None:
            fields["due"] = _due_to_wire(item.due)
        if item.status == TodoItemStatus.COMPLETED:
            fields["isChecked"] = True

        item_id = uuid4().hex
        await self._async_write(
            lambda: self.coordinator.client.async_create_list_item(
                self._list_id, item_id, fields
            ),
            "create_failed",
        )

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Update an item, sending only what changed.

        See `_changed_fields`. Home Assistant gives us the whole item; sending
        the whole item back is what destroys other people's edits.
        """
        if item.uid is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="item_not_found"
            )

        if not _changed_fields(item, self._raw_item(item.uid)):
            # §6: an empty PATCH body is a 400 by design. Nothing changed, so
            # there is nothing to send — and no reason to touch the server.
            return

        def request():
            # Recomputed per attempt, so a retry after a conflict diffs against
            # the row as it now stands rather than replaying a stale diff.
            changes = _changed_fields(item, self._raw_item(item.uid))
            return self.coordinator.client.async_update_list_item(
                self._list_id, item.uid, changes or {"text": item.summary or ""}
            )

        await self._async_write(request, "update_failed")

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Delete items.

        Home Assistant asks for a list of ids — `todo.remove_completed_items`
        can hand over a long one — and Calendora deletes one at a time. They run
        sequentially rather than concurrently on purpose: a burst of parallel
        deletes against a shared list is a good way to find a rate limit that is
        not documented, and clearing a completed list is not time-critical.
        """
        for uid in uids:
            await self._async_write(
                lambda uid=uid: self.coordinator.client.async_delete_list_item(
                    self._list_id, uid
                ),
                "delete_failed",
            )
