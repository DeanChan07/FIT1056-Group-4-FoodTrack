"""F-01 accounts and roles: registration, signing in, sessions, team accounts,
and the local IT Admin bootstrap and recovery (FR-01 to FR-07, FR-38 to FR-40)."""

import hashlib
import secrets
from datetime import datetime, timedelta

from .. import domain as d
from ..domain import DomainError, PermissionDenied
from ..passwords import check_password, hash_password
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
    _clean(display_name, "a display name")
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
    with store.transaction() as tx:
        user = _create_user(tx, username, password, display_name, d.RECIPIENT)
        _audit(tx, user, "Recipient registered", user["username"], d.SECURITY)
        return _public_user(user)


def login(store, username, password):
    """FR-02 and NFR-09. After five wrong passwords in a row the account pauses for one
    minute, then two, four ... up to fifteen. A pause, not a permanent lock, so someone
    typing a Staff username cannot keep the real person out for long."""
    name = (username or "").strip().lower()
    problem = None
    with store.transaction() as tx:
        user = tx.find_one("users", username=name)
        if not user:
            check_password(_DUMMY_HASH, password or "")
            raise DomainError("Username or password is incorrect.")
        locked = user.get("locked_until")
        if locked and datetime.fromisoformat(locked) > d.now():
            wait = max(1, round((datetime.fromisoformat(locked) - d.now()).total_seconds() / 60))
            raise DomainError(f"Too many wrong passwords. Please wait about {wait} minute"
                              f"{'s' if wait != 1 else ''} and try again.")
        if not check_password(user["password_hash"], password or ""):
            user["failed_logins"] = (user.get("failed_logins") or 0) + 1
            extra = user["failed_logins"] - d.FREE_LOGIN_ATTEMPTS
            if extra >= 0:
                minutes = min(d.LOCK_MAX_MINUTES, d.LOCK_FIRST_MINUTES * 2 ** extra)
                user["locked_until"] = (d.now() + timedelta(minutes=minutes)).isoformat()
            _audit(tx, None, "Sign-in failed", user["username"], d.SECURITY,
                   failed_in_a_row=user["failed_logins"])
            problem = "Username or password is incorrect."
        elif not user["active"]:
            problem = "This account is inactive. Please contact the food bank."
        else:
            user["failed_logins"] = 0
            user["locked_until"] = None
            _audit(tx, user, "Signed in", user["username"], d.SECURITY)
            return _public_user(user)
    raise DomainError(problem)  # raised after saving, so the failed attempt is counted


def get_user(store, user_id):
    user = store.reader().get("users", user_id)
    return _public_user(user) if user else None


# ---------------------------------------------------------------- sessions (NFR-09)

def _token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(store, user):
    """Make a sign-in that survives a page refresh. Only a hash of the token is stored."""
    token = secrets.token_urlsafe(32)
    with store.transaction() as tx:
        tx.insert("sessions", {"token_hash": _token_hash(token), "user_id": user["id"],
                               "created_at": _now(), "last_seen": _now()})
    return token


def resume_session(store, token):
    """Return (user, None) while the session is valid, or (None, reason) when it ended.
    Sessions end after 15 minutes without activity or 8 hours in total."""
    if not token:
        return None, None
    tx = store.reader()
    session = tx.find_one("sessions", token_hash=_token_hash(token))
    if not session:
        return None, None
    user = tx.get("users", session["user_id"])
    now = d.now()
    reason = None
    if not user or not user["active"]:
        reason = "Your account is no longer active."
    elif now - datetime.fromisoformat(session["last_seen"]) > timedelta(
            minutes=d.SESSION_IDLE_MINUTES):
        reason = (f"You were signed out after {d.SESSION_IDLE_MINUTES} minutes without "
                  "activity. Please sign in again.")
    elif now - datetime.fromisoformat(session["created_at"]) > timedelta(
            hours=d.SESSION_MAX_HOURS):
        reason = f"You were signed out after {d.SESSION_MAX_HOURS} hours. Please sign in again."
    if reason:
        end_session(store, token)
        return None, reason
    if now - datetime.fromisoformat(session["last_seen"]) > timedelta(seconds=30):
        with store.transaction() as wtx:  # not on every click, to keep saves rare
            live = wtx.find_one("sessions", token_hash=_token_hash(token))
            if live:
                live["last_seen"] = _now()
    return _public_user(user), None


def end_session(store, token):
    if not token:
        return
    with store.transaction() as tx:
        tx.conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))


def _end_all_sessions(tx, user_id):
    tx.conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


# ---------------------------------------------------------------- team accounts

def create_internal_account(store, actor, username, password, display_name, role):
    """FR-04 and FR-05."""
    require(actor, d.MANAGER, d.ADMIN)
    if role not in d.MANAGEABLE_ROLES.get(actor["role"], ()):
        raise PermissionDenied("Your role cannot create that type of account.")
    with store.transaction() as tx:
        user = _create_user(tx, username, password, display_name, role, actor["id"])
        _audit(tx, actor, "Account created", user["username"], d.SECURITY,
               role=d.ROLE_LABELS[role])
        return _public_user(user)


def list_accounts(store, actor):
    require(actor, d.MANAGER, d.ADMIN, d.STAFF)
    roles = {
        d.STAFF: (d.RECIPIENT,),
        d.MANAGER: (d.STAFF, d.VOLUNTEER),
        d.ADMIN: (d.MANAGER, d.RECIPIENT),
    }[actor["role"]]
    return [_public_user(u) for u in store.reader().all("users") if u["role"] in roles]


def update_account(store, actor, user_id, display_name):
    require(actor, d.MANAGER, d.ADMIN)
    with store.transaction() as tx:
        user = tx.get("users", user_id)
        if not user or user["role"] not in d.MANAGEABLE_ROLES[actor["role"]]:
            raise PermissionDenied("Your role cannot change that account.")
        user["display_name"] = _clean(display_name, "a display name")
        _audit(tx, actor, "Account renamed", user["username"], d.SECURITY)
        return _public_user(user)


def deactivate_account(store, actor, user_id, confirmed, verification_note=""):
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
            user["deactivation_verification"] = {"note": note, "by": actor["id"], "at": _now()}
        elif user["role"] not in d.MANAGEABLE_ROLES.get(actor["role"], ()):
            raise PermissionDenied("Your role cannot deactivate that account.")
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
        if not user or user["role"] != d.ADMIN:
            raise DomainError("No IT Admin has that username.")
        user["password_hash"] = hash_password(new_password)
        user["failed_logins"] = 0
        user["locked_until"] = None
        user["active"] = True
        _end_all_sessions(tx, user["id"])
        _audit(tx, None, "IT Admin password reset on this computer", user["username"],
               d.SECURITY)
        return _public_user(user)
