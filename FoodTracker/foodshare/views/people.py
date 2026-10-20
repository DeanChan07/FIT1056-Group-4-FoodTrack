"""People: needs profiles, Recipients, accounts and volunteer tasks."""

from datetime import date, time, timedelta

import streamlit as st

from foodshare import domain as d
from foodshare import services as s
from foodshare.domain import DomainError, EditConflict
from foodshare.views import common as c
from foodshare.views import food


# ---------------------------------------------------------------- needs profile

def my_needs():
    user = c.me()
    c.header("My needs", "Only staff preparing your food see a short summary of this. "
             "Volunteers never do.", "person")
    profile_form(user["id"], staff_mode=False)


def profile_form(recipient_id, staff_mode):
    user = c.me()
    profile = s.get_profile(c.store(), user, recipient_id) or {}
    version = c.snapshot(f"profile{recipient_id}", profile.get("version", 0))
    key = f"prof{recipient_id}_"
    with st.form(f"profile_form_{recipient_id}"):
        fields = {}
        for field, label, required, why in d.PROFILE_FIELDS:
            value = profile.get(field)
            if isinstance(value, list):
                value = ", ".join(value)
            label = f"{label} ({'required' if required else 'optional'})"
            if field == "household_size":
                fields[field] = st.number_input(label, min_value=1, step=1,
                                                value=int(value) if value else None,
                                                key=key + field)
            elif field == "urgency":
                fields[field] = st.segmented_control(label, d.URGENCY_LEVELS,
                                                     default=value or "Standard",
                                                     key=key + field)
            else:
                fields[field] = st.text_input(label, value or "", key=key + field)
            st.caption(why)
        consent = False
        if staff_mode:
            consent = st.checkbox("The Recipient gave permission for me to make this change.",
                                  key=key + "consent")
        if st.form_submit_button("Save needs", type="primary", icon=":material/save:"):
            fields["loaded_version"] = version
            try:
                s.save_profile(c.store(), user, recipient_id, fields, consent=consent)
            except EditConflict as e:
                c.forget(key, f"snap_profile{recipient_id}")
                c.flash(str(e), "error")
                st.rerun()
            except DomainError as e:
                st.error(str(e), icon=":material/error:")
            else:
                c.done("Needs saved.", key, f"snap_profile{recipient_id}")
    if profile.get("updated_at"):
        st.caption(f"Last updated {c.nice_when(profile['updated_at'])}.")


# ---------------------------------------------------------------- staff: recipients

def recipients():
    user = c.me()
    c.header("Recipients", "In name order, never ranked. Choose someone to set food aside or "
             "update their needs with their permission.", "groups")
    rows = s.recipients_for_allocation(c.store(), user)
    c.table([{"Name": r["display_name"], "Needs": c.needs_text(r["summary"]),
              "Urgency": (r["summary"] or {}).get("urgency", "Not given")} for r in rows])
    if not rows:
        return
    chosen = st.selectbox("Recipient", [r["id"] for r in rows], key="rec_open",
                          format_func=lambda i: next(r["display_name"] for r in rows
                                                     if r["id"] == i))
    recipient = next(r for r in rows if r["id"] == chosen)
    allocate_tab, needs_tab = st.tabs([":material/shopping_bag: Set food aside",
                                       ":material/person: Needs profile"])
    with allocate_tab:
        food.allocate_form(recipient)
    with needs_tab:
        profile_form(chosen, staff_mode=True)


# ---------------------------------------------------------------- accounts

def accounts():
    user = c.me()
    s.require(user, d.STAFF, d.MANAGER, d.ADMIN)
    store = c.store()
    titles = {d.STAFF: "Recipient accounts", d.MANAGER: "Team", d.ADMIN: "Accounts"}
    c.header(titles[user["role"]], {
        d.STAFF: "Deactivate a Recipient account when they ask, after checking it is them.",
        d.MANAGER: "Create and manage Staff and Volunteer accounts.",
        d.ADMIN: "Create and manage Manager accounts, and deactivate Recipient accounts.",
    }[user["role"]], "manage_accounts")
    rows = s.list_accounts(store, user)
    c.table([{"Name": u["display_name"], "Username": u["username"],
              "Role": d.ROLE_LABELS[u["role"]], "Active": "Yes" if u["active"] else "No"}
             for u in rows])
    creatable = d.MANAGEABLE_ROLES.get(user["role"], ())
    tabs = []
    if creatable:
        tabs += ["create", "rename"]
    tabs.append("deactivate")
    labels = {"create": ":material/person_add: Create account",
              "rename": ":material/edit: Change a name",
              "deactivate": ":material/person_off: Deactivate"}
    for name, tab in zip(tabs, st.tabs([labels[t] for t in tabs])):
        with tab:
            if name == "create":
                _create_account(creatable)
            elif name == "rename":
                _rename_account([u for u in rows if u["role"] in creatable])
            else:
                _deactivate_account([u for u in rows if u["active"]])


def _create_account(creatable):
    with st.form("create_account"):
        a, b = st.columns(2)
        name = a.text_input("Display name", key="acct_new_name")
        role = b.selectbox("Role", creatable, format_func=d.ROLE_LABELS.get,
                           key="acct_new_role")
        x, y = st.columns(2)
        username = x.text_input("Username", key="acct_new_username")
        password = y.text_input("Temporary password", type="password",
                                key="acct_new_password",
                                help=f"{d.PASSWORD_MIN_LENGTH} to {d.PASSWORD_MAX_LENGTH} "
                                     "characters.")
        if st.form_submit_button("Create account", type="primary", icon=":material/person_add:"):
            try:
                s.create_internal_account(c.store(), c.me(), username, password, name, role)
            except DomainError as e:
                st.error(str(e), icon=":material/error:")
            else:
                c.done("Account created.", "acct_new_")


def _rename_account(people):
    if not people:
        st.caption("No accounts you can change yet.")
        return
    with st.form("rename_account"):
        who = st.selectbox("Account", [u["id"] for u in people], key="acct_ren_who",
                           format_func=lambda i: next(f"{u['display_name']} ({u['username']})"
                                                      for u in people if u["id"] == i))
        name = st.text_input("New display name", key="acct_ren_name")
        if st.form_submit_button("Save name", icon=":material/save:"):
            try:
                s.update_account(c.store(), c.me(), who, name)
            except DomainError as e:
                st.error(str(e), icon=":material/error:")
            else:
                c.done("Account updated.", "acct_ren_")


def _deactivate_account(people):
    if not people:
        st.caption("No active accounts.")
        return
    with st.form("deactivate_account"):
        who = st.selectbox("Account", [u["id"] for u in people], key="acct_off_who",
                           format_func=lambda i: next(
                               f"{u['display_name']} ({u['username']}, "
                               f"{d.ROLE_LABELS[u['role']]})" for u in people if u["id"] == i))
        note = st.text_input("How was the request checked? (needed for Recipients)",
                             key="acct_off_note",
                             placeholder="e.g. In person with photo ID, 7 Oct")
        sure = st.checkbox("Yes, deactivate this account", key="acct_off_sure")
        if st.form_submit_button("Deactivate", icon=":material/person_off:"):
            try:
                s.deactivate_account(c.store(), c.me(), who, sure, note)
            except DomainError as e:
                st.error(str(e), icon=":material/error:")
            else:
                c.done("Account deactivated.", "acct_off_")


# ---------------------------------------------------------------- volunteer tasks

def task_cards(rows):
    if not rows:
        st.info("No tasks yet.", icon=":material/info:")
        return
    for t in rows:
        with st.container(border=True):
            st.markdown(f"**{c.nice_date(t['shift_date'])} at {t['shift_time']}** "
                        f"{c.badge(t['task_type'])}")
            st.markdown(c.esc(t["instructions"]) or "No extra instructions.")


def tasks():
    user = c.me()
    store = c.store()
    if user["role"] == d.VOLUNTEER:
        c.header("My tasks", "Your shifts. Only you can see these.", "assignment")
        task_cards(s.list_tasks(store, user))
        return
    c.header("Volunteer tasks", "Assign receiving or distribution shifts.", "assignment")
    volunteers = s.list_volunteers(store, user)
    with st.expander("Assign a task", expanded=True, icon=":material/add_task:"):
        if not volunteers:
            st.caption("There are no active Volunteers yet.")
        else:
            with st.form("assign_task"):
                a, b = st.columns(2)
                who = a.selectbox("Volunteer", [v["id"] for v in volunteers], key="task_who",
                                  format_func=lambda i: next(v["display_name"] for v in volunteers
                                                             if v["id"] == i))
                kind = b.segmented_control("Task", d.TASK_TYPES, default=d.TASK_TYPES[0],
                                           key="task_kind")
                x, y = st.columns(2)
                day = x.date_input("Shift date", value=date.today() + timedelta(days=1),
                                   format="DD/MM/YYYY", key="task_day")
                at = y.time_input("Shift time", value=time(9, 0), step=900, key="task_time")
                notes = st.text_area("Instructions", key="task_notes")
                if st.form_submit_button("Assign task", type="primary",
                                         icon=":material/add_task:"):
                    try:
                        s.assign_task(store, user, who, kind, c.iso(day), c.hhmm(at), notes)
                    except DomainError as e:
                        st.error(str(e), icon=":material/error:")
                    else:
                        c.done("Task assigned.", "task_")
    c.table(s.list_tasks(store, user),
            {"shift_date": "Date", "shift_time": "Time", "volunteer_name": "Volunteer",
             "task_type": "Task", "instructions": "Instructions"})
