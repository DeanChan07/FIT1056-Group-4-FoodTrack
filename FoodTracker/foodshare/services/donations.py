"""F-02 donations: booking a drop-off without an account, and receiving it (FR-08 to FR-12)."""

import secrets

from .. import domain as d
from ..domain import DomainError
from .public_controls import public_limit
from .people import volunteer_assigned_on
from .base import _audit, _clean, _not_in_past, _now, _positive_int, require


def _new_reference(tx):
    while True:
        ref = "DN-" + secrets.token_hex(12).upper()
        if not tx.find_one("donations", reference=ref):
            return ref


def schedule_donation(store, items, dropoff_date, dropoff_time, donor_name=""):
    """FR-08 and FR-09: no account needed; returns the unique reference."""
    clean_items = []
    for item in items:
        name = _clean(item.get("item_type"), "item name", required=False, max_length=150)
        if not name:
            continue
        clean_items.append({
            "item_type": name,
            "offered_qty": _positive_int(item.get("quantity"), f"Quantity for {name}"),
        })
    if not clean_items:
        raise DomainError("Please add at least one item type with a quantity.")
    dropoff_date, dropoff_time = _not_in_past(dropoff_date, dropoff_time, "drop-off")
    public_limit(store, "donation_booking", 60)
    with store.transaction() as tx:
        return tx.insert("donations", {
            "reference": _new_reference(tx),
            "donor_name": _clean(donor_name, "donor name", required=False, max_length=100),
            "dropoff_date": dropoff_date,
            "dropoff_time": dropoff_time,
            "items": clean_items,
            "status": d.SCHEDULED,
            "created_at": _now(),
        })


def find_donation(store, reference):
    """Donors check their donation status with the reference (no account)."""
    public_limit(store, "donation_lookup", 300)
    ref = (reference or "").strip().upper()
    with store.reader() as read_tx:
        return read_tx.find_one("donations", reference=ref)


def receive_donation(store, actor, reference, accepted):
    """FR-10 to FR-12: accepted is a list per item of
    {accepted_qty, expiry_date, allergens, dietary_tags, category}."""
    require(actor, d.VOLUNTEER, d.STAFF)
    with store.transaction() as tx:
        if actor["role"] == d.VOLUNTEER and not volunteer_assigned_on(tx, actor, d.today().isoformat(), "Receiving"):
            from ..domain import PermissionDenied
            raise PermissionDenied("You need a Receiving task today to receive donations.")
        donation = tx.find_one("donations", reference=(reference or "").strip().upper())
        if not donation:
            raise DomainError("No donation has that reference.")
        if donation["status"] == d.COLLECTED:
            raise DomainError("This donation has already been received.")
        if len(accepted) != len(donation["items"]):
            raise DomainError("Please record every item in the donation.")
        for item, entry in zip(donation["items"], accepted):
            qty = _positive_int(entry.get("accepted_qty"),
                                f"Accepted quantity for {item['item_type']}", allow_zero=True)
            if qty > item["offered_qty"]:
                raise DomainError(f"Accepted quantity for {item['item_type']} is more than "
                                  "was offered.")
            item["accepted_qty"] = qty
            item["rejected_qty"] = item["offered_qty"] - qty
            if qty:
                expiry = d.parse_date(entry.get("expiry_date"))
                batch = tx.insert("batches", {
                    "name": item["item_type"],
                    "category": _clean(entry.get("category"), "", required=False) or "General",
                    "quantity": qty,
                    "expiry_date": expiry.isoformat(),
                    "allergens": d.normalize_allergens(entry.get("allergens")),
                    "allergens_confirmed": bool(entry.get("allergens_confirmed")),
                    "dietary_tags": d.split_list(entry.get("dietary_tags")),
                    "source_donation": donation["reference"],
                    "created_at": _now(),
                    "on_hold": False,
                    "version": 1,
                })
                item["batch_id"] = batch["id"]
                tx.insert("adjustments", {"batch_id": batch["id"], "change": qty,
                          "before_quantity": 0, "after_quantity": qty, "reason_code": "Received",
                          "reason": f"Donation {donation['reference']} received",
                          "source_type": "donations", "source_id": donation["id"],
                          "made_by": actor["id"], "made_at": _now()})
        donation["status"] = d.COLLECTED
        donation["received_by"] = actor["id"]
        donation["received_at"] = _now()
        donation["receipt"] = (
            f"Thank you. Donation {donation['reference']} was received on "
            f"{d.parse_date(donation['received_at'][:10]).strftime('%d %b %Y')}.")
        _audit(tx, actor, "Donation received", donation["reference"],
               accepted=sum(i["accepted_qty"] for i in donation["items"]),
               rejected=sum(i["rejected_qty"] for i in donation["items"]))
        return donation


def list_donations(store, actor):
    require(actor, d.VOLUNTEER, d.STAFF, d.MANAGER)
    with store.reader() as read_tx:
        return sorted(read_tx.all("donations"), key=lambda x: x["id"], reverse=True)
