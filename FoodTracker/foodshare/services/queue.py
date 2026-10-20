"""Pickup queue with check-in (FR-50 to FR-55).

Before the day, a Recipient sees an estimate from the booked times. On the day they
check in (themselves, or Staff do it for them at the desk). Checked-in people are
served in the order they arrived; Staff move them to Serving, record the collection,
or mark No-show (which puts their food back on the shelf).
"""

from datetime import datetime

from .. import domain as d
from ..domain import DomainError, PermissionDenied
from .allocations import _close
from .base import _audit, _name, _notify, _now, _positive_int, require


def _minutes(moment):
    return moment.hour * 60 + moment.minute


def _queue(tx, on_date):
    """Uncollected allocations for one day, in serving order, each with an estimated
    window. Arrived people come first (Serving, then by check-in time); people not
    here yet follow in booked-time order. Nobody starts before the person ahead of them
    has had their minutes_per_pickup."""
    step = tx.setting("minutes_per_pickup")
    window = tx.setting("queue_window_minutes")
    now = d.now()
    is_today = on_date == d.today().isoformat()
    rows = tx.find("allocations", status=d.ALLOCATED, pickup_date=on_date)

    def order(a):
        if a["queue_state"] == d.SERVING:
            return (0, a["checked_in_at"] or "", a["id"])
        if a["checked_in_at"]:
            return (1, a["checked_in_at"], a["id"])
        return (2, d.format_time(d.parse_time(a["pickup_time"])), a["id"])

    queue, previous = [], None
    for position, a in enumerate(sorted(rows, key=order), start=1):
        booked = d.parse_time(a["pickup_time"])
        arrived = bool(a["checked_in_at"])
        base = _minutes(datetime.fromisoformat(a["checked_in_at"])) if arrived else booked
        if arrived and is_today:
            base = max(base, _minutes(now))
        start = base if previous is None else max(base, previous + step)
        previous = start
        queue.append({
            "allocation_id": a["id"],
            "recipient_id": a["recipient_id"],
            "recipient_name": _name(tx, a["recipient_id"]),
            "position": position,
            "ahead": position - 1,
            "booked_time": a["pickup_time"],
            "checked_in_at": a["checked_in_at"],
            "state": a["queue_state"] or ("Waiting" if arrived else "Not here yet"),
            "window_start": d.format_time(start),
            "window_end": d.format_time(start + window),
            "delay": max(0, start - booked),
            "item_count": sum(i["quantity"] for i in a["items"]),
        })
    return queue


def pickup_queue(store, actor, on_date=None):
    """Staff view of one day's queue, plus the upcoming days that have pickups."""
    require(actor, d.STAFF)
    tx = store.reader()
    upcoming = {}
    for a in tx.find("allocations", status=d.ALLOCATED):
        upcoming[a["pickup_date"]] = upcoming.get(a["pickup_date"], 0) + 1
    if not on_date:
        later = sorted(day for day in upcoming if day >= d.today().isoformat())
        on_date = later[0] if later else d.today().isoformat()
    on_date = d.parse_date(on_date).isoformat()
    settings = tx.settings()
    return {
        "date": on_date,
        "queue": _queue(tx, on_date),
        "upcoming": sorted(upcoming.items()),
        "minutes_per_pickup": settings["minutes_per_pickup"],
        "queue_window_minutes": settings["queue_window_minutes"],
        "paused": settings["queue_paused"],
    }


def _can_check_in_now(allocation):
    return (allocation["pickup_date"] == d.today().isoformat()
            and _minutes(d.now()) >= d.parse_time(allocation["pickup_time"])
            - d.CHECK_IN_EARLY_MINUTES)


def queue_status(store, actor, allocation_id):
    """A Recipient sees only their own place: position, people ahead and a time window,
    never anyone else's name (FR-52, FR-53). While the queue is paused, no estimate."""
    tx = store.reader()
    allocation = tx.get("allocations", allocation_id)
    if not allocation:
        raise DomainError("Allocation not found.")
    if actor and actor["role"] == d.RECIPIENT:
        if allocation["recipient_id"] != actor["id"]:
            raise PermissionDenied("You do not have access to this allocation.")
    else:
        require(actor, d.STAFF)
    if allocation["status"] != d.ALLOCATED:
        return None
    queue = _queue(tx, allocation["pickup_date"])
    mine = next(q for q in queue if q["allocation_id"] == allocation["id"])
    return {
        "date": allocation["pickup_date"],
        "position": mine["position"],
        "ahead": mine["ahead"],
        "total": len(queue),
        "booked_time": mine["booked_time"],
        "window_start": mine["window_start"],
        "window_end": mine["window_end"],
        "delay": mine["delay"],
        "state": mine["state"],
        "checked_in": bool(allocation["checked_in_at"]),
        "can_check_in": not allocation["checked_in_at"] and _can_check_in_now(allocation),
        "paused": tx.setting("queue_paused"),
        "updated_at": _now(),
    }


def check_in(store, actor, allocation_id):
    """FR-50: the Recipient (or Staff for them) says they have arrived. Doing it twice
    changes nothing, so a double tap cannot move anyone down the queue."""
    with store.transaction() as tx:
        allocation = tx.get("allocations", allocation_id)
        if not allocation:
            raise DomainError("Allocation not found.")
        if actor and actor["role"] == d.RECIPIENT:
            if allocation["recipient_id"] != actor["id"]:
                raise PermissionDenied("You do not have access to this allocation.")
        else:
            require(actor, d.STAFF)
        if allocation["status"] != d.ALLOCATED:
            raise DomainError(f"This pickup is already {allocation['status'].lower()}.")
        if allocation["checked_in_at"]:
            return allocation
        if not _can_check_in_now(allocation):
            raise DomainError(f"You can check in on {allocation['pickup_date']} from "
                              f"{d.CHECK_IN_EARLY_MINUTES} minutes before your pickup time.")
        allocation["checked_in_at"] = _now()
        allocation["queue_state"] = d.WAITING
        _audit(tx, actor, "Checked in", f"Allocation {allocation['id']}")
        return allocation


def move_in_queue(store, actor, allocation_id, action):
    """FR-51: Staff move someone along. action is "serve", "wait" or "no_show"."""
    require(actor, d.STAFF)
    with store.transaction() as tx:
        allocation = tx.get("allocations", allocation_id)
        if not allocation or allocation["status"] != d.ALLOCATED:
            raise DomainError("Only pickups that are still waiting can be moved.")
        if action == "serve":
            if allocation["queue_state"] != d.WAITING:
                raise DomainError("Only someone who has checked in can be served.")
            allocation["queue_state"] = d.SERVING
        elif action == "wait":
            if allocation["queue_state"] != d.SERVING:
                raise DomainError("Only someone being served can go back to waiting.")
            allocation["queue_state"] = d.WAITING
        elif action == "no_show":
            if allocation["pickup_date"] > d.today().isoformat():
                raise DomainError("Someone can only be marked as not coming on or after "
                                  "their pickup day.")
            _close(tx, actor, allocation, d.NO_SHOW, "Did not come to collect")
            _notify(tx, allocation["recipient_id"], "Missed pickup",
                    "We missed you at your pickup. Please contact the food bank to book "
                    "another time.")
        else:
            raise DomainError("Unknown queue action.")
        _audit(tx, actor, "Queue updated", f"Allocation {allocation['id']}", step=action)
        return allocation


def set_queue_settings(store, actor, minutes_per_pickup, window_minutes, paused=None):
    """FR-55: timing, and pausing estimates when the desk is held up."""
    require(actor, d.STAFF, d.MANAGER)
    step = _positive_int(minutes_per_pickup, "Minutes per pickup")
    window = _positive_int(window_minutes, "Time window")
    if step > 60 or window > 120:
        raise DomainError("Please use at most 60 minutes per pickup and a 120 minute window.")
    with store.transaction() as tx:
        tx.set_setting("minutes_per_pickup", step)
        tx.set_setting("queue_window_minutes", window)
        if paused is not None:
            tx.set_setting("queue_paused", bool(paused))
        _audit(tx, actor, "Queue settings changed", "", minutes_per_pickup=step,
               window_minutes=window, paused=bool(tx.setting("queue_paused")))
