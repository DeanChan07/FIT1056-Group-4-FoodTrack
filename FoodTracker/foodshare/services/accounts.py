"""F-01 accounts and roles: registration, signing in, sessions, team accounts,
and the local IT Admin bootstrap and recovery (FR-01 to FR-07, FR-38 to FR-40)."""

import hashlib
import secrets
import re
from datetime import datetime, timedelta

from .. import domain as d
from ..domain import DomainError, PermissionDenied
from ..passwords import check_password, hash_password
from .public_controls import public_limit
from .base import _audit, _clean, _now, _public_user, require

# Checked when the username does not exist, so a wrong username takes as long as a wrong password.
_DUMMY_HASH = hash_password("not-a-real-password-just-for-timing")


def _check_new_password(password):
    password = password or ""
    if not d.PASSWORD_MIN_LENGTH <= len(password) <= d.PASSWORD_MAX_LENGTH:
        raise DomainError(f"Password must be {d.PASSWORD_MIN_LENGTH} to "
                          f"{d.PASSWORD_MAX_LENGTH} characters. A short sentence is easy to "
                          "remember, for example: green tea at four o'clock")
    return password


def _create_user(tx, username, password, display_name, role, created_by=None):
    username = _clean(username, "a username").lower()
    _clean(display_name, "a display name", max_length=100)
    if not re.fullmatch(r"[a-z0-9_.-]{1,64}", username):
        raise DomainError("Username must use 1 to 64 letters, numbers, dots, underscores or hyphens.")
    _check_new_password(password)
    if tx.find_one("users", username=username):
        raise DomainError("That username is already taken.")
    return tx.insert("users", {
        "username": username,
        "password_hash": hash_password(password),
        "display_name": display_name.strip(),
        "role": role,
        "active": True,
        "created_by": created_by,
        "created_at": _now(),
        "failed_logins": 0,
    })


def register_recipient(store, username, password, display_name, role=None):
    """FR-01: public self-registration creates only Recipient accounts."""
    if role not in (None, "", d.RECIPIENT):
        raise PermissionDenied("Only Recipient accounts can be created here.")
    public_limit(store, "registration", 30)
    with store.transaction() as tx:
        user = _create_user(tx, username, password, display_name, d.RECIPIENT)
        _audit(tx, user, "Recipient registered", user["username"], d.SECURITY)
        return _public_user(user)


def login(store, username, password):
    """NFR-09: five failures within fifteen minutes cause a fifteen-minute delay."""
    name = (username or "").strip().lower()
    problem = None
    with store.transaction() as tx:
        user = tx.find_one("users", username=name)
        if not user:
            check_password(_DUMMY_HASH, password or "")
            raise DomainError("Username or password is incorrect.")
        locked = user.get("locked_until")
        if locked and datetime.fromisoformat(locked) > d.now():
            raise DomainError("Username or password is incorrect. Please try again later.")
        if not check_password(user["password_hash"], password or ""):
            started = user.get("failure_started_at")
            if not started or d.now() - datetime.fromisoformat(started) >= timedelta(minutes=15):
                user["failed_logins"] = 0
                user["failure_started_at"] = _now()
            user["failed_logins"] = (user.get("failed_logins") or 0) + 1
            if user["failed_logins"] >= d.FREE_LOGIN_ATTEMPTS:
                user["locked_until"] = (d.now() + timedelta(minutes=15)).isoformat()
            _audit(tx, None, "Sign-in failed", user["username"], d.SECURITY,
                   result="Denied", failed_in_a_row=user["failed_logins"])
            problem = "Username or password is incorrect."
        elif not user["active"]:
            problem = "This account is inactive. Please contact the food bank."
        else:
            user["failed_logins"] = 0
            user["failure_started_at"] = None
            user["locked_until"] = None
            _audit(tx, user, "Signed in", user["username"], d.SECURITY)
            return _public_user(user)
    raise DomainError(problem)  # raised after saving, so the failed attempt is counted


def get_user(store, user_id):
    with store.reader() as read_tx:
        user = read_tx.get("users", user_id)
    return _public_user(user) if user else None


# ---------------------------------------------------------------- sessions (NFR-09)

def _token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(store, user):
    """Make a sign-in that survives a page refresh. Only a hash of the token is stored."""
    token = secrets.token_urlsafe(32)
    with store.transaction() as tx:
        live = tx.get("users", user["id"])
        if not live or not live["active"]:
            raise PermissionDenied("This account is no longer active.")
        tx.insert("sessions", {"token_hash": _token_hash(token), "user_id": user["id"],
                               "created_at": _now(), "last_seen": _now()})
    return token


def _session_state(tx, token_hash):
    session = tx.find_one("sessions", token_hash=token_hash)
    if not session:
        return None, None, None
    user = tx.get("users", session["user_id"])
    moment = d.now()
    reason = None
    if not user or not user["active"]:
        reason = "Your account is no longer active."
    elif moment - datetime.fromisoformat(session["last_seen"]) >= timedelta(minutes=d.SESSION_IDLE_MINUTES):
        reason = "You were signed out after 15 minutes without activity. Please sign in again."
    elif moment - datetime.fromisoformat(session["created_at"]) >= timedelta(hours=d.SESSION_MAX_HOURS):
        reason = "You were signed out after 8 hours. Please sign in again."
    return session, user, reason


def resume_session(store, token, *, touch=True):
    """Validate every request; renew activity at most once per thirty seconds."""
    if not isinstance(token, str) or not token:
        return None, None
    hashed = _token_hash(token)
    with store.reader() as tx:
        session, user, reason = _session_state(tx, hashed)
        if not session:
            return None, None
        due = touch and d.now() - datetime.fromisoformat(session["last_seen"]) >= timedelta(seconds=30)
        if not reason and not due:
            return _public_user(user), None
    with store.transaction() as tx:
        session, user, reason = _session_state(tx, hashed)
        if not session:
            return None, None
        if reason:
            tx.delete("sessions", token_hash=hashed)
            return None, reason
        if touch:
            session["last_seen"] = _now()
        return _public_user(user), None


def end_session(store, token):
    if not token:
        return
    with store.transaction() as tx:
        tx.delete("sessions", token_hash=_token_hash(token))


def _end_all_sessions(tx, user_id):
    tx.delete("sessions", user_id=user_id)


# ---------------------------------------------------------------- team accounts

def create_internal_account(store, actor, username, password, display_name, role,
                            *, current_password="", confirmed=False):
    """FR-04 and FR-05."""
    require(actor, d.MANAGER, d.ADMIN)
    if role not in d.MANAGEABLE_ROLES.get(actor["role"], ()):
        raise PermissionDenied("Your role cannot create that type of account.")
    with store.transaction() as tx:
        if role == d.ADMIN:
            _reauth_admin(tx, actor, current_password, confirmed)
        user = _create_user(tx, username, password, display_name, role, actor["id"])
        _audit(tx, actor, "Account created", user["username"], d.SECURITY,
               role=d.ROLE_LABELS[role])
        return _public_user(user)


def _reauth_admin(tx, actor, password, confirmed):
    require(actor, d.ADMIN)
    live = tx.get("users", actor["id"])
    if not confirmed or not live or not live["active"] or live["role"] != d.ADMIN:
        raise PermissionDenied("Please confirm this IT Admin change.")
    if not check_password(live["password_hash"], password or ""):
        raise PermissionDenied("Please enter your current password to confirm this IT Admin change.")


def list_accounts(store, actor):
    require(actor, d.MANAGER, d.ADMIN, d.STAFF)
    roles = {
        d.STAFF: (d.RECIPIENT,),
        d.MANAGER: (d.STAFF, d.VOLUNTEER),
        d.ADMIN: (d.ADMIN, d.MANAGER, d.RECIPIENT),
    }[actor["role"]]
    with store.reader() as read_tx:
        return [_public_user(u) for u in read_tx.all("users") if u["role"] in roles]


def update_account(store, actor, user_id, display_name, *, current_password="", confirmed=False):
    require(actor, d.MANAGER, d.ADMIN)
    with store.transaction() as tx:
        user = tx.get("users", user_id)
        if not user or user["role"] not in d.MANAGEABLE_ROLES[actor["role"]]:
            raise PermissionDenied("Your role cannot change that account.")
        if user["role"] == d.ADMIN:
            _reauth_admin(tx, actor, current_password, confirmed)
        user["display_name"] = _clean(display_name, "a display name", max_length=100)
        _audit(tx, actor, "Account renamed", user["username"], d.SECURITY)
        return _public_user(user)


def deactivate_account(store, actor, user_id, confirmed, verification_note="", *, current_password=""):
    """FR-04 to FR-07: confirmation always required; Recipients need a verified request.
    Every open session of that person ends straight away."""
    require(actor, d.MANAGER, d.ADMIN, d.STAFF)
    if not confirmed:
        raise DomainError("Please confirm that you want to deactivate this account.")
    with store.transaction() as tx:
        user = tx.get("users", user_id)
        if not user:
            raise DomainError("Account not found.")
        if user["role"] == d.RECIPIENT:
            if actor["role"] not in (d.STAFF, d.ADMIN):
                raise PermissionDenied("Only Staff or IT Admins can deactivate Recipient accounts.")
            note = _clean(verification_note, "how the request was verified")
            user["deactivation_verification"] = {"verified": True, "by": actor["id"], "at": _now()}
            from .allocations import _close
            for allocation in tx.find("allocations", recipient_id=user["id"], status=d.ALLOCATED):
                _close(tx, actor, allocation, d.CANCELLED, "Recipient account deactivated")
                _audit(tx, actor, "Allocation cancelled", f"Allocation {allocation['id']}")
            tx.delete("notifications", user_id=user["id"])
        elif user["role"] not in d.MANAGEABLE_ROLES.get(actor["role"], ()):
            raise PermissionDenied("Your role cannot deactivate that account.")
        if user["role"] == d.ADMIN:
            _reauth_admin(tx, actor, current_password, confirmed)
            if user["active"] and tx.count("users", role=d.ADMIN, active=True) <= 1:
                raise DomainError("The last active IT Admin cannot be deactivated.")
        user["active"] = False
        _end_all_sessions(tx, user["id"])
        _audit(tx, actor, "Account deactivated", user["username"], d.SECURITY)
        return _public_user(user)


# ---------------------------------------------------------------- IT Admin (local only)

def bootstrap_admin(store, username, password, display_name):
    """FR-38: make the first IT Admin from the computer running the app. Refused once
    any active IT Admin exists, so it cannot be used to sneak in a second one."""
    with store.transaction() as tx:
        if tx.find("users", role=d.ADMIN, active=True):
            raise DomainError("An IT Admin already exists. Use reset-admin to recover it.")
        user = _create_user(tx, username, password, display_name, d.ADMIN)
        _audit(tx, None, "IT Admin created on this computer", user["username"], d.SECURITY)
        return _public_user(user)


def recover_admin(store, username, new_password):
    """FR-40: set a new password for an IT Admin from the computer running the app.
    Clears the sign-in pause and ends every session that account had open."""
    _check_new_password(new_password)
    with store.transaction() as tx:
        user = tx.find_one("users", username=(username or "").strip().lower())
        if not user or user["role"] != d.ADMIN or not user["active"]:
            raise DomainError("No active IT Admin has that username.")
        user["password_hash"] = hash_password(new_password)
        user["failed_logins"] = 0
        user["locked_until"] = None
        user["active"] = True
        _end_all_sessions(tx, user["id"])
        _audit(tx, None, "IT Admin password reset on this computer", user["username"],
               d.SECURITY)
        return _public_user(user)
