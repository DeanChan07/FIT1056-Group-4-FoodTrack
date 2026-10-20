"""F-03 inventory: batches, safety holds, signed stock corrections and alerts
(FR-13 to FR-16, FR-27, FR-41, FR-42)."""

from .. import domain as d
from ..domain import DomainError, EditConflict
from .base import _audit, _clean, _name, _now, _positive_int, require


def _reserved_map(tx):
    """How many units of each batch are set aside for uncollected allocations."""
    totals = {}
    for allocation in tx.find("allocations", status=d.ALLOCATED):
        for item in allocation["items"]:
            totals[item["batch_id"]] = totals.get(item["batch_id"], 0) + item["quantity"]
    return totals


def _reserved(tx, batch_id):
    return _reserved_map(tx).get(batch_id, 0)


def _with_status(tx, batch, reserved=None):
    """FR-14: on shelf, set aside, available and a text status for one batch."""
    reserved = _reserved_map(tx) if reserved is None else reserved
    view = dict(batch)
    view["reserved"] = reserved.get(batch["id"], 0)
    view["available"] = batch["quantity"] - view["reserved"]
    view["expiry_status"] = d.expiry_label(batch)
    view["usable"] = d.is_usable(batch)
    view["hold_text"] = "On hold" if batch.get("on_hold") else ""
    return view


def usable_units(rows):
    """The one 'units available' figure used on every page (dashboard and inventory)."""
    return sum(max(r["available"], 0) for r in rows if r["usable"])


def list_batches(store, actor, search=""):
    """FR-13 and FR-14."""
    require(actor, d.STAFF, d.MANAGER)
    tx = store.reader()
    term = (search or "").strip().lower()
    batches = [b for b in tx.all("batches")
               if not term or term in b["name"].lower() or term in (b["category"] or "").lower()]
    reserved = _reserved_map(tx)
    return [_with_status(tx, b, reserved) for b in sorted(batches, key=lambda b: b["expiry_date"])]


def get_batch(store, actor, batch_id):
    require(actor, d.STAFF, d.MANAGER)
    tx = store.reader()
    batch = tx.get("batches", batch_id)
    if not batch:
        raise DomainError("Batch not found.")
    return _with_status(tx, batch)


def save_batch(store, actor, fields, batch_id=None):
    """Staff add a batch (with its starting quantity) or edit its details (FR-13).

    Editing never changes the quantity; that is done with adjust_stock so every
    change has a reason and a history (FR-41)."""
    require(actor, d.STAFF)
    name = _clean(fields.get("name"), "the item name")
    expiry = d.parse_date(fields.get("expiry_date")).isoformat()
    on_hold = bool(fields.get("on_hold"))
    hold_reason = (fields.get("hold_reason") or "").strip()
    if on_hold and not hold_reason:
        raise DomainError("Please say why this batch is on hold, for example "
                          "'Waiting for a safety check'.")
    with store.transaction() as tx:
        if batch_id is None:
            quantity = _positive_int(fields.get("quantity"), "Quantity", allow_zero=True)
            batch = tx.insert("batches", {"created_at": _now(), "source_donation": None,
                                          "quantity": quantity, "version": 0})
            if quantity:
                tx.insert("adjustments", {"batch_id": batch["id"], "change": quantity,
                                          "reason": "New stock added", "made_by": actor["id"],
                                          "made_at": _now()})
            action = "Stock added"
        else:
            batch = tx.get("batches", batch_id)
            if not batch:
                raise DomainError("Batch not found.")
            loaded = fields.get("loaded_version")
            if loaded is not None and str(loaded) != str(batch.get("version") or 0):
                raise EditConflict("Someone changed this stock while you were editing. "
                                   "The form now shows the latest details; please check them "
                                   "and save again.")
            action = "Batch details changed"
            if on_hold != bool(batch.get("on_hold")):
                action = "Batch put on hold" if on_hold else "Batch hold released"
        batch.update({
            "name": name,
            "category": (fields.get("category") or "General").strip() or "General",
            "expiry_date": expiry,
            "allergens": d.split_list(fields.get("allergens")),
            "dietary_tags": d.split_list(fields.get("dietary_tags")),
            "on_hold": on_hold,
            "hold_reason": hold_reason if on_hold else "",
            "version": (batch.get("version") or 0) + 1,
        })
        _audit(tx, actor, action, f"Batch {batch['id']} ({name})",
               **({"hold_reason": hold_reason} if on_hold else {}))
        return batch


# ---------------------------------------------------------------- stock corrections

def adjust_stock(store, actor, batch_id, change, reason, loaded_quantity=None):
    """FR-41: a signed correction (+ found, - damaged or miscounted) with a reason.
    The quantity can never drop below what is already set aside for Recipients."""
    require(actor, d.STAFF)
    try:
        change = int(change)
    except (TypeError, ValueError):
        raise DomainError("The change must be a whole number, like 3 or -2.")
    if change == 0:
        raise DomainError("Please enter a change other than 0.")
    reason = _clean(reason, "the reason for the correction")
    with store.transaction() as tx:
        batch = tx.get("batches", batch_id)
        if not batch:
            raise DomainError("Batch not found.")
        if loaded_quantity is not None and str(loaded_quantity) != str(batch["quantity"]):
            raise EditConflict("Someone changed this stock while you were editing. "
                               "The form now shows the latest quantity; please check it "
                               "and save again.")
        _apply_change(tx, batch, change)
        row = tx.insert("adjustments", {"batch_id": batch["id"], "change": change,
                                        "reason": reason, "made_by": actor["id"],
                                        "made_at": _now()})
        _audit(tx, actor, "Stock corrected", f"Batch {batch['id']} ({batch['name']})",
               change=change, reason=reason)
        return row


def _apply_change(tx, batch, change):
    new_quantity = batch["quantity"] + change
    floor = _reserved(tx, batch["id"])
    if new_quantity < floor:
        raise DomainError(f"{batch['name']} cannot go below {floor}, because {floor} "
                          "are set aside for Recipients.")
    batch["quantity"] = new_quantity
    batch["version"] = (batch.get("version") or 0) + 1


def reverse_adjustment(store, actor, adjustment_id, reason):
    """FR-42: undo a correction by adding its exact opposite, linked to it. Each
    correction can be reversed once; the original row is never edited or deleted."""
    require(actor, d.STAFF)
    reason = _clean(reason, "the reason for the reversal")
    with store.transaction() as tx:
        original = tx.get("adjustments", adjustment_id)
        if not original:
            raise DomainError("Correction not found.")
        if original.get("reverses_id"):
            raise DomainError("A reversal cannot itself be reversed. Add a new correction.")
        if tx.find_one("adjustments", reverses_id=original["id"]):
            raise DomainError("This correction has already been reversed.")
        batch = tx.get("batches", original["batch_id"])
        _apply_change(tx, batch, -original["change"])
        row = tx.insert("adjustments", {"batch_id": batch["id"], "change": -original["change"],
                                        "reason": reason, "made_by": actor["id"],
                                        "made_at": _now(), "reverses_id": original["id"]})
        _audit(tx, actor, "Stock correction reversed", f"Batch {batch['id']} ({batch['name']})",
               change=-original["change"], reverses=original["id"])
        return row


def stock_history(store, actor, batch_id):
    """Every correction to one batch, newest first, with who made it."""
    require(actor, d.STAFF, d.MANAGER)
    tx = store.reader()
    rows = tx.find("adjustments", batch_id=int(batch_id))
    reversed_ids = {r["reverses_id"] for r in rows if r["reverses_id"]}
    result = []
    for r in sorted(rows, key=lambda r: r["id"], reverse=True):
        view = dict(r)
        view["made_by_name"] = _name(tx, r["made_by"])
        view["reversed"] = r["id"] in reversed_ids
        result.append(view)
    return result


# ---------------------------------------------------------------- alerts (FR-27)

def stock_alerts(store, actor):
    """Near-expiry batches, and items whose usable available stock is at or below the
    threshold. Available means on shelf minus set aside, leaving out expired or held food,
    so an item that has fully expired shows as 0 instead of disappearing."""
    require(actor, d.STAFF, d.MANAGER)
    tx = store.reader()
    threshold = tx.setting("low_stock_threshold")
    reserved = _reserved_map(tx)
    batches = [_with_status(tx, b, reserved) for b in tx.all("batches")]
    near = [b for b in batches if b["quantity"] > 0
            and (d.is_near_expiry(b) or d.is_expired(b))]
    totals = {}
    for b in batches:
        totals.setdefault(b["name"], 0)
        if b["usable"]:
            totals[b["name"]] += max(b["available"], 0)
    low = [{"name": n, "quantity": q} for n, q in sorted(totals.items()) if q <= threshold]
    return {"threshold": threshold, "near_expiry": sorted(near, key=lambda b: b["expiry_date"]),
            "low_stock": low}


def set_low_stock_threshold(store, actor, value):
    require(actor, d.STAFF, d.MANAGER)
    threshold = _positive_int(value, "Low-stock threshold", allow_zero=True)
    with store.transaction() as tx:
        tx.set_setting("low_stock_threshold", threshold)
        _audit(tx, actor, "Low-stock threshold changed", "", threshold=threshold)
    return threshold
