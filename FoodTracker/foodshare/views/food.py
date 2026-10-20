"""Food going out: allocations, collection, private swaps and the pickup queue."""

from datetime import date, time, timedelta

import streamlit as st

from foodshare import domain as d
from foodshare import services as s
from foodshare.domain import DomainError, EditConflict
from foodshare.views import common as c


# ---------------------------------------------------------------- Recipient: my food

def my_food():
    user = c.me()
    c.header("My food", "What has been set aside for you, and when to collect it.", "shopping_bag")
    rows = s.list_allocations(c.store(), user)
    if not rows:
        st.info("Nothing has been set aside for you yet. Staff will let you know.",
                icon=":material/info:")
        return
    upcoming = [a for a in rows if a["status"] == d.ALLOCATED]
    past = [a for a in rows if a["status"] != d.ALLOCATED]
    for a in sorted(upcoming, key=lambda a: (a["pickup_date"], a["pickup_time"])):
        recipient_allocation_card(a["id"])
    if past:
        st.subheader("Collected before")
        c.table(past, {"id": "No.", "pickup_date": "Pickup date", "status": "Status"})
    if "swap_target" in st.session_state:
        swap_dialog(*st.session_state["swap_target"])


def recipient_allocation_card(allocation_id):
    user = c.me()
    a = s.get_allocation(c.store(), user, allocation_id)
    with st.container(border=True):
        st.markdown(f"#### Pickup on {c.nice_date(a['pickup_date'])} at {a['pickup_time']} "
                    f"{c.badge(a['status'])}")
        if a["status"] == d.ALLOCATED:
            c.live_queue_card(allocation_id)
        elif a["status"] in (d.CANCELLED, d.NO_SHOW):
            st.info(f"This pickup was {a['status'].lower()}: {c.esc(a['close_reason'])}",
                    icon=":material/info:")
        st.markdown("**Your items**")
        latest = {}
        for sw in sorted(a["swaps"], key=lambda x: x["id"]):
            latest[sw["item_id"]] = sw
        for item in a["items"]:
            left, right = st.columns([3, 2], vertical_alignment="center")
            left.markdown(f"**{item['quantity']} × {c.esc(item['name'])}**")
            sw = latest.get(item["item_id"])
            if sw and sw["status"] == d.PENDING:
                right.markdown(f"Swap requested {c.badge(d.PENDING)}")
            elif a["status"] == d.ALLOCATED:
                if right.button("Request a private swap", key=f"swapbtn_{a['id']}_{item['item_id']}",
                                icon=":material/swap_horiz:"):
                    st.session_state["swap_target"] = (a["id"], item["item_id"], item["name"])
            if sw and sw["status"] != d.PENDING:
                left.caption(f"Swap {sw['status'].lower()}: {c.esc(sw['response'])}")
        if a["distribution"]:
            st.success(f"Collected on {c.nice_date(a['distribution']['collected_date'])}.",
                       icon=":material/check_circle:")


def _close_swap_dialog():
    c.forget("swap_")


@st.dialog("Request a private swap", on_dismiss=_close_swap_dialog)
def swap_dialog(allocation_id, item_id, item_name):
    st.markdown(f"Ask to swap **{c.esc(item_name)}** for something else. Only staff preparing "
                "food see your request. A reason is optional.")
    chip = st.pills("Quick reason", d.SWAP_REASON_CHIPS, key="swap_chip")
    note = st.text_area("Or say it in your own words", key="swap_note")
    send, cancel = st.columns(2)
    if cancel.button("Cancel", icon=":material/close:", width="stretch"):
        c.forget("swap_")
        st.rerun()
    if send.button("Send request", type="primary", icon=":material/send:", width="stretch"):
        reason = "; ".join(x for x in (chip, (note or "").strip()) if x)
        try:
            s.request_swap(c.store(), c.me(), allocation_id, item_id, reason)
        except DomainError as e:
            st.error(str(e), icon=":material/error:")
        else:
            c.done("Your request was sent privately to staff. Status: Pending.", "swap_")


def my_swaps():
    user = c.me()
    c.header("My swaps", "Your private swap requests and what staff decided.", "swap_horiz")
    rows = s.list_swaps(c.store(), user)
    if not rows:
        st.info("You have not asked for any swaps. You can ask from My food.",
                icon=":material/info:")
        return
    for sw in rows:
        with st.container(border=True):
            st.markdown(f"**{c.esc(sw['item_name'])}** {c.badge(sw['status'])}")
            st.caption(f"Asked on {c.nice_when(sw['created_at'])}"
                       + (f" · Your reason: {c.esc(sw['reason'])}" if sw["reason"] else ""))
            steps = ["Sent", "Being reviewed", "Decided"]
            reached = 1 if sw["status"] == d.PENDING else 3
            st.progress(reached / 3, text=" → ".join(
                f"**{step}**" if n < reached else step for n, step in enumerate(steps)))
            if sw["response"]:
                st.markdown(c.esc(sw["response"]))
            if sw["status"] == d.PENDING and st.button(
                    "Withdraw request", key=f"withdraw_{sw['id']}", icon=":material/undo:"):
                try:
                    s.withdraw_swap(c.store(), user, sw["id"])
                except DomainError as e:
                    st.error(str(e), icon=":material/error:")
                else:
                    c.done("Your request was withdrawn. Your original item is still set aside.")


# ---------------------------------------------------------------- Staff and volunteers

def allocations():
    user = c.me()
    s.require(user, d.STAFF, d.VOLUNTEER)
    title = "Collections" if user["role"] == d.VOLUNTEER else "Allocations"
    c.header(title, "Choose an allocation to record its collection"
             + (" or change its pickup time." if user["role"] == d.STAFF else "."), "inventory")
    rows = s.list_allocations(c.store(), user)
    if user["role"] == d.VOLUNTEER:
        st.caption("You see today's pickups only on a day you have a Distribution shift.")
    show = st.segmented_control("Show", ["Waiting for pickup", "Collected",
                                         "Cancelled or missed", "All"],
                                default="Waiting for pickup", key="alloc_filter")
    if show == "Waiting for pickup":
        rows = [a for a in rows if a["status"] == d.ALLOCATED]
    elif show == "Collected":
        rows = [a for a in rows if a["status"] == d.COLLECTED]
    elif show == "Cancelled or missed":
        rows = [a for a in rows if a["status"] in (d.CANCELLED, d.NO_SHOW)]
    for a in rows:
        a["items_text"] = ", ".join(f"{i['quantity']} × {i['name']}" for i in a["items"])
    c.table(rows, {"id": "No.", "recipient_name": "Recipient", "pickup_date": "Pickup date",
                   "pickup_time": "Time", "status": "Status", "items_text": "Items"})
    if not rows:
        return
    chosen = st.selectbox(
        "Open allocation", [a["id"] for a in rows], key="alloc_open",
        format_func=lambda i: next(f"No. {a['id']} · {a['recipient_name']} · "
                                   f"{c.nice_date(a['pickup_date'])} {a['pickup_time']}"
                                   for a in rows if a["id"] == i))
    allocation_detail(chosen)


def allocation_detail(allocation_id):
    user = c.me()
    a = s.get_allocation(c.store(), user, allocation_id)
    with st.container(border=True):
        st.markdown(f"#### No. {a['id']} for {c.esc(a['recipient_name'])} "
                    f"{c.badge(a['status'])}")
        st.write(f"Pickup: {c.nice_date(a['pickup_date'])} at {a['pickup_time']}")
        c.table(a["items"], {"name": "Item", "quantity": "Quantity"})
        if user["role"] == d.STAFF:
            q = s.queue_status(c.store(), user, allocation_id)
            if q:
                st.caption(f"Queue: #{q['position']} of {q['total']}, expected "
                           f"{q['window_start']}–{q['window_end']}.")
        if a["distribution"]:
            dist = a["distribution"]
            st.success(f"Collected on {c.nice_date(dist['collected_date'])}: "
                       + ", ".join(f"{i['quantity']} × {c.esc(i['name'])}"
                                   for i in dist["items"]),
                       icon=":material/check_circle:")
            return
        if a["status"] in (d.CANCELLED, d.NO_SHOW):
            st.info(f"{a['status']} on {c.nice_when(a['closed_at'])}: "
                    f"{c.esc(a['close_reason'])}. The food went back on the shelf.",
                    icon=":material/info:")
    if a["status"] != d.ALLOCATED:
        return
    left, right = st.columns(2, gap="medium")
    with left:
        collection_form(a)
    if user["role"] == d.STAFF:
        with right:
            pickup_form(a)
            cancel_form(a)


def collection_form(a):
    shown = c.snapshot(f"collect{a['id']}", {i["item_id"]: i["batch_id"] for i in a["items"]})
    with st.form(f"collect_form_{a['id']}", border=True):
        st.markdown("**Record collection**")
        qty = {}
        if c.me()["role"] == d.STAFF:
            when = st.date_input("Collected on", value=date.today(), max_value=date.today(),
                                 format="DD/MM/YYYY", key=f"col{a['id']}_date",
                                 help="Usually today. Pick an earlier day if you are entering "
                                      "a collection late.")
        else:
            when = date.today()
            st.caption(f"Collected today, {c.nice_date(c.iso(when))}.")
        for i in a["items"]:
            qty[i["item_id"]] = st.number_input(
                f"{i['name']} collected", min_value=0, max_value=i["quantity"],
                value=i["quantity"], step=1, key=f"col{a['id']}_{i['item_id']}_{i['batch_id']}")
        if st.form_submit_button("Confirm collection", type="primary",
                                 icon=":material/check:"):
            try:
                s.record_collection(c.store(), c.me(), a["id"], qty, c.iso(when),
                                    batch_ids=shown)
            except EditConflict as e:
                c.forget(f"col{a['id']}_", f"snap_collect{a['id']}")
                c.flash(str(e), "error")
                st.rerun()
            except DomainError as e:
                st.error(str(e), icon=":material/error:")
            else:
                c.done("Collection recorded and stock updated.",
                       f"col{a['id']}_", f"snap_collect{a['id']}")


def pickup_form(a):
    with st.form(f"pickup_form_{a['id']}", border=True):
        st.markdown("**Change pickup time**")
        new_date = st.date_input("Date", value=c.as_date(a["pickup_date"], date.today()),
                                 format="DD/MM/YYYY", key=f"pick{a['id']}_date")
        new_time = st.time_input("Time", value=c.as_time(a["pickup_time"], time(14, 0)),
                                 step=900, key=f"pick{a['id']}_time")
        st.caption("The Recipient gets a notice and their queue estimate updates straight away.")
        if st.form_submit_button("Save and notify", icon=":material/notifications:"):
            try:
                s.update_pickup(c.store(), c.me(), a["id"], c.iso(new_date), c.hhmm(new_time))
            except DomainError as e:
                st.error(str(e), icon=":material/error:")
            else:
                c.done("Pickup time changed. The Recipient has been sent a notice.",
                       f"pick{a['id']}_")


def cancel_form(a):
    with st.expander("Cancel this pickup", icon=":material/event_busy:"):
        with st.form(f"cancel_form_{a['id']}", border=False):
            reason = st.text_input("Reason the Recipient will see", key=f"cancel{a['id']}_reason",
                                   placeholder="e.g. They asked to cancel by phone")
            sure = st.checkbox("Yes, cancel it and put the food back on the shelf",
                               key=f"cancel{a['id']}_sure")
            if st.form_submit_button("Cancel pickup", icon=":material/event_busy:"):
                try:
                    s.cancel_allocation(c.store(), c.me(), a["id"], sure, reason)
                except DomainError as e:
                    st.error(str(e), icon=":material/error:")
                else:
                    c.done("Pickup cancelled. The food is back on the shelf and the Recipient "
                           "has been told.", f"cancel{a['id']}_")


# ---------------------------------------------------------------- Staff: allocate

def allocate_form(recipient):
    user = c.me()
    rid = recipient["id"]
    st.markdown(f"**Needs:** {c.needs_text(recipient['summary'])}")
    batches = s.suitable_batches(c.store(), user, rid)
    safe = [b for b in batches if not b["problems"]]
    unsafe = [b for b in batches if b["problems"]]
    if not safe:
        st.warning("No suitable stock is available for this Recipient right now.",
                   icon=":material/warning:")
    with st.form(f"allocate_form_{rid}", border=True):
        chosen = []
        for b in safe:
            left, right = st.columns([3, 1], vertical_alignment="center")
            left.markdown(f"**{c.esc(b['name'])}** · {c.esc(b['category'])} · "
                          f"{b['available']} available · "
                          f"use by {c.nice_date(b['expiry_date'])} {c.badge(b['expiry_status'])}")
            amount = right.number_input("Quantity", min_value=0, max_value=b["available"],
                                        value=0, step=1, key=f"alloc{rid}_{b['id']}",
                                        label_visibility="collapsed")
            chosen.append({"batch_id": b["id"], "quantity": amount})
        a, b = st.columns(2)
        pickup_date = a.date_input("Pickup date", value=date.today() + timedelta(days=1),
                                   min_value=date.today(), format="DD/MM/YYYY",
                                   key=f"alloc{rid}_date")
        pickup_time = b.time_input("Pickup time", value=time(14, 0), step=900,
                                   key=f"alloc{rid}_time")
        if st.form_submit_button("Save allocation", type="primary", icon=":material/check:",
                                 disabled=not safe):
            try:
                made = s.create_allocation(c.store(), user, rid, chosen, c.iso(pickup_date),
                                           c.hhmm(pickup_time))
            except DomainError as e:
                st.error(str(e), icon=":material/error:")
            else:
                c.done(f"Allocation No. {made['id']} saved for {c.esc(recipient['display_name'])}.",
                       f"alloc{rid}_")
    if unsafe:
        with st.expander(f"Not suitable for this Recipient ({len(unsafe)})"):
            c.table([{"Item": b["name"], "Why not": "; ".join(b["problems"])} for b in unsafe])


# ---------------------------------------------------------------- Staff: swaps

def swaps_review():
    user = c.me()
    s.require(user, d.STAFF)
    c.header("Swap requests", "Private requests from Recipients. Reasons are seen only by staff.",
             "swap_horiz")
    rows = s.list_swaps(c.store(), user)
    pending = [sw for sw in rows if sw["status"] == d.PENDING]
    st.metric("Waiting for a decision", len(pending))
    if pending:
        chosen = st.selectbox("Open request", [sw["id"] for sw in pending], key="swap_open",
                              format_func=lambda i: next(f"Request {sw['id']} · {sw['item_name']}"
                                                         for sw in pending if sw["id"] == i))
        swap_decision(chosen)
    else:
        st.success("No requests are waiting.", icon=":material/check_circle:")
    done_rows = [sw for sw in rows if sw["status"] != d.PENDING]
    if done_rows:
        st.subheader("Earlier requests")
        c.table(done_rows, {"id": "Request", "item_name": "Item", "status": "Status",
                            "response": "Response"})


def swap_decision(swap_id):
    user = c.me()
    sw = s.get_swap(c.store(), user, swap_id)
    with st.container(border=True):
        st.markdown(f"#### {c.esc(sw['recipient_name'])} would like to swap "
                    f"{sw['quantity']} × {c.esc(sw['item_name'])}")
        st.caption(f"Pickup {c.nice_date(sw['pickup_date'])} at {sw['pickup_time']}. The "
                   "request closes by itself if nobody decides before the pickup window ends.")
        st.markdown(f"**Reason:** {c.esc(sw['reason']) or 'No reason given (that is fine).'}")
        st.markdown(f"**Needs:** {c.esc(c.needs_text(sw['summary']))}")
        approve_tab, decline_tab = st.tabs([":material/check: Approve with a replacement",
                                            ":material/close: Decline"])
        with approve_tab:
            if not sw["options"]:
                st.warning("No safe replacement has enough stock right now.",
                           icon=":material/warning:")
            else:
                option = st.radio(
                    "Safe replacements", [b["id"] for b in sw["options"]], key=f"swap{swap_id}_pick",
                    format_func=lambda i: next(
                        f"{b['name']} · {b['available']} available · use by "
                        f"{c.nice_date(b['expiry_date'])}" for b in sw["options"] if b["id"] == i))
                if st.button("Approve swap", type="primary", key=f"swap{swap_id}_approve",
                             icon=":material/check:"):
                    try:
                        s.approve_swap(c.store(), user, swap_id, option)
                    except DomainError as e:
                        st.error(str(e), icon=":material/error:")
                    else:
                        c.done("Swap approved. The Recipient has been told.", f"swap{swap_id}_")
        with decline_tab:
            response = st.text_area("Kind response for the Recipient",
                                    key=f"swap{swap_id}_response",
                                    placeholder="Sorry, we have nothing suitable to swap today.")
            if st.button("Decline swap", key=f"swap{swap_id}_decline", icon=":material/close:"):
                try:
                    s.decline_swap(c.store(), user, swap_id, response)
                except DomainError as e:
                    st.error(str(e), icon=":material/error:")
                else:
                    c.done("Swap declined. The Recipient can see your response.",
                           f"swap{swap_id}_")


# ---------------------------------------------------------------- Staff: queue

def queue():
    user = c.me()
    c.header("Pickup queue", "Who is here and who is expected. Recipients only ever see their "
             "own place.", "schedule")
    store = c.store()
    first = s.pickup_queue(store, user)
    days = [day for day, _ in first["upcoming"]]
    if first["date"] not in days:
        days.insert(0, first["date"])
    counts = dict(first["upcoming"])
    day = st.selectbox("Day", days, key="queue_day",
                       format_func=lambda x: f"{c.nice_date(x)} ({counts.get(x, 0)} pickups)")
    queue_table(day)
    q = s.pickup_queue(store, user, day)
    with st.expander("Queue timing", icon=":material/tune:"):
        with st.form("queue_settings"):
            x, y = st.columns(2)
            step = x.number_input("Minutes per pickup", 1, 60, q["minutes_per_pickup"],
                                  key="queue_step")
            window = y.number_input("Window length (minutes)", 1, 120,
                                    q["queue_window_minutes"], key="queue_window")
            paused = st.toggle("Pause estimates (Recipients see 'held up for a moment')",
                               value=q["paused"], key="queue_paused")
            if st.form_submit_button("Save timing", icon=":material/save:"):
                try:
                    s.set_queue_settings(store, user, step, window, paused)
                except DomainError as e:
                    st.error(str(e), icon=":material/error:")
                else:
                    c.done("Queue timing saved. Every Recipient's estimate has been updated.",
                           "queue_step", "queue_window", "queue_paused")


@st.fragment(run_every="20s")
def queue_table(day):
    """The day's queue, refreshed every 20 seconds, with the desk actions."""
    user = c.me()
    store = c.store()
    q = s.pickup_queue(store, user, day)
    a, b, x = st.columns(3)
    a.metric("People booked", len(q["queue"]))
    b.metric("Checked in", sum(1 for r in q["queue"] if r["checked_in_at"]))
    x.metric("Minutes per pickup", q["minutes_per_pickup"])
    if q["paused"]:
        st.warning("Estimates are paused. Recipients are told the desk is held up.",
                   icon=":material/pause_circle:")
    c.table(q["queue"], {"position": "Place", "recipient_name": "Recipient", "state": "Status",
                         "booked_time": "Booked", "window_start": "Expected from",
                         "window_end": "Until", "delay": "Minutes late", "item_count": "Items"})
    st.caption(f"Updated {c.nice_when(d.now().isoformat())}. Refreshes every "
               "20 seconds.")
    if not q["queue"]:
        return
    with st.container(border=True):
        st.markdown("**At the desk**")
        rows = q["queue"]
        chosen = st.selectbox("Recipient", [r["allocation_id"] for r in rows], key="queue_who",
                              format_func=lambda i: next(f"#{r['position']} {r['recipient_name']}"
                                                         f" · {r['state']}"
                                                         for r in rows
                                                         if r["allocation_id"] == i))
        row = next(r for r in rows if r["allocation_id"] == chosen)
        actions = []
        if row["state"] == "Not here yet":
            actions.append(("check_in", "Check in", ":material/how_to_reg:"))
        if row["state"] == d.WAITING:
            actions.append(("serve", "Start serving", ":material/play_arrow:"))
        if row["state"] == d.SERVING:
            actions.append(("wait", "Back to waiting", ":material/undo:"))
        actions.append(("no_show", "Did not come", ":material/person_off:"))
        with st.container(horizontal=True):
            for action, label, icon in actions:
                if st.button(label, key=f"queue_{action}", icon=icon):
                    try:
                        if action == "check_in":
                            s.check_in(store, user, chosen)
                        else:
                            s.move_in_queue(store, user, chosen, action)
                    except DomainError as e:
                        st.error(str(e), icon=":material/error:")
                    else:
                        c.flash(f"{row['recipient_name']}: {label.lower()} done.")
                        st.rerun()
        st.caption("Record what they took on Allocations. 'Did not come' puts their food back "
                   "on the shelf and sends them a notice.")
