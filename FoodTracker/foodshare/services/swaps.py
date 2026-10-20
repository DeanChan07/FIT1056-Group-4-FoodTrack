"""F-09 private food swaps (FR-31 to FR-37, FR-43, FR-44).

A request is Pending until Staff approve or decline it, or the Recipient withdraws it.
It also closes by itself:
  Expired   - the pickup window ended before anyone decided,
  Closed    - the food was collected first,
  Cancelled - the allocation was cancelled or the Recipient did not come.
The reason is seen only by the Recipient and Staff, never Volunteers or Managers (FR-34).
"""

from .. import domain as d
from ..domain import DomainError, PermissionDenied
from .base import _audit, _clean, _name, _notify, _now, require
from .stock import _reserved_map, _with_status


def _window_ended(tx, allocation):
    return d.now() >= d.pickup_end(allocation, tx.setting("queue_window_minutes"))


def _close_open_swaps(tx, allocation_id, status, response):
    for swap in tx.find("swaps", allocation_id=allocation_id, status=d.PENDING):
        swap["status"] = status
        swap["response"] = response
        swap["closed_at"] = _now()


def _expire_swaps(tx):
    """FR-43: Pending requests whose pickup window has ended become Expired."""
    for swap in tx.find("swaps", status=d.PENDING):
        allocation = tx.get("allocations", swap["allocation_id"])
        if allocation and _window_ended(tx, allocation):
            swap["status"] = d.EXPIRED
            swap["response"] = ("This request closed because the pickup time passed before "
                                "staff could decide. Your original item was kept for you.")
            swap["closed_at"] = _now()


def refresh_swap_lifecycle(store):
    """Save any expiries before showing swaps. Writes only when something changed."""
    tx = store.reader()
    due = [s for s in tx.find("swaps", status=d.PENDING)
           if (a := tx.get("allocations", s["allocation_id"])) and _window_ended(tx, a)]
    if due:
        with store.transaction() as wtx:
            _expire_swaps(wtx)


def request_swap(store, actor, allocation_id, item_id, reason=""):
    """FR-31 to FR-33."""
    require(actor, d.RECIPIENT)
    with store.transaction() as tx:
        allocation = tx.get("allocations", allocation_id)
        if not allocation or allocation["recipient_id"] != actor["id"]:
            raise PermissionDenied("You do not have access to this allocation.")
        if allocation["status"] != d.ALLOCATED:
            raise DomainError("This food has already been collected or cancelled, so it "
                              "cannot be swapped.")
        if _window_ended(tx, allocation):
            raise DomainError("The pickup time for this food has passed, so it can no longer "
                              "be swapped.")
        item = next((i for i in allocation["items"] if i["item_id"] == item_id), None)
        if not item:
            raise DomainError("Item not found in this allocation.")
        if any(s["item_id"] == item_id
               for s in tx.find("swaps", allocation_id=allocation["id"], status=d.PENDING)):
            raise DomainError("You already have a request waiting for this item.")
        return tx.insert("swaps", {
            "allocation_id": allocation["id"],
            "item_id": item_id,
            "item_name": item["name"],
            "recipient_id": actor["id"],
            "reason": (reason or "").strip(),
            "status": d.PENDING,
            "response": "",
            "replacement_batch_id": None,
            "created_at": _now(),
        })


def list_swaps(store, actor, status=None):
    refresh_swap_lifecycle(store)
    if actor and actor["role"] == d.RECIPIENT:
        rows = store.reader().find("swaps", recipient_id=actor["id"])
    else:
        require(actor, d.STAFF)
        rows = store.reader().all("swaps")
    if status:
        rows = [s for s in rows if s["status"] == status]
    return sorted(rows, key=lambda s: s["id"], reverse=True)


def get_swap(store, actor, swap_id):
    require(actor, d.STAFF)
    refresh_swap_lifecycle(store)
    tx = store.reader()
    swap = tx.get("swaps", swap_id)
    if not swap:
        raise DomainError("Request not found.")
    view = dict(swap)
    view["recipient_name"] = _name(tx, swap["recipient_id"])
    allocation = tx.get("allocations", swap["allocation_id"])
    item = next(i for i in allocation["items"] if i["item_id"] == swap["item_id"])
    view["quantity"] = item["quantity"]
    view["pickup_date"] = allocation["pickup_date"]
    view["pickup_time"] = allocation["pickup_time"]
    profile = tx.find_one("profiles", recipient_id=swap["recipient_id"])
    view["summary"] = d.needs_summary(profile)
    reserved = _reserved_map(tx)
    options = []
    for batch in tx.all("batches"):
        if batch["id"] == item["batch_id"] or not d.is_usable(batch):
            continue
        b = _with_status(tx, batch, reserved)
        if b["available"] >= item["quantity"] and not d.suitability_problems(batch, profile):
            options.append(b)
    view["options"] = options
    return view


def _pending_swap_for_decision(tx, swap_id, verb):
    swap = tx.get("swaps", swap_id)
    if not swap or swap["status"] != d.PENDING:
        raise DomainError(f"Only Pending requests can be {verb}.")
    allocation = tx.get("allocations", swap["allocation_id"])
    if allocation["status"] != d.ALLOCATED:
        raise DomainError("This allocation has already been collected or cancelled.")
    if _window_ended(tx, allocation):  # FR-44
        raise DomainError("The pickup time has passed, so this request has closed.")
    return swap, allocation


def approve_swap(store, actor, swap_id, replacement_batch_id):
    """FR-35 and FR-36: replace the item and move the reserved stock in one save."""
    from .allocations import _check_batch_for
    require(actor, d.STAFF)
    with store.transaction() as tx:
        swap, allocation = _pending_swap_for_decision(tx, swap_id, "approved")
        item = next(i for i in allocation["items"] if i["item_id"] == swap["item_id"])
        profile = tx.find_one("profiles", recipient_id=swap["recipient_id"])
        replacement_batch_id = int(replacement_batch_id)
        if replacement_batch_id == item["batch_id"]:
            raise DomainError("Please choose a different item as the replacement.")
        batch = _check_batch_for(tx, replacement_batch_id, item["quantity"], profile)
        item["batch_id"] = batch["id"]
        item["name"] = batch["name"]
        swap["status"] = d.APPROVED
        swap["replacement_batch_id"] = batch["id"]
        swap["response"] = f"Your item has been changed to {batch['name']}."
        swap["reviewed_by"] = actor["id"]
        swap["closed_at"] = _now()
        _notify(tx, swap["recipient_id"], "Swap request", swap["response"])
        _audit(tx, actor, "Swap approved", f"Request {swap['id']}",
               allocation=allocation["id"])  # no reason: it is private
        return swap


def decline_swap(store, actor, swap_id, response):
    """FR-37: a respectful response visible only to the Recipient and Staff."""
    require(actor, d.STAFF)
    text = _clean(response, "a response for the Recipient")
    with store.transaction() as tx:
        swap, allocation = _pending_swap_for_decision(tx, swap_id, "declined")
        swap["status"] = d.DECLINED
        swap["response"] = text
        swap["reviewed_by"] = actor["id"]
        swap["closed_at"] = _now()
        _notify(tx, swap["recipient_id"], "Swap request",
                "There is an update on your swap request.")
        _audit(tx, actor, "Swap declined", f"Request {swap['id']}", allocation=allocation["id"])
        return swap


def withdraw_swap(store, actor, swap_id):
    """A Recipient can change their mind while a request is still Pending."""
    require(actor, d.RECIPIENT)
    with store.transaction() as tx:
        swap = tx.get("swaps", swap_id)
        if not swap or swap["recipient_id"] != actor["id"]:
            raise PermissionDenied("You do not have access to this request.")
        if swap["status"] != d.PENDING:
            raise DomainError("Only a Pending request can be withdrawn.")
        swap["status"] = d.WITHDRAWN
        swap["response"] = "You withdrew this request."
        swap["closed_at"] = _now()
        return swap
