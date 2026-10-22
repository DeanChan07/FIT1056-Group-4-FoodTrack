"""F-05 allocation and collection, and F-07 pickup notices
(FR-20 to FR-23, FR-26, FR-30).

Stock is reserved when food is set aside, subtracted when it is collected, and
released again if the allocation is cancelled or the Recipient does not come.
"""

from .. import domain as d
from ..domain import DomainError, EditConflict, PermissionDenied
from .base import audit_food_blocks, _audit, _clean, _name, _not_in_past, _notify, _now, _positive_int, require
from .maintenance import close_queue_entry, expire_overdue_allocations
from .people import volunteer_distributing_on
from .stock import _reserved, _reserved_map, _with_status
from .swaps import _close_open_swaps, refresh_swap_lifecycle


def suitable_batches(store, actor, recipient_id):
    require(actor, d.STAFF)
    with store.reader() as tx:
        profile = tx.find_one("profiles", recipient_id=recipient_id)
        reserved = _reserved_map(tx)
        rows = []
        for batch in sorted(tx.all("batches"), key=lambda b: b["expiry_date"]):
            view = _with_status(tx, batch, reserved)
            if not view["usable"] or view["available"] <= 0:
                continue
            view["problems"] = d.suitability_problems(batch, profile)
            rows.append(view)
        return rows


def _check_batch_for(tx, batch_id, quantity, profile, release=None):
    batch = tx.get("batches", batch_id)
    if not batch:
        raise DomainError("That stock batch no longer exists.")
    if d.is_expired(batch):
        raise d.UnsafeFood(f"{batch['name']} has expired and cannot be given out.", batch["id"])
    if batch.get("on_hold") or batch.get("archived"):
        raise d.UnsafeFood(f"{batch['name']} is on hold and cannot be given out.", batch["id"])
    problems = d.suitability_problems(batch, profile)
    if problems:
        raise DomainError(f"{batch['name']} is not suitable: {'; '.join(problems)}.")
    available = batch["quantity"] - _reserved(tx, batch["id"]) + (release or 0)
    if quantity > available:
        raise DomainError(f"Only {available} of {batch['name']} available.")
    return batch


@audit_food_blocks
def create_allocation(store, actor, recipient_id, items, pickup_date, pickup_time):
    """FR-20 and FR-21: Staff choose; the system only checks safety and stock."""
    require(actor, d.STAFF)
    expire_overdue_allocations(store)
    pickup_date, pickup_time = _not_in_past(pickup_date, pickup_time, "pickup")
    chosen = [(int(i["batch_id"]), _positive_int(i["quantity"], "Quantity"))
              for i in items if str(i.get("quantity") or "0").strip() not in ("", "0")]
    if not chosen:
        raise DomainError("Please choose at least one item and quantity.")
    with store.transaction() as tx:
        recipient = tx.get("users", recipient_id)
        if not recipient or recipient["role"] != d.RECIPIENT or not recipient["active"]:
            raise DomainError("Recipient not found.")
        profile = tx.find_one("profiles", recipient_id=recipient["id"])
        allocation = tx.insert("allocations", {
            "recipient_id": recipient["id"],
            "status": d.ALLOCATED,
            "pickup_date": pickup_date,
            "pickup_time": pickup_time,
            "created_by": actor["id"],
            "created_at": _now(),
            "items": [], "version": 1,
        })
        for n, (batch_id, qty) in enumerate(chosen, start=1):
            batch = _check_batch_for(tx, batch_id, qty, profile)
            allocation["items"].append(
                {"item_id": n, "batch_id": batch_id, "name": batch["name"], "quantity": qty})
            tx.flush()  # so the next item's stock check counts this one
        _audit(tx, actor, "Food set aside", f"Allocation {allocation['id']}",
               units=sum(q for _, q in chosen), pickup=f"{pickup_date} {pickup_time}")
        return allocation


def _volunteer_can_see(tx, actor, allocation):
    """C5 and M10: Volunteers see an allocation only on its pickup day, and only when they
    have a Distribution shift that day. They never see swaps or needs."""
    today = d.today().isoformat()
    return allocation["pickup_date"] == today and volunteer_distributing_on(tx, actor, today)


def list_allocations(store, actor, recipient_id=None):
    expire_overdue_allocations(store)
    require(actor, d.RECIPIENT, d.STAFF, d.VOLUNTEER)
    if actor and actor["role"] == d.RECIPIENT:
        recipient_id = actor["id"]
    else:
        require(actor, d.STAFF, d.VOLUNTEER)
    with store.reader() as tx:
        if actor["role"] == d.VOLUNTEER:
            rows = [a for a in tx.find("allocations", pickup_date=d.today().isoformat())
                    if _volunteer_can_see(tx, actor, a)
                    and (recipient_id is None or a["recipient_id"] == recipient_id)]
        elif recipient_id is not None:
            rows = tx.find("allocations", recipient_id=recipient_id)
        else:
            rows = tx.all("allocations")
        result = []
        for a in sorted(rows, key=lambda x: x["id"], reverse=True):
            view = dict(a)
            view["recipient_name"] = _name(tx, a["recipient_id"])
            result.append(view)
        return result


def get_allocation(store, actor, allocation_id):
    require(actor, d.RECIPIENT, d.STAFF, d.VOLUNTEER)
    expire_overdue_allocations(store)
    refresh_swap_lifecycle(store)
    with store.reader() as tx:
        allocation = tx.get("allocations", allocation_id)
        if not allocation:
            raise DomainError("Allocation not found.")
        if actor and actor["role"] == d.RECIPIENT:
            if allocation["recipient_id"] != actor["id"]:
                raise PermissionDenied("You do not have access to this allocation.")
        else:
            require(actor, d.STAFF, d.VOLUNTEER)
            if actor["role"] == d.VOLUNTEER and not _volunteer_can_see(tx, actor, allocation):
                raise PermissionDenied("You can only open allocations for your distribution shift.")
        view = dict(allocation)
        view["recipient_name"] = _name(tx, allocation["recipient_id"])
        view["swaps"] = ([] if actor["role"] == d.VOLUNTEER
                         else tx.find("swaps", allocation_id=allocation["id"]))
        view["distribution"] = tx.find_one("distributions", allocation_id=allocation["id"])
        return view


@audit_food_blocks
def record_collection(store, actor, allocation_id, actual_quantities, collected_date=None,
                      batch_ids=None, exception_reason=""):
    """FR-22 and FR-23: distribution record and stock deduction in one save.

    Collecting fewer than allocated is allowed; the rest goes back on the shelf.
    batch_ids maps item_id to the batch the form showed, so a swap approved while the
    page was open cannot make the wrong food come off the shelf."""
    require(actor, d.STAFF, d.VOLUNTEER)
    expire_overdue_allocations(store)
    day = d.parse_date(collected_date or d.today().isoformat())
    if day > d.today():
        raise DomainError("The collection date cannot be in the future.")
    with store.transaction() as tx:
        allocation = tx.get("allocations", allocation_id)
        if not allocation:
            raise DomainError("Allocation not found.")
        if actor["role"] == d.VOLUNTEER:
            if day != d.today() or not _volunteer_can_see(tx, actor, allocation):
                raise PermissionDenied("Volunteers can record a collection only on the pickup "
                                       "day of their own Distribution shift.")
        if allocation["status"] != d.ALLOCATED:
            raise DomainError(f"This allocation is already {allocation['status'].lower()}.")
        recipient = tx.get("users", allocation["recipient_id"])
        if not recipient or not recipient["active"]:
            raise DomainError("This Recipient account is inactive.")
        if day < d.parse_date(allocation["pickup_date"]):
            raise DomainError("The collection date cannot be before the pickup date.")
        profile = tx.find_one("profiles", recipient_id=allocation["recipient_id"])
        late = day == d.today() and d.now() >= d.pickup_end(allocation, tx.setting("queue_window_minutes"))
        if late:
            reason = exception_reason.strip() or allocation.get("exception_reason")
            if actor["role"] != d.STAFF or not reason:
                raise DomainError("The pickup window has ended. Staff must record an exception reason for late collection.")
            allocation["exception_reason"] = _clean(reason, "an exception reason")
        if day < d.parse_date(allocation["created_at"][:10]):
            raise DomainError("The collection date cannot be before the food was set aside.")
        issued = []
        for item in allocation["items"]:
            shown = (batch_ids or {}).get(item["item_id"])
            if shown and str(shown) != str(item["batch_id"]):
                raise EditConflict("This allocation changed while the page was open (a swap "
                                   "was approved). Please check the items and confirm again.")
            qty = _positive_int(actual_quantities.get(item["item_id"], item["quantity"]),
                                f"Collected quantity for {item['name']}", allow_zero=True)
            if qty > item["quantity"]:
                raise DomainError(f"Collected quantity for {item['name']} is more than was "
                                  "allocated.")
            batch = tx.get("batches", item["batch_id"])
            if not batch:
                raise DomainError("A batch in this allocation no longer exists. Please ask Staff to reallocate it.")
            if qty and d.is_expired(batch):
                raise d.UnsafeFood(f"{batch['name']} has expired and cannot be given out.", batch["id"])
            if qty and (batch.get("on_hold") or batch.get("archived")):
                raise d.UnsafeFood(f"{batch['name']} is on hold and cannot be given out.", batch["id"])
            if qty:
                problems = d.suitability_problems(batch, profile)
                if problems:
                    raise DomainError(f"{batch['name']} is not suitable: {'; '.join(problems)}.")
            if qty > batch["quantity"]:
                raise DomainError(f"Only {batch['quantity']} of {batch['name']} in stock.")
            before = batch["quantity"]
            batch["quantity"] -= qty
            if qty:
                tx.insert("adjustments", {"batch_id": batch["id"], "change": -qty,
                          "before_quantity": before, "after_quantity": batch["quantity"],
                          "reason": "Food collected", "reason_code": "Distributed",
                          "source_type": "allocations", "source_id": allocation["id"],
                          "made_by": actor["id"], "made_at": _now()})
            batch["version"] = (batch.get("version") or 0) + 1
            issued.append({"item_id": item["item_id"], "batch_id": batch["id"],
                           "name": item["name"], "quantity": qty})
        allocation["status"] = d.COLLECTED
        allocation["version"] = (allocation.get("version") or 0) + 1
        close_queue_entry(tx, allocation["id"], "Completed")
        allocation["queue_state"] = None
        _close_open_swaps(tx, allocation["id"], d.CLOSED,
                          "This request closed because the food was collected.", actor)
        _audit(tx, actor, "Collection recorded", f"Allocation {allocation['id']}",
               units=sum(i["quantity"] for i in issued), date=day.isoformat())
        return tx.insert("distributions", {
            "allocation_id": allocation["id"],
            "recipient_id": allocation["recipient_id"],
            "collected_date": day.isoformat(),
            "items": issued,
            "recorded_by": actor["id"],
        })


def cancel_allocation(store, actor, allocation_id, confirmed, reason=""):
    """FR-23 and C4: Staff cancel an uncollected allocation. The reserved food goes back
    on the shelf, any waiting swap request is closed, and the Recipient is told."""
    require(actor, d.STAFF)
    if not confirmed:
        raise DomainError("Please tick the box to confirm the cancellation.")
    reason = _clean(reason, "a short reason for the Recipient")
    with store.transaction() as tx:
        allocation = tx.get("allocations", allocation_id)
        if not allocation:
            raise DomainError("Allocation not found.")
        if allocation["status"] != d.ALLOCATED:
            raise DomainError(f"This allocation is already {allocation['status'].lower()}.")
        _close(tx, actor, allocation, d.CANCELLED, reason)
        _notify(tx, allocation["recipient_id"], "Pickup cancelled",
                f"Your pickup on {allocation['pickup_date']} at {allocation['pickup_time']} "
                f"was cancelled: {reason}")
        _audit(tx, actor, "Allocation cancelled", f"Allocation {allocation['id']}")
        return allocation


def _close(tx, actor, allocation, status, reason):
    allocation["status"] = status
    allocation["queue_state"] = None
    allocation["version"] = (allocation.get("version") or 0) + 1
    close_queue_entry(tx, allocation["id"], status)
    allocation["closed_by"] = actor["id"] if actor else None
    allocation["closed_at"] = _now()
    allocation["close_reason"] = reason
    _close_open_swaps(tx, allocation["id"], d.CANCELLED,
                      "This request closed because the pickup was cancelled.", actor)


# ---------------------------------------------------------------- notices (F-07)

def update_pickup(store, actor, allocation_id, pickup_date, pickup_time):
    """FR-26: the new time and an unread notice are saved together."""
    require(actor, d.STAFF)
    expire_overdue_allocations(store)
    pickup_date, pickup_time = _not_in_past(pickup_date, pickup_time, "pickup")
    with store.transaction() as tx:
        allocation = tx.get("allocations", allocation_id)
        if not allocation or allocation["status"] != d.ALLOCATED:
            raise DomainError("Only uncollected allocations can be rescheduled.")
        if (allocation["pickup_date"], allocation["pickup_time"]) == (pickup_date, pickup_time):
            return None
        close_queue_entry(tx, allocation["id"], d.CANCELLED)
        allocation["version"] = (allocation.get("version") or 0) + 1
        allocation["exception_reason"] = None
        allocation["pickup_date"] = pickup_date
        allocation["pickup_time"] = pickup_time
        allocation["checked_in_at"] = None  # a new day means a new check-in
        allocation["queue_state"] = None
        _audit(tx, actor, "Pickup time changed", f"Allocation {allocation['id']}",
               pickup=f"{pickup_date} {pickup_time}")
        return _notify(tx, allocation["recipient_id"], "Pickup change",
                       f"Your pickup time has changed to {pickup_date} at {pickup_time}.")


def list_notifications(store, actor):
    require(actor, *((d.RECIPIENT,) + d.INTERNAL_ROLES))
    with store.reader() as read_tx:
        rows = read_tx.find("notifications", user_id=actor["id"])
    return sorted(rows, key=lambda n: n["id"], reverse=True)


def unread_count(store, actor):
    if not actor:
        return 0
    require(actor, d.RECIPIENT, *d.INTERNAL_ROLES)
    with store.reader() as read_tx:
        return read_tx.count("notifications", user_id=actor["id"], read=False)


def mark_notifications_read(store, actor, ids=None):
    """Mark the notices the person has seen as read (all of them when ids is None)."""
    require(actor, d.RECIPIENT, *d.INTERNAL_ROLES)
    with store.transaction() as tx:
        for n in tx.find("notifications", user_id=actor["id"], read=False):
            if ids is None or n["id"] in ids:
                n["read"] = True
