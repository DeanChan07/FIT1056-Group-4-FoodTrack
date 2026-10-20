"""Small helpers every service module uses: role checks, input cleaning,
notices and the audit log."""

from datetime import datetime

from .. import domain as d
from ..domain import DomainError, PermissionDenied


def _now():
    return d.now().isoformat(timespec="seconds")


def require(actor, *roles):
    """FR-03: stop unless the signed-in person has one of these roles."""
    if not actor or not actor.get("active", True) or actor["role"] not in roles:
        raise PermissionDenied("You do not have access to this page or action.")


def _clean(text, field, required=True):
    value = (text or "").strip()
    if required and not value:
        raise DomainError(f"Please fill in {field}.")
    return value


def _positive_int(value, field, allow_zero=False):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise DomainError(f"{field} must be a whole number.")
    if number < 0 or (number == 0 and not allow_zero):
        raise DomainError(f"{field} must be {'zero or more' if allow_zero else 'at least 1'}.")
    return number


def _not_in_past(day_text, time_text, what):
    """New bookings must be for today or later, and not for a time that has already gone."""
    day = d.parse_date(_clean(day_text, f"the {what} date"))
    minutes = d.parse_time(_clean(time_text, f"the {what} time"))
    when = datetime.combine(day, datetime.min.time()).replace(hour=minutes // 60,
                                                              minute=minutes % 60)
    if day < d.today() or when < d.now().replace(second=0, microsecond=0):
        raise DomainError(f"The {what} date and time cannot be in the past.")
    return day.isoformat(), d.format_time(minutes)


def _public_user(user):
    hidden = {"password_hash", "failed_logins", "locked_until"}
    return {k: v for k, v in user.items() if k not in hidden}


def _name(tx, user_id):
    user = tx.get("users", user_id) if user_id else None
    return user["display_name"] if user else "Unknown"


def _notify(tx, user_id, kind, message):
    return tx.insert("notifications", {"user_id": user_id, "kind": kind, "message": message,
                                       "read": False, "created_at": _now()})


def _audit(tx, actor, action, target="", category=d.OPERATIONS, **details):
    """FR-56: one append-only row per important change. Never pass swap reasons,
    needs details, feedback text or passwords in here (FR-57)."""
    tx.insert("audit", {
        "at": _now(),
        "actor_id": actor["id"] if actor else None,
        "actor_role": actor["role"] if actor else None,
        "category": category,
        "action": action,
        "target": target,
        "details": details or {},
    })
