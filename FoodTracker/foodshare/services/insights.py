"""Reports (FR-28, FR-29), the anonymous feedback box (FR-45 to FR-49),
the audit log (FR-56, FR-57) and the dashboard numbers."""

import csv
import io
from datetime import timedelta

from .. import domain as d
from ..domain import DomainError
from .base import _audit, _name, _now, require
from .stock import _reserved_map, _with_status, stock_alerts, usable_units
from .swaps import refresh_swap_lifecycle


# ---------------------------------------------------------------- reports

def build_report(store, actor, start, end):
    """FR-28: donations received and food given out between two dates, and stock now.
    Current stock is split into usable units and expired units so nothing is double counted."""
    require(actor, d.STAFF, d.MANAGER)
    start_d, end_d = d.parse_date(start), d.parse_date(end)
    if start_d > end_d:
        raise DomainError("The start date must be on or before the end date.")
    tx = store.reader()
    rows = []
    donated = distributed = 0
    for dn in tx.find("donations", status=d.COLLECTED):
        day = d.parse_date(dn["received_at"][:10])
        if start_d <= day <= end_d:
            for item in dn["items"]:
                rows.append({"type": "Donation received", "date": day.isoformat(),
                             "reference": dn["reference"], "item": item["item_type"],
                             "quantity": item.get("accepted_qty", 0)})
                donated += item.get("accepted_qty", 0)
    for dist in tx.all("distributions"):
        day = d.parse_date(dist["collected_date"])
        if start_d <= day <= end_d:
            for item in dist["items"]:
                rows.append({"type": "Distribution completed", "date": day.isoformat(),
                             "reference": f"AL-{dist['allocation_id']}", "item": item["name"],
                             "quantity": item["quantity"]})
                distributed += item["quantity"]
    stock = {}
    for b in tx.all("batches"):
        entry = stock.setdefault(b["name"], {"item": b["name"], "quantity": 0, "expired": 0})
        entry["expired" if d.is_expired(b) else "quantity"] += b["quantity"]
    return {
        "start": start_d.isoformat(), "end": end_d.isoformat(),
        "rows": sorted(rows, key=lambda r: (r["date"], r["type"])),
        "total_donated": donated, "total_distributed": distributed,
        "stock": [stock[k] for k in sorted(stock)],
    }


def report_csv(report):
    """FR-29: the same rows and totals as the screen."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["FoodShare Tracker report", report["start"], report["end"]])
    w.writerow([])
    w.writerow(["Type", "Date", "Reference", "Item", "Quantity"])
    for r in report["rows"]:
        w.writerow([r["type"], r["date"], r["reference"], r["item"], r["quantity"]])
    w.writerow([])
    w.writerow(["Total donated units", report["total_donated"]])
    w.writerow(["Total distributed units", report["total_distributed"]])
    w.writerow([])
    w.writerow(["Current stock item", "Units in date", "Units expired"])
    for s in report["stock"]:
        w.writerow([s["item"], s["quantity"], s["expired"]])
    return out.getvalue()


# ---------------------------------------------------------------- anonymous feedback

def submit_feedback(store, rating, category, message):
    """No login, and nothing that identifies the person is stored:
    no account, name, IP address or exact time (only the date)."""
    rating = (str(rating).strip() if rating is not None else "")
    if rating:
        try:
            rating = int(rating)
        except ValueError:
            raise DomainError("Please choose one of the faces.")
        if rating not in d.FEEDBACK_RATINGS:
            raise DomainError("Please choose one of the faces.")
    else:
        rating = None
    message = (message or "").strip()
    if rating is None and not message:
        raise DomainError("Please choose a face or write a few words.")
    if len(message) > d.FEEDBACK_MAX_LENGTH:
        raise DomainError(f"Please keep your feedback under {d.FEEDBACK_MAX_LENGTH} characters.")
    if category not in d.FEEDBACK_CATEGORIES:
        category = "General"
    with store.transaction() as tx:
        return tx.insert("feedback", {
            "rating": rating,
            "category": category,
            "message": message,
            "submitted_on": d.today().isoformat(),
            "reviewed": False,
            "archived": False,
        })


def feedback_inbox(store, actor):
    require(actor, d.STAFF, d.MANAGER)
    rows = sorted(store.reader().all("feedback"), key=lambda f: f["id"], reverse=True)
    current = [f for f in rows if not f["archived"]]
    rated = [f["rating"] for f in current if f["rating"]]
    return {
        "rows": rows,
        "total": len(current),
        "new": sum(1 for f in current if not f["reviewed"]),
        "archived": len(rows) - len(current),
        "average": round(sum(rated) / len(rated), 1) if rated else None,
        "by_rating": {r: sum(1 for x in rated if x == r) for r in d.FEEDBACK_RATINGS},
        "by_category": {c: sum(1 for f in current if f["category"] == c)
                        for c in d.FEEDBACK_CATEGORIES},
    }


def mark_feedback_reviewed(store, actor, feedback_id, archive=False):
    """FR-48: New -> Reviewed -> Archived."""
    require(actor, d.STAFF, d.MANAGER)
    with store.transaction() as tx:
        item = tx.get("feedback", feedback_id)
        if not item:
            raise DomainError("Feedback not found.")
        item["reviewed"] = True
        if archive:
            item["archived"] = True
        _audit(tx, actor, "Feedback archived" if archive else "Feedback reviewed",
               f"Feedback {item['id']}")  # never the message itself
        return item


def delete_old_feedback(store, keep_days=d.FEEDBACK_KEEP_DAYS):
    """FR-49: feedback older than 90 days is removed. Run by `python manage.py maintenance`."""
    cutoff = (d.today() - timedelta(days=keep_days)).isoformat()
    with store.transaction() as tx:
        removed = tx.conn.execute("DELETE FROM feedback WHERE submitted_on < ?",
                                  (cutoff,)).rowcount
        if removed:
            _audit(tx, None, "Old feedback removed", "", removed=removed, before=cutoff)
    return removed


# ---------------------------------------------------------------- audit log

def audit_events(store, actor, limit=500):
    """FR-57: IT Admins read sign-in and account events; Managers read stock and food
    events. Nobody can change or delete a row (the database refuses)."""
    require(actor, d.ADMIN, d.MANAGER)
    category = d.SECURITY if actor["role"] == d.ADMIN else d.OPERATIONS
    tx = store.reader()
    rows = tx.find("audit", category=category)
    result = []
    for r in sorted(rows, key=lambda r: r["id"], reverse=True)[:limit]:
        view = dict(r)
        view["actor_name"] = _name(tx, r["actor_id"]) if r["actor_id"] else "System"
        view["details_text"] = ", ".join(f"{k.replace('_', ' ')}: {v}"
                                         for k, v in (r["details"] or {}).items())
        result.append(view)
    return result


# ---------------------------------------------------------------- dashboard numbers

def dashboard_stats(store, actor):
    require(actor, d.STAFF, d.MANAGER)
    refresh_swap_lifecycle(store)
    tx = store.reader()
    reserved = _reserved_map(tx)
    batches = [_with_status(tx, b, reserved) for b in tx.all("batches")]
    alerts = stock_alerts(store, actor)
    today = d.today().isoformat()
    waiting = tx.find("allocations", status=d.ALLOCATED)
    return {
        "units": usable_units(batches),  # same figure as "Units available" on Inventory
        "near_expiry": len(alerts["near_expiry"]),
        "low_stock": len(alerts["low_stock"]),
        "pending_swaps": tx.count("swaps", status=d.PENDING),
        "queue_today": sum(1 for a in waiting if a["pickup_date"] == today),
        "upcoming_pickups": len(waiting),
        "new_feedback": sum(1 for f in tx.all("feedback")
                            if not f["reviewed"] and not f["archived"]),
        "scheduled_donations": tx.count("donations", status=d.SCHEDULED),
    }

