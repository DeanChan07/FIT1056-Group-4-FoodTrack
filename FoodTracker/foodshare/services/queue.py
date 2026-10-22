"""One pickup desk: arrival order, private wait estimates and audited transitions."""
from datetime import timedelta
from .. import domain as d
from ..domain import DomainError, PermissionDenied
from .allocations import _close
from .base import _audit, _name, _notify, _now, _positive_int, require
from .maintenance import close_queue_entry, expire_overdue_allocations
from .people import volunteer_distributing_on


def _desk_access(tx, actor, allocation):
    require(actor, d.STAFF, d.VOLUNTEER)
    if actor["role"] == d.VOLUNTEER and not (
        allocation["pickup_date"] == d.today().isoformat()
        and volunteer_distributing_on(tx, actor, d.today().isoformat())):
        raise PermissionDenied("You need a Distribution task today for this pickup.")


def _clock(minutes):
    days, minute = divmod(minutes, 24 * 60)
    return d.format_time(minute) + (f" (+{days} day)" if days else "")


def _queue(tx, on_date):
    rows = tx.find("allocations", status=d.ALLOCATED, pickup_date=on_date)
    step = tx.setting("minutes_per_pickup")
    paused = tx.setting("queue_paused")
    active_entries = {entry["allocation_id"]: entry["id"]
                      for state in (d.WAITING, d.SERVING)
                      for entry in tx.find("queue_entries", state=state)}
    def order(a):
        return (0 if a["queue_state"] == d.SERVING else 1 if a["checked_in_at"] else 2,
                a["checked_in_at"] or a["pickup_time"], active_entries.get(a["id"], a["id"]))
    result = []
    active_before = 0
    for index, a in enumerate(sorted(rows, key=order), 1):
        arrived = bool(a["checked_in_at"])
        waiting = a["queue_state"] == d.WAITING
        lo, hi = active_before * step, (active_before + 1) * step
        booked = d.parse_time(a["pickup_time"])
        # Clock previews are supplemental; the SRS waiting range counts active arrivals only.
        base = d.now().hour * 60 + d.now().minute if on_date == d.today().isoformat() else booked
        start = base + lo
        result.append({"allocation_id": a["id"], "recipient_id": a["recipient_id"],
            "recipient_name": _name(tx, a["recipient_id"]),
            "position": active_before + 1 if arrived else None,
            "ahead": active_before if arrived else None,
            "booked_time": a["pickup_time"], "checked_in_at": a["checked_in_at"],
            "state": a["queue_state"] or "Not here yet",
            "wait_min": lo if waiting and not paused else None,
            "wait_max": hi if waiting and not paused else None,
            "window_start": _clock(start) if waiting and not paused else None,
            "window_end": _clock(start + step) if waiting and not paused else None,
            "delay": max(0, start - booked) if waiting and not paused else None,
            "item_count": sum(i["quantity"] for i in a["items"])})
        if arrived:
            active_before += 1
    return result


def pickup_queue(store, actor, on_date=None):
    require(actor, d.STAFF, d.VOLUNTEER)
    expire_overdue_allocations(store)
    with store.reader() as tx:
        if actor["role"] == d.VOLUNTEER:
            _desk_access(tx, actor, {"pickup_date": on_date or d.today().isoformat()})
        upcoming = {}
        for a in tx.find("allocations", status=d.ALLOCATED):
            if actor["role"] == d.VOLUNTEER and a["pickup_date"] != d.today().isoformat():
                continue
            upcoming[a["pickup_date"]] = upcoming.get(a["pickup_date"], 0) + 1
        if not on_date:
            later = sorted(day for day in upcoming if day >= d.today().isoformat())
            on_date = later[0] if later else d.today().isoformat()
        on_date = d.parse_date(on_date).isoformat()
        return {"date": on_date, "queue": _queue(tx, on_date), "upcoming": sorted(upcoming.items()),
                "minutes_per_pickup": tx.setting("minutes_per_pickup"),
                "queue_window_minutes": tx.setting("queue_window_minutes"),
                "paused": tx.setting("queue_paused")}


def _can_check_in_now(allocation, window):
    return (d.pickup_start(allocation) - timedelta(minutes=d.CHECK_IN_EARLY_MINUTES)
            <= d.now() < d.pickup_end(allocation, window))


def queue_status(store, actor, allocation_id):
    require(actor, d.RECIPIENT, d.STAFF)
    expire_overdue_allocations(store)
    with store.reader() as tx:
        allocation = tx.get("allocations", allocation_id)
        if not allocation:
            raise DomainError("Allocation not found.")
        if actor["role"] == d.RECIPIENT and allocation["recipient_id"] != actor["id"]:
            raise PermissionDenied("You do not have access to this allocation.")
        if allocation["status"] != d.ALLOCATED:
            return None
        queue = _queue(tx, allocation["pickup_date"])
        mine = next(q for q in queue if q["allocation_id"] == allocation_id)
        public = {key: mine[key] for key in ("position", "ahead", "booked_time", "window_start",
                  "window_end", "delay", "state", "wait_min", "wait_max")}
        public.update(date=allocation["pickup_date"], total=sum(bool(a["checked_in_at"]) for a in queue),
            checked_in=bool(allocation["checked_in_at"]), paused=tx.setting("queue_paused"),
            can_check_in=not allocation["checked_in_at"] and not tx.setting("queue_paused")
                         and _can_check_in_now(allocation, tx.setting("queue_window_minutes")),
            window_ended=d.now() >= d.pickup_end(allocation, tx.setting("queue_window_minutes")),
            updated_at=_now())
        return public


def check_in(store, actor, allocation_id, exception_reason=""):
    """Idempotent check-in. Only Staff may admit a same-day late arrival with a reason."""
    require(actor, d.RECIPIENT, d.STAFF, d.VOLUNTEER)
    expire_overdue_allocations(store)
    with store.transaction() as tx:
        a = tx.get("allocations", allocation_id)
        if not a:
            raise DomainError("Allocation not found.")
        if actor["role"] == d.RECIPIENT:
            if a["recipient_id"] != actor["id"]:
                raise PermissionDenied("You do not have access to this allocation.")
        else:
            _desk_access(tx, actor, a)
        recipient = tx.get("users", a["recipient_id"])
        if not recipient or not recipient["active"]:
            raise DomainError("This Recipient account is inactive.")
        if a["status"] != d.ALLOCATED:
            raise DomainError(f"This pickup is already {a['status'].lower()}.")
        if a["checked_in_at"]:
            return a
        if tx.setting("queue_paused"):
            raise DomainError("Queue paused. Please ask Staff before checking in.")
        window = tx.setting("queue_window_minutes")
        if not _can_check_in_now(a, window):
            late = d.now() >= d.pickup_end(a, window)
            if not (late and a["pickup_date"] == d.today().isoformat()
                    and actor["role"] == d.STAFF and exception_reason.strip()):
                if late:
                    raise DomainError("The pickup window has ended. Please contact Staff for help.")
                raise DomainError(f"You can check in from {d.CHECK_IN_EARLY_MINUTES} minutes before your pickup time.")
            from .base import _clean
            a["exception_reason"] = _clean(exception_reason, "an exception reason")
        a.update(checked_in_at=_now(), queue_state=d.WAITING)
        tx.insert("queue_entries", {"allocation_id": a["id"], "checked_in_at": a["checked_in_at"],
                                   "state": d.WAITING})
        _audit(tx, actor, "Checked in", f"Allocation {a['id']}", late_exception=bool(a.get("exception_reason")))
        return a


def move_in_queue(store, actor, allocation_id, action):
    require(actor, d.STAFF, d.VOLUNTEER)
    with store.transaction() as tx:
        a = tx.get("allocations", allocation_id)
        if not a or a["status"] != d.ALLOCATED:
            raise DomainError("Only pickups that are still waiting can be moved.")
        _desk_access(tx, actor, a)
        if action in ("no_show", "wait"):
            require(actor, d.STAFF)
        if action == "serve":
            if any(other["id"] != a["id"] and other["queue_state"] == d.SERVING
                   for other in tx.find("allocations", status=d.ALLOCATED, pickup_date=a["pickup_date"])):
                raise DomainError("The pickup desk is already serving someone.")
            if a["queue_state"] != d.WAITING:
                raise DomainError("Only someone who has checked in can be served.")
            a["queue_state"] = d.SERVING
        elif action == "wait":
            if a["queue_state"] != d.SERVING:
                raise DomainError("Only someone being served can go back to waiting.")
            a["queue_state"] = d.WAITING
        elif action == "no_show":
            if d.now() < d.pickup_end(a, tx.setting("queue_window_minutes")):
                raise DomainError("Please wait until the pickup window has ended before marking a no-show.")
            _close(tx, actor, a, d.NO_SHOW, "Did not come to collect")
            _notify(tx, a["recipient_id"], "Missed pickup", "Please contact the food bank to arrange another pickup.")
        else:
            raise DomainError("Unknown queue action.")
        for entry in tx.find("queue_entries", allocation_id=a["id"]):
            if entry["state"] in (d.WAITING, d.SERVING):
                entry["state"] = a["queue_state"]
        _audit(tx, actor, "Queue updated", f"Allocation {a['id']}", step=action)
        return a


def set_queue_settings(store, actor, minutes_per_pickup, window_minutes, paused=None):
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
