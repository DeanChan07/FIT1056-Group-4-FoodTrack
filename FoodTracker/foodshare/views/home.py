"""Home pages for each role, and the notices page."""

import streamlit as st

from foodshare import domain as d
from foodshare import services as s
from foodshare.views import common as c
from foodshare.views import people


def recipient_home():
    user = c.me()
    store = c.store()
    c.hero(f"Hi {user['display_name']}",
           "Here is your next pickup and anything waiting for you.", "👋")
    upcoming = [a for a in s.list_allocations(store, user) if a["status"] == d.ALLOCATED]
    if upcoming:
        nxt = min(upcoming, key=lambda a: (a["pickup_date"], a["pickup_time"]))
        c.live_queue_card(nxt["id"], "Your next pickup")
        st.markdown("Food set aside for you: "
                    + ", ".join(f"{i['quantity']} × {c.esc(i['name'])}" for i in nxt["items"]))
    else:
        st.info("Nothing is set aside for you right now.", icon=":material/info:")
    a, b, x = st.columns(3)
    a.metric("Pickups booked", len(upcoming), border=True)
    b.metric("Swap requests waiting", len(s.list_swaps(store, user, d.PENDING)), border=True)
    x.metric("Unread notices", s.unread_count(store, user), border=True)
    with st.container(horizontal=True):
        c.link("my_food", "See my food", ":material/shopping_bag:")
        c.link("my_needs", "Update my needs", ":material/person:")
        c.link("notices", "Read notices", ":material/notifications:")


def volunteer_home():
    user = c.me()
    c.hero(f"Hi {user['display_name']}", "Thank you for volunteering. Here are your shifts.", "🙌")
    people.task_cards(s.list_tasks(c.store(), user))
    with st.container(horizontal=True):
        c.link("receive", "Receive a donation", ":material/move_to_inbox:")
        c.link("allocations", "Record a collection", ":material/inventory:")


def team_home():
    """Dashboard for Staff and Managers."""
    user = c.me()
    store = c.store()
    c.hero(f"Hi {user['display_name']}", f"{d.ROLE_LABELS[user['role']]} dashboard.", "📊")
    stats = s.dashboard_stats(store, user)
    tiles = [
        ("Units available", stats["units"], "inventory_2"),
        ("Near expiry", stats["near_expiry"], "schedule"),
        ("Low stock items", stats["low_stock"], "trending_down"),
        ("Donations expected", stats["scheduled_donations"], "move_to_inbox"),
        ("Pickups today", stats["queue_today"], "today"),
        ("Pickups booked", stats["upcoming_pickups"], "event"),
        ("Swap requests", stats["pending_swaps"], "swap_horiz"),
        ("New feedback", stats["new_feedback"], "sentiment_satisfied"),
    ]
    for row in (tiles[:4], tiles[4:]):
        for col, (label, value, icon) in zip(st.columns(4), row):
            col.metric(label, value, border=True, icon=f":material/{icon}:")
    left, right = st.columns(2, gap="medium")
    with left.container(border=True):
        st.markdown("**Use soon**")
        near = stats["alerts"]["near_expiry"]
        c.table(near[:6], {"name": "Item", "quantity": "On shelf", "expiry_date": "Use by",
                           "expiry_status": "Status"})
        c.link("alerts", "All alerts", ":material/arrow_forward:")
    with right.container(border=True):
        if user["role"] == d.STAFF:
            st.markdown("**Next pickups**")
            q = s.pickup_queue(store, user)
            st.caption(c.nice_date(q["date"]))
            c.table(q["queue"][:6], {"position": "Place", "recipient_name": "Recipient",
                                     "window_start": "From", "window_end": "Until"})
            c.link("queue", "Full queue", ":material/arrow_forward:")
        else:
            st.markdown("**Volunteer shifts**")
            c.table(s.list_tasks(store, user)[:6],
                    {"shift_date": "Date", "shift_time": "Time", "volunteer_name": "Volunteer",
                     "task_type": "Task"})
            c.link("tasks", "All tasks", ":material/arrow_forward:")


def admin_home():
    user = c.me()
    c.hero(f"Hi {user['display_name']}", "IT Admin. Manage Manager accounts and read the "
           "sign-in and account history here.", "🛠️")
    rows = s.list_accounts(c.store(), user)
    a, b, x = st.columns(3)
    a.metric("Managers", sum(u["role"] == d.MANAGER for u in rows), border=True)
    b.metric("Recipients", sum(u["role"] == d.RECIPIENT for u in rows), border=True)
    x.metric("Inactive accounts", sum(not u["active"] for u in rows), border=True)
    with st.container(horizontal=True):
        c.link("accounts", "Manage accounts", ":material/manage_accounts:")
        c.link("audit", "Audit log", ":material/history:")


def notices():
    user = c.me()
    store = c.store()
    c.header("Notices", "Messages from the food bank, newest first.", "notifications")
    rows = s.list_notifications(store, user)
    if not rows:
        st.info("No notices yet.", icon=":material/info:")
        return
    for n in rows:
        with st.container(border=True):
            st.markdown(f"**{n['kind']}** {c.badge('New') if not n['read'] else ''}")
            st.markdown(c.esc(n["message"]))
            st.caption(c.nice_when(n["created_at"]))
    unread = {n["id"] for n in rows if not n["read"]}
    if unread:  # only the notices shown here; one arriving now stays unread
        s.mark_notifications_read(store, user, unread)
