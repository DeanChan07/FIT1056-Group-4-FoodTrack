"""Food coming in and on the shelves: receiving donations, inventory and alerts."""

from datetime import date, timedelta

import streamlit as st

from foodshare import domain as d
from foodshare import services as s
from foodshare.domain import DomainError, EditConflict
from foodshare.views import common as c

BATCH_COLUMNS = {"name": "Item", "category": "Category", "quantity": "On shelf",
                 "reserved": "Set aside", "available": "Available",
                 "expiry_date": "Use by", "expiry_status": "Status", "hold_text": "Hold",
                 "allergens_text": "Allergens", "tags_text": "Dietary tags"}


def _with_text(rows):
    for b in rows:
        b["allergens_text"] = c.listing(b.get("allergens"))
        b["tags_text"] = c.listing(b.get("dietary_tags"))
    return rows


# ---------------------------------------------------------------- receive donations

def receive():
    user = c.me()
    store = c.store()
    c.header("Receive a donation", "Record what was accepted. Accepted food goes straight into "
             "the inventory.", "move_to_inbox")
    scheduled = [dn for dn in s.list_donations(store, user) if dn["status"] == d.SCHEDULED]
    if scheduled:
        with st.expander(f"Donations expected ({len(scheduled)})", expanded=True):
            c.table([{"Reference": dn["reference"], "From": dn["donor_name"] or "Not given",
                      "Drop-off": f"{c.nice_date(dn['dropoff_date'])} {dn['dropoff_time']}",
                      "Items": ", ".join(f"{i['offered_qty']} × {i['item_type']}"
                                         for i in dn["items"])} for dn in scheduled])
    choices = [dn["reference"] for dn in scheduled]
    ref = st.selectbox("Donation reference", choices, index=None, accept_new_options=True,
                       placeholder="Pick or type a reference, e.g. DN-DEMO01", key="recv_ref")
    if not ref:
        return
    donation = s.find_donation(store, ref)
    if not donation:
        st.error("No donation has that reference.", icon=":material/error:")
        return
    if donation["status"] == d.COLLECTED:
        st.success(donation["receipt"], icon=":material/check_circle:")
        c.table(donation["items"], {"item_type": "Item", "offered_qty": "Offered",
                                    "accepted_qty": "Accepted", "rejected_qty": "Rejected"})
        return
    key = f"recv{donation['id']}_"
    with st.form(f"receive_form_{donation['id']}"):
        st.markdown(f"**{donation['reference']}** from "
                    f"{c.esc(donation['donor_name']) or 'a donor'}")
        accepted = []
        for n, item in enumerate(donation["items"]):
            with st.container(border=True):
                st.markdown(f"**{c.esc(item['item_type'])}** · {item['offered_qty']} offered")
                a, b, x = st.columns(3)
                qty = a.number_input("Accepted", 0, item["offered_qty"], item["offered_qty"],
                                     key=f"{key}{n}_qty")
                expiry = b.date_input("Use by", value=date.today() + timedelta(days=30),
                                      format="DD/MM/YYYY", key=f"{key}{n}_expiry")
                category = x.text_input("Category", "General", key=f"{key}{n}_category")
                y, z = st.columns(2)
                allergens = y.text_input("Allergens (comma separated)", key=f"{key}{n}_allergens")
                tags = z.text_input("Dietary tags, e.g. halal, vegetarian", key=f"{key}{n}_tags")
                accepted.append({"accepted_qty": qty, "expiry_date": c.iso(expiry),
                                 "category": category, "allergens": allergens,
                                 "dietary_tags": tags})
        if st.form_submit_button("Record donation", type="primary", icon=":material/check:"):
            try:
                result = s.receive_donation(store, user, donation["reference"], accepted)
            except DomainError as e:
                st.error(str(e), icon=":material/error:")
            else:
                c.done(result["receipt"], key)


# ---------------------------------------------------------------- inventory

def inventory():
    user = c.me()
    store = c.store()
    c.header("Inventory", "Everything on the shelves, soonest use-by date first.",
             "inventory_2")
    a, b = st.columns([2, 1])
    search = a.text_input("Search by item or category", key="inv_search",
                          placeholder="e.g. rice, canned")
    status = b.segmented_control("Status", ["All", "Near expiry", "Expired", "On hold"],
                                 default="All", key="inv_status")
    rows = _with_text(s.list_batches(store, user, search))
    if status in ("Near expiry", "Expired"):
        rows = [r for r in rows if r["expiry_status"] == status]
    elif status == "On hold":
        rows = [r for r in rows if r["on_hold"]]
    x, y, z = st.columns(3)
    x.metric("Batches", len(rows))
    y.metric("Units available", s.usable_units(rows),
             help="On shelf, minus food set aside, leaving out expired or held food. "
                  "The dashboard uses the same figure.")
    z.metric("Near expiry or expired", sum(r["expiry_status"] != "OK" for r in rows))
    c.table(rows, BATCH_COLUMNS)
    if user["role"] != d.STAFF:
        st.caption("Only Organisation Staff can add or change stock.")
        return
    add_tab, edit_tab, fix_tab = st.tabs([":material/add: Add stock",
                                          ":material/edit: Edit a batch",
                                          ":material/exposure: Correct stock"])
    everything = s.list_batches(store, user)

    def pick(key):
        return st.selectbox("Batch", [r["id"] for r in everything], key=key,
                            format_func=lambda i: next(
                                f"{r['name']} · {r['quantity']} on shelf · use by "
                                f"{c.nice_date(r['expiry_date'])}"
                                for r in everything if r["id"] == i))
    with add_tab:
        batch_form(None)
    with edit_tab:
        if everything:
            batch_form(pick("inv_edit"))
    with fix_tab:
        if everything:
            correction_form(pick("inv_fix"))


def batch_form(batch_id):
    user = c.me()
    batch = s.get_batch(c.store(), user, batch_id) if batch_id else {}
    key = f"batch{batch_id or 'new'}_"
    loaded = c.snapshot(f"batch{batch_id}", batch.get("version")) if batch_id else None
    with st.form(f"batch_form_{batch_id or 'new'}"):
        a, b = st.columns(2)
        name = a.text_input("Item name (required)", batch.get("name", ""), key=key + "name")
        category = b.text_input("Category", batch.get("category", "General"),
                                key=key + "category")
        x, y = st.columns(2)
        quantity = x.number_input("Quantity on shelf (required)", min_value=0, step=1,
                                  value=batch.get("quantity", 0), key=key + "quantity",
                                  disabled=bool(batch_id),
                                  help="To change the amount of a batch, use Correct stock, "
                                       "so there is a reason and a history." if batch_id
                                  else None)
        expiry = y.date_input("Use by (required)",
                              value=c.as_date(batch.get("expiry_date"),
                                              date.today() + timedelta(days=30)),
                              format="DD/MM/YYYY", key=key + "expiry")
        allergens = st.text_input("Allergens (comma separated)",
                                  ", ".join(batch.get("allergens", [])), key=key + "allergens")
        tags = st.text_input("Dietary tags (comma separated)",
                             ", ".join(batch.get("dietary_tags", [])), key=key + "tags")
        on_hold = st.checkbox("On hold: do not give this out (for example a recall or a "
                              "damaged seal)", value=bool(batch.get("on_hold")),
                              key=key + "hold")
        hold_reason = st.text_input("Why it is on hold", batch.get("hold_reason") or "",
                                    key=key + "hold_reason")
        if batch_id and batch["reserved"]:
            st.caption(f"{batch['reserved']} are set aside for Recipients. While on hold, "
                       "they stay set aside but cannot be handed out.")
        label = "Save changes" if batch_id else "Add to inventory"
        if st.form_submit_button(label, type="primary", icon=":material/save:"):
            fields = {"name": name, "category": category, "quantity": quantity,
                      "expiry_date": c.iso(expiry), "allergens": allergens,
                      "dietary_tags": tags, "on_hold": on_hold, "hold_reason": hold_reason}
            if batch_id:
                fields["loaded_version"] = loaded
            try:
                s.save_batch(c.store(), user, fields, batch_id)
            except EditConflict as e:
                c.forget(key, f"snap_batch{batch_id}")
                c.flash(str(e), "error")
                st.rerun()
            except DomainError as e:
                st.error(str(e), icon=":material/error:")
            else:
                c.done("Stock saved.", key, f"snap_batch{batch_id}")


def correction_form(batch_id):
    """FR-41 and FR-42: signed corrections with a reason, and reversals."""
    user = c.me()
    batch = s.get_batch(c.store(), user, batch_id)
    key = f"fix{batch_id}_"
    loaded = c.snapshot(f"fix{batch_id}", batch["quantity"])
    a, b, x = st.columns(3)
    a.metric("On shelf", batch["quantity"])
    b.metric("Set aside", batch["reserved"])
    x.metric("Lowest it can go", batch["reserved"])
    with st.form(f"fix_form_{batch_id}"):
        y, z = st.columns([1, 2])
        change = y.number_input("Change (+ found, − damaged or miscounted)", step=1, value=0,
                                key=key + "change")
        reason = z.text_input("Reason (required)", key=key + "reason",
                              placeholder="e.g. 2 tins dented and thrown away")
        if st.form_submit_button("Save correction", type="primary", icon=":material/save:"):
            try:
                s.adjust_stock(c.store(), user, batch_id, change, reason, loaded)
            except EditConflict as e:
                c.forget(key, f"snap_fix{batch_id}")
                c.flash(str(e), "error")
                st.rerun()
            except DomainError as e:
                st.error(str(e), icon=":material/error:")
            else:
                c.done("Correction saved.", key, f"snap_fix{batch_id}", f"snap_batch{batch_id}")
    history = s.stock_history(c.store(), user, batch_id)
    st.markdown("**History**")
    c.table([{"When": c.nice_when(h["made_at"]), "Change": f"{h['change']:+d}",
              "Reason": h["reason"], "By": h["made_by_name"],
              "Note": (f"Reverses #{h['reverses_id']}" if h["reverses_id"]
                       else "Reversed" if h["reversed"] else ""), "No.": h["id"]}
             for h in history])
    reversible = [h for h in history if not h["reverses_id"] and not h["reversed"]]
    if reversible:
        with st.expander("Undo a correction", icon=":material/undo:"):
            with st.form(f"reverse_form_{batch_id}", border=False):
                which = st.selectbox("Correction", [h["id"] for h in reversible],
                                     key=key + "rev_which",
                                     format_func=lambda i: next(
                                         f"No. {h['id']}: {h['change']:+d} ({h['reason']})"
                                         for h in reversible if h["id"] == i))
                why = st.text_input("Reason for undoing it", key=key + "rev_reason")
                if st.form_submit_button("Undo correction", icon=":material/undo:"):
                    try:
                        s.reverse_adjustment(c.store(), user, which, why)
                    except DomainError as e:
                        st.error(str(e), icon=":material/error:")
                    else:
                        c.done("Correction undone. Both entries stay in the history.", key,
                               f"snap_fix{batch_id}", f"snap_batch{batch_id}")


# ---------------------------------------------------------------- alerts

def alerts():
    user = c.me()
    store = c.store()
    c.header("Stock alerts", "Food to use soon, and items running low.", "notifications_active")
    info = s.stock_alerts(store, user)
    a, b = st.columns(2)
    a.metric("Near expiry or expired", len(info["near_expiry"]))
    b.metric(f"Low stock (at or below {info['threshold']})", len(info["low_stock"]))
    st.subheader("Use soon")
    c.table(_with_text(info["near_expiry"]),
            {"name": "Item", "quantity": "On shelf", "expiry_date": "Use by",
             "expiry_status": "Status"})
    st.subheader("Running low")
    c.table(info["low_stock"], {"name": "Item", "quantity": "Units left"})
    with st.form("threshold_form"):
        threshold = st.number_input("Warn me when an item is at or below", min_value=0,
                                    value=info["threshold"], step=1, key="alert_threshold")
        if st.form_submit_button("Save threshold", icon=":material/save:"):
            try:
                s.set_low_stock_threshold(store, user, threshold)
            except DomainError as e:
                st.error(str(e), icon=":material/error:")
            else:
                c.done("Low-stock threshold saved.", "alert_threshold")
