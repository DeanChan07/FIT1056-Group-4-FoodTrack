"""Idempotent retention and missed-pickup maintenance; no background worker is required."""
from datetime import datetime, timedelta
from .. import domain as d
from .base import _audit, _notify, _now


def close_queue_entry(tx, allocation_id, state):
    for entry in tx.find("queue_entries", allocation_id=allocation_id):
        if entry["state"] in (d.WAITING, d.SERVING):
            entry.update(state=state, closed_at=_now())


def expire_overdue_allocations(store):
    """Keep same-day late pickups reserved; release missed pickups from the next day.

    A window crossing midnight remains valid until its actual exclusive end.
    Staff must create a new allocation after release; an exception cannot revive it.
    """
    def overdue(tx, allocation):
        return (allocation["pickup_date"] < d.today().isoformat()
                and d.now() >= d.pickup_end(allocation, tx.setting("queue_window_minutes")))
    with store.reader() as tx:
        due = any(overdue(tx, a) for a in tx.find("allocations", status=d.ALLOCATED))
    if not due:
        return 0
    from .allocations import _close
    count = 0
    with store.transaction() as tx:
        for allocation in tx.find("allocations", status=d.ALLOCATED):
            if overdue(tx, allocation):
                _close(tx, None, allocation, d.EXPIRED, "The pickup day has passed. Please contact Staff for a new allocation.")
                _notify(tx, allocation["recipient_id"], "Missed pickup",
                        "Your missed pickup has closed. Please contact the food bank to arrange another pickup.")
                _audit(tx, None, "Allocation expired", f"Allocation {allocation['id']}")
                count += 1
    return count


def run_maintenance(store, force=False):
    """On app activity, check once per hour for retention; expire pickups on every run."""
    expired = expire_overdue_allocations(store)
    with store.reader() as tx:
        last = tx.setting("maintenance_at")
        if not force and last and d.now() - datetime.fromisoformat(last) < timedelta(hours=1):
            return {"allocations": expired, "feedback": 0, "sessions": 0}
    with store.transaction() as tx:
        last = tx.setting("maintenance_at")
        if not force and last and d.now() - datetime.fromisoformat(last) < timedelta(hours=1):
            return {"allocations": expired, "feedback": 0, "sessions": 0}
        feedback = tx.delete_before("feedback", "submitted_on", (d.today() - timedelta(days=90)).isoformat())
        sessions = 0
        for session in tx.all("sessions"):
            person = tx.get("users", session["user_id"])
            if (not person or not person["active"]
                or d.now() - datetime.fromisoformat(session["last_seen"]) >= timedelta(minutes=15)
                or d.now() - datetime.fromisoformat(session["created_at"]) >= timedelta(hours=8)):
                sessions += tx.delete("sessions", id=session["id"])
        tx.delete_before("public_limits", "started_at", (d.now() - timedelta(days=1)).isoformat())
        tx.set_setting("maintenance_at", _now())
    return {"allocations": expired, "feedback": feedback, "sessions": sessions}
