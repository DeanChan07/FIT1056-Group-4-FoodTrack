"""F-04 needs profiles and F-06 volunteer tasks (FR-17 to FR-19, FR-21, FR-24, FR-25)."""

from .. import domain as d
from ..domain import DomainError, EditConflict
from .base import _audit, _clean, _name, _now, _positive_int, _public_user, require


# ---------------------------------------------------------------- needs profiles

def _can_manage_profile(actor, recipient_id):
    require(actor, d.RECIPIENT, d.STAFF)
    if actor and actor["role"] == d.RECIPIENT and actor["id"] == recipient_id:
        return
    require(actor, d.STAFF)


def get_profile(store, actor, recipient_id):
    _can_manage_profile(actor, recipient_id)
    with store.reader() as read_tx:
        return read_tx.find_one("profiles", recipient_id=recipient_id)


def save_profile(store, actor, recipient_id, fields, consent=False):
    """FR-17: the Recipient, or Staff with the Recipient's permission."""
    _can_manage_profile(actor, recipient_id)
    if actor["role"] == d.STAFF and not consent:
        raise DomainError("Please confirm the Recipient gave permission for this change.")
    household = _positive_int(fields.get("household_size"), "Household size")
    if household > 100:
        raise DomainError("Household size must be at most 100. Please contact Staff for larger groups.")
    urgency = fields.get("urgency") or "Standard"
    if urgency not in d.URGENCY_LEVELS:
        raise DomainError("Please choose an urgency option from the list.")
    with store.transaction() as tx:
        recipient = tx.get("users", recipient_id)
        if not recipient or recipient["role"] != d.RECIPIENT:
            raise DomainError("Recipient not found.")
        profile = tx.find_one("profiles", recipient_id=recipient_id)
        if not profile:
            profile = tx.insert("profiles", {"recipient_id": recipient_id, "version": 0})
        # Two people editing at once: the later save must not wipe out the earlier one.
        loaded = fields.get("loaded_version")
        if loaded is not None and str(loaded).strip() != str(profile.get("version") or 0):
            raise EditConflict("Someone else changed this profile while you were editing. "
                               "The form now shows their changes; please make yours again.")
        profile.update({
            "version": (profile.get("version") or 0) + 1,
            "household_size": household,
            "allergies": d.normalize_allergens(fields.get("allergies")),
            "allergies_confirmed": bool(fields.get("allergies_confirmed")),
            "dietary_restrictions": d.split_list(fields.get("dietary_restrictions")),
            "cultural_needs": d.split_list(fields.get("cultural_needs")),
            "accessibility_needs": (fields.get("accessibility_needs") or "").strip(),
            "preferred_pickup": (fields.get("preferred_pickup") or "").strip(),
            "urgency": urgency,
            "updated_by": actor["id"],
            "updated_at": _now(),
        })
        if actor["role"] == d.STAFF:  # the change itself is private; only that it happened
            _audit(tx, actor, "Needs profile changed with permission", recipient["username"])
        return profile


def recipients_for_allocation(store, actor):
    """FR-19 and FR-21: needs summaries in name order, never ranked."""
    require(actor, d.STAFF)
    with store.reader() as tx:
        rows = []
        for user in tx.find("users", role=d.RECIPIENT, active=True):
            profile = tx.find_one("profiles", recipient_id=user["id"])
            rows.append({"id": user["id"], "display_name": user["display_name"],
                         "summary": d.needs_summary(profile)})
        return sorted(rows, key=lambda r: r["display_name"].lower())


# ---------------------------------------------------------------- volunteer tasks

def list_volunteers(store, actor):
    require(actor, d.STAFF, d.MANAGER)
    with store.reader() as read_tx:
        return [_public_user(u) for u in read_tx.find("users", role=d.VOLUNTEER, active=True)]


def assign_task(store, actor, volunteer_id, task_type, shift_date, shift_time, instructions):
    """FR-24."""
    require(actor, d.STAFF, d.MANAGER)
    if task_type not in d.TASK_TYPES:
        raise DomainError("Please choose Receiving or Distribution.")
    day = d.parse_date(_clean(shift_date, "the shift date"))
    minutes = d.parse_time(_clean(shift_time, "the shift time"))
    if day < d.today():
        raise DomainError("The shift date cannot be in the past.")
    with store.transaction() as tx:
        volunteer = tx.get("users", volunteer_id)
        if not volunteer or volunteer["role"] != d.VOLUNTEER or not volunteer["active"]:
            raise DomainError("Please choose an active Volunteer.")
        _task_conflict(tx, volunteer_id, day.isoformat(), d.format_time(minutes))
        task = tx.insert("tasks", {
            "volunteer_id": volunteer["id"],
            "task_type": task_type,
            "shift_date": day.isoformat(),
            "shift_time": d.format_time(minutes),
            "instructions": _clean(instructions, "instructions", required=False),
            "assigned_by": actor["id"], "status": "Active", "version": 1,
        })
        _audit(tx, actor, "Task assigned", volunteer["username"], task=task_type,
               shift=f"{task['shift_date']} {task['shift_time']}")
        return task


def list_tasks(store, actor):
    """FR-25: Volunteers see only their own tasks."""
    require(actor, d.VOLUNTEER, d.STAFF, d.MANAGER)
    with store.reader() as tx:
        if actor and actor["role"] == d.VOLUNTEER:
            rows = tx.find("tasks", volunteer_id=actor["id"])
        else:
            require(actor, d.STAFF, d.MANAGER)
            rows = tx.all("tasks")
        result = []
        for t in sorted(rows, key=lambda t: (t["shift_date"], t["shift_time"])):
            view = dict(t)
            view["volunteer_name"] = _name(tx, t["volunteer_id"])
            result.append(view)
        return result


def volunteer_distributing_on(tx, actor, day):
    """M10: a Volunteer may hand out food only on a day they have a Distribution shift."""
    return volunteer_assigned_on(tx, actor, day, "Distribution")


def volunteer_assigned_on(tx, actor, day, kind):
    return any(t["task_type"] == kind and t["shift_date"] == day
               and t.get("status") != d.CANCELLED
               for t in tx.find("tasks", volunteer_id=actor["id"]))


def _task_conflict(tx, volunteer_id, day, at, exclude=None):
    if any(t["id"] != exclude and t.get("status") != d.CANCELLED
           and t["shift_date"] == day and t["shift_time"] == at
           for t in tx.find("tasks", volunteer_id=volunteer_id)):
        raise DomainError("This Volunteer already has a task at that date and time.")


def update_task(store, actor, task_id, volunteer_id, task_type, shift_date, shift_time,
                instructions, *, loaded_version=None):
    require(actor, d.STAFF, d.MANAGER)
    if task_type not in d.TASK_TYPES:
        raise DomainError("Please choose Receiving or Distribution.")
    day, at = d.parse_date(shift_date), d.format_time(d.parse_time(shift_time))
    if day < d.today():
        raise DomainError("The shift date cannot be in the past.")
    with store.transaction() as tx:
        task = tx.get("tasks", task_id)
        person = tx.get("users", volunteer_id)
        if not task or task.get("status") == d.CANCELLED:
            raise DomainError("Only active tasks can be changed.")
        if not person or person["role"] != d.VOLUNTEER or not person["active"]:
            raise DomainError("Please choose an active Volunteer.")
        if loaded_version is not None and loaded_version != (task.get("version") or 0):
            raise EditConflict("This task changed. Please reload it before saving.")
        _task_conflict(tx, volunteer_id, day.isoformat(), at, task_id)
        task.update(volunteer_id=volunteer_id, task_type=task_type, shift_date=day.isoformat(),
                    shift_time=at, instructions=_clean(instructions, "instructions", required=False),
                    version=(task.get("version") or 0) + 1)
        _audit(tx, actor, "Task changed", f"Task {task_id}")
        return task


def cancel_task(store, actor, task_id, reason, confirmed=False):
    require(actor, d.STAFF, d.MANAGER)
    if not confirmed:
        raise DomainError("Please confirm the task cancellation.")
    reason = _clean(reason, "a cancellation reason")
    with store.transaction() as tx:
        task = tx.get("tasks", task_id)
        if not task:
            raise DomainError("Task not found.")
        if task.get("status") == d.CANCELLED:
            return task
        task.update(status=d.CANCELLED, cancel_reason=reason, version=(task.get("version") or 0) + 1)
        _audit(tx, actor, "Task cancelled", f"Task {task_id}")
        return task
