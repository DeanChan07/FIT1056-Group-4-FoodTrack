"""Which pages each role sees, in menu order (FR-03: nobody sees another role's pages)."""

import streamlit as st

from foodshare import domain as d
from foodshare import services as s
from foodshare.views import food, home, insights, people, public, stock

# key: (page function, menu title, icon)
PAGES = {
    "welcome": (public.welcome, "Welcome", "home"),
    "sign_in": (public.sign_in, "Sign in", "login"),
    "register": (public.register, "Create an account", "person_add"),
    "donate": (public.donate, "Donate food", "volunteer_activism"),
    "donation_status": (public.donation_status, "Check a donation", "search"),
    "feedback": (public.feedback, "Feedback", "sentiment_satisfied"),
    "recipient_home": (home.recipient_home, "Home", "home"),
    "my_food": (food.my_food, "My food", "shopping_bag"),
    "my_swaps": (food.my_swaps, "My swaps", "swap_horiz"),
    "my_needs": (people.my_needs, "My needs", "person"),
    "volunteer_home": (home.volunteer_home, "Home", "home"),
    "team_home": (home.team_home, "Dashboard", "dashboard"),
    "admin_home": (home.admin_home, "Dashboard", "dashboard"),
    "receive": (stock.receive, "Receive", "move_to_inbox"),
    "inventory": (stock.inventory, "Inventory", "inventory_2"),
    "alerts": (stock.alerts, "Alerts", "notifications_active"),
    "recipients": (people.recipients, "Recipients", "groups"),
    "allocations": (food.allocations, "Allocations", "inventory"),
    "queue": (food.queue, "Queue", "schedule"),
    "swaps": (food.swaps_review, "Swaps", "swap_horiz"),
    "tasks": (people.tasks, "Tasks", "assignment"),
    "reports": (insights.reports, "Reports", "bar_chart"),
    "feedback_inbox": (insights.feedback_inbox, "Feedback", "sentiment_satisfied"),
    "accounts": (people.accounts, "Accounts", "manage_accounts"),
    "notices": (home.notices, "Notices", "notifications"),
    "audit": (insights.audit_log, "Audit log", "history"),
}

MENUS = {
    None: ["welcome", "sign_in", "register", "donate", "donation_status", "feedback"],
    d.RECIPIENT: ["recipient_home", "my_food", "my_swaps", "my_needs", "notices", "feedback"],
    d.VOLUNTEER: ["volunteer_home", "tasks", "receive", "allocations", "queue", "notices"],
    d.STAFF: ["team_home", "receive", "inventory", "recipients", "allocations", "queue",
              "swaps", "tasks", "alerts", "reports", "feedback_inbox", "accounts", "audit", "notices"],
    d.MANAGER: ["team_home", "accounts", "tasks", "inventory", "alerts", "reports",
                "feedback_inbox", "audit", "notices"],
    d.ADMIN: ["admin_home", "accounts", "audit", "notices"],
}

# Public anonymous feedback remains available while any role is signed in.
for _role in d.INTERNAL_ROLES:
    MENUS[_role].append("feedback")

TITLES = {  # the same page can have a friendlier name for a role
    (d.VOLUNTEER, "tasks"): "My tasks",
    (d.VOLUNTEER, "allocations"): "Collections",
    (d.MANAGER, "accounts"): "Team",
}


def page(key, title=None, default=False):
    func, menu_title, icon = PAGES[key]
    return st.Page(func, title=title or menu_title, icon=f":material/{icon}:",
                   url_path=key, default=default)


def pages_for(user):
    role = user["role"] if user else None
    counts = {}
    if user:
        counts["notices"] = s.unread_count(c_store(), user)
    if role in (d.STAFF, d.MANAGER):
        with c_store().reader() as tx:
            counts["swaps"] = tx.count("swaps", status=d.PENDING)
            counts["feedback_inbox"] = tx.count("feedback", reviewed=False, archived=False)
    pages = []
    for n, key in enumerate(MENUS[role]):
        title = TITLES.get((role, key), PAGES[key][1])
        if counts.get(key):
            title = f"{title} ({counts[key]})"
        pages.append(page(key, title, default=(n == 0)))
    if role is None:
        # Refreshing the browser starts a new, signed-out session. Asking to sign in on
        # the same address brings the person straight back to the page they were on.
        for key in PAGES.keys() - set(MENUS[None]):
            pages.append(st.Page(public.sign_in_first, title=PAGES[key][1], url_path=key,
                                 visibility="hidden"))
    return pages


def c_store():
    from foodshare.views.common import store
    return store()
