"""Shared helpers for every Streamlit page: the data store, who is signed in,
messages that survive a refresh, and small display pieces."""

import html
import json
import re
import sqlite3
from datetime import date, datetime, time

import streamlit as st

from foodshare import data_path
from foodshare import domain as d
from foodshare import services as s
from foodshare.storage import SqliteStore

STATUS_COLOURS = {
    d.SCHEDULED: "blue", d.COLLECTED: "green", d.ALLOCATED: "orange",
    d.PENDING: "orange", d.APPROVED: "green", d.DECLINED: "red", d.WITHDRAWN: "gray",
    d.CANCELLED: "gray", d.NO_SHOW: "red", d.EXPIRED: "gray", d.CLOSED: "gray",
    d.WAITING: "blue", d.SERVING: "violet", "Not here yet": "gray", "On hold": "red",
    "Expired": "red", "Near expiry": "orange", "OK": "green",
    "Receiving": "blue", "Distribution": "violet",
    "Standard": "gray", "Soon": "orange", "Urgent": "red",
    "New": "blue", "Reviewed": "gray", "Archived": "gray",
}
COOKIE = "foodshare_session"


@st.cache_resource(show_spinner=False)
def _open_store(path):
    # Opened once; every save is its own SQLite transaction.
    return SqliteStore(path)


def store():
    return _open_store(data_path())


# ---------------------------------------------------------------- who is signed in

def me(*, touch=True):
    """The signed-in person, checked against their session each time, or None.

    The session token lives in this browser tab's state and in a cookie, so a
    refresh keeps the person signed in. It ends after 15 idle minutes (NFR-09)."""
    token = st.session_state.get("session_token")
    if token is None and not st.session_state.get("_cookie_checked"):
        st.session_state["_cookie_checked"] = True  # only once per browser session
        token = st.context.cookies.get(COOKIE)
    if not isinstance(token, str) or not token:
        return None
    user, reason = s.resume_session(store(), token, touch=touch)
    if not user:
        st.session_state.pop("session_token", None)
        st.session_state.pop("user_id", None)
        st.session_state["_cookie"] = ""  # forget the ended session in the browser too
        if reason:
            flash(reason, "info")
        return None
    st.session_state["session_token"] = token
    st.session_state["user_id"] = user["id"]
    return user


def sign_in(user):
    st.session_state.clear()
    token = s.start_session(store(), user)
    st.session_state["session_token"] = token
    st.session_state["user_id"] = user["id"]
    st.session_state["_cookie"] = token


def sign_out():
    s.end_session(store(), st.session_state.get("session_token"))
    st.session_state.clear()
    st.session_state["_cookie_checked"] = True  # do not sign back in from the old cookie
    st.session_state["_cookie"] = ""
    flash("You have signed out.", "info")


def write_cookie():
    """Send a pending sign-in (or sign-out) to the browser as a cookie. Runs once
    per change, through a CSRF-protected server route. HttpOnly and SameSite=Strict;
    Secure when served over HTTPS."""
    if "_cookie" not in st.session_state:
        return
    token = st.session_state.pop("_cookie")
    import os
    if os.environ.get("FOODSHARE_COOKIE_ENDPOINT") != "1":
        return  # AppTest/direct streamlit launch keeps a server-side tab session only.
    from foodshare.http_security import cookie_handoff
    handle = cookie_handoff(token)
    st.html("""<script>
    (async () => {
        const response = await fetch('/foodshare/csrf', {credentials: 'same-origin', cache: 'no-store'});
        const data = await response.json();
        await fetch('/foodshare/session', {method: 'POST', credentials: 'same-origin',
            headers: {'X-Foodshare-CSRF': data.token, 'Content-Type': 'text/plain'},
            body: """ + json.dumps(handle) + """});
    })();
    </script>""", unsafe_allow_javascript=True, width=1)


# ---------------------------------------------------------------- messages

def flash(message, kind="success"):
    """Show a message after the next refresh (st.rerun)."""
    st.session_state.setdefault("_flash", []).append((kind, message))


def show_flash():
    for kind, message in st.session_state.pop("_flash", []):
        if kind == "error":
            st.error(message, icon=":material/error:")
        elif kind == "info":
            st.info(message, icon=":material/info:")
        else:
            st.success(message, icon=":material/check_circle:")


def done(message, *forget_prefixes):
    """After a successful save: clear the form, show the message, refresh the page."""
    forget(*forget_prefixes)
    flash(message)
    st.rerun()


# ---------------------------------------------------------------- forms

def snapshot(name, value):
    """What a form showed when it was opened. Saving compares it with the data file,
    so one person cannot quietly undo another person's change."""
    key = f"snap_{name}"
    if key not in st.session_state:
        st.session_state[key] = value
    return st.session_state[key]


def forget(*prefixes):
    """Drop form values and snapshots so the next refresh shows the saved data."""
    for key in [k for k in st.session_state if prefixes and str(k).startswith(prefixes)]:
        del st.session_state[key]


def forget_snapshots_when_page_changes(page):
    if st.session_state.get("_page") != page.title:
        forget("snap_")
        st.session_state["_page"] = page.title


def iso(value):
    return value.isoformat() if isinstance(value, date) else (value or "")


def hhmm(value):
    return value.strftime("%H:%M") if isinstance(value, time) else (value or "")


def as_date(text, fallback=None):
    try:
        return d.parse_date(text)
    except d.DomainError:
        return fallback


def as_time(text, fallback=None):
    try:
        minutes = d.parse_time(text)
    except d.DomainError:
        return fallback
    return time(minutes // 60, minutes % 60)


# ---------------------------------------------------------------- display

def header(title, caption=None, icon=None):
    st.header(f":material/{icon}: {title}" if icon else title, divider="green")
    if caption:
        st.caption(caption)
    show_flash()


def hero(title, text, emoji="🥫"):
    st.markdown(
        f"""<div style="background:linear-gradient(135deg,#0f766e,#14b8a6);color:#fff;
        padding:1.6rem 1.8rem;border-radius:1rem;margin-bottom:1rem">
        <div style="font-size:2.3rem;line-height:1">{emoji}</div>
        <div style="font-size:1.9rem;font-weight:700;margin-top:.5rem">{html.escape(title)}</div>
        <div style="opacity:.92;margin-top:.35rem;font-size:1.05rem">{html.escape(text)}</div>
        </div>""",
        unsafe_allow_html=True)
    show_flash()


def badge(label):
    """Status as a coloured label that also says it in words (NFR-08)."""
    return f":{STATUS_COLOURS.get(label, 'gray')}-badge[{label}]"


def nice_date(text):
    try:
        return d.parse_date(text).strftime("%a %d %b %Y")
    except d.DomainError:
        return text or ""


def nice_when(text):
    """2026-10-07T14:03:00 -> 07 Oct 2026, 14:03"""
    try:
        return datetime.fromisoformat(text).strftime("%d %b %Y, %H:%M")
    except (TypeError, ValueError):
        return text or ""


_MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!|<>~$:])")


def esc(text):
    """Show text that people typed exactly as typed. Without this, a name like
    '[click](http://...)' or ':red[...]' would turn into a link or coloured text."""
    return _MARKDOWN_SPECIAL.sub(r"\\\1", str(text or ""))


def listing(values):
    return ", ".join(values) if values else "None"


def table(rows, columns=None, **kwargs):
    """A tidy read-only table. columns maps data keys to headings, in order."""
    if columns:
        rows = [{heading: row.get(key) for key, heading in columns.items()} for row in rows]
    if not rows:
        st.caption("Nothing to show yet.")
        return
    st.dataframe(rows, hide_index=True, width="stretch", **kwargs)


def needs_text(summary):
    if not summary:
        return "No needs profile yet."
    parts = [f"Household of {summary['household_size']}"]
    if not summary.get("allergies_confirmed"):
        parts.append("allergy information not confirmed")
    if summary["allergies"]:
        parts.append("allergies: " + ", ".join(summary["allergies"]))
    if summary["dietary"]:
        parts.append("needs: " + ", ".join(summary["dietary"]))
    return " · ".join(parts)


def link(page_key, label=None, icon=None):
    from foodshare.views import nav
    page = nav.page(page_key)
    st.page_link(page, label=label or page.title, icon=icon or page.icon)


def go(page_key):
    from foodshare.views import nav
    st.switch_page(nav.page(page_key))


def queue_card(q, title="Your place in the pickup queue"):
    with st.container(border=True):
        st.markdown(f"**{title}** {badge(q['state'])}")
        st.caption(f"Pickup {nice_date(q['date'])} at {q['booked_time']}")
        if q["paused"]:
            st.warning("Queue paused. Your place is kept; no estimate is available.")
        elif q["state"] == d.SERVING:
            st.info("You are being served.")
        elif not q["checked_in"]:
            st.info("Check in when you arrive to receive an approximate waiting time.")
        else:
            a, b, col = st.columns(3)
            a.metric("Your place", f"#{q['position']} of {q['total']}")
            b.metric("People ahead of you", q["ahead"])
            col.metric("Approximate wait", f"{q['wait_min']}-{q['wait_max']} minutes")
        st.caption(f"Last updated {nice_when(q['updated_at'])}. Refreshes every 20 seconds.")


@st.fragment(run_every="20s")
def live_queue_card(allocation_id, title="Your place in the pickup queue"):
    """The queue card, refreshed every 20 seconds without reloading the page (FR-54).
    The refresh does not count as activity, so the 15-minute sign-out still applies."""
    user = me(touch=False)
    if not user:
        st.info("Your session has ended. Please sign in again.")
        return
    try:
        q = s.queue_status(store(), user, allocation_id)
    except (d.DomainError, sqlite3.Error, OSError):
        st.caption("Estimate unavailable. We could not update your queue place just now.")
        last = st.session_state.get(f"_queue_last_{allocation_id}")
        if last:
            st.caption(f"Last confirmed update: {nice_when(last)}")
        return
    if not q:
        return
    st.session_state[f"_queue_last_{allocation_id}"] = q["updated_at"]
    queue_card(q, title)
    if q["can_check_in"]:
        if st.button("I'm here: check in", key=f"checkin_{allocation_id}", type="primary",
                     icon=":material/how_to_reg:"):
            try:
                user = me()  # a button press is activity; the timer refresh is not
                if not user:
                    return
                s.check_in(store(), user, allocation_id)
            except d.DomainError as e:
                st.error(str(e), icon=":material/error:")
            else:
                flash("You are checked in. Please wait nearby; your place updates by itself.")
                st.rerun()
    elif not q["checked_in"]:
        st.caption(f"On your pickup day you can check in here from "
                   f"{d.CHECK_IN_EARLY_MINUTES} minutes before your time.")
