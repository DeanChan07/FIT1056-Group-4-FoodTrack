"""Reports and the anonymous feedback inbox."""

from datetime import date, timedelta

import streamlit as st

from foodshare import domain as d
from foodshare import services as s
from foodshare.domain import DomainError
from foodshare.views import common as c


def reports():
    user = c.me()
    s.require(user, d.STAFF, d.MANAGER)
    c.header("Reports", "Donations received and food given out between two dates.",
             "bar_chart")
    a, b = st.columns(2)
    start = a.date_input("From", value=date.today() - timedelta(days=30), format="DD/MM/YYYY",
                         key="rep_start")
    end = b.date_input("To", value=date.today(), format="DD/MM/YYYY", key="rep_end")
    try:
        report = s.build_report(c.store(), user, c.iso(start), c.iso(end))
    except DomainError as e:
        st.error(str(e), icon=":material/error:")
        return
    x, y, z = st.columns(3)
    x.metric("Units donated", report["total_donated"], border=True)
    y.metric("Units given out", report["total_distributed"], border=True)
    z.metric("Records", len(report["rows"]), border=True)
    c.table(report["rows"], {"date": "Date", "type": "Type", "reference": "Reference",
                             "item": "Item", "quantity": "Quantity"})
    st.download_button("Download CSV", s.report_csv(report),
                       file_name=f"foodshare_report_{report['start']}_{report['end']}.csv",
                       mime="text/csv", icon=":material/download:")
    st.subheader("Current stock")
    st.caption("Units still in date. Expired units are counted separately in the CSV, so "
               "nothing is counted twice.")
    if report["stock"]:
        st.bar_chart(report["stock"], x="item", y="quantity", horizontal=True,
                     x_label="", y_label="Units", color="#0f766e")


def feedback_inbox():
    user = c.me()
    store = c.store()
    c.header("Feedback", "Anonymous feedback. Nothing here says who wrote it.",
             "sentiment_satisfied")
    fb = s.feedback_inbox(store, user)
    a, b, x = st.columns(3)
    a.metric("Total", fb["total"], border=True)
    b.metric("New", fb["new"], border=True)
    x.metric("Average rating", f"{fb['average']} / 5" if fb["average"] else "None yet",
             border=True)
    left, right = st.columns(2, gap="medium")
    with left.container(border=True):
        st.markdown("**Ratings**")
        st.bar_chart([{"Rating": f"{r} {label}", "People": fb["by_rating"][r]}
                      for r, (emoji, label) in d.FEEDBACK_RATINGS.items()],
                     x="Rating", y="People", sort=False, color="#14b8a6", x_label="")
    with right.container(border=True):
        st.markdown("**Topics**")
        st.bar_chart([{"Topic": k, "People": v} for k, v in fb["by_category"].items()],
                     x="Topic", y="People", horizontal=True, sort=False, color="#0f766e",
                     y_label="")
    a, b = st.columns(2)
    show_all = a.toggle("Show feedback already reviewed", key="fb_all")
    show_archived = b.toggle(f"Show archived ({fb['archived']})", key="fb_archived")
    rows = [f for f in fb["rows"] if (show_all or not f["reviewed"])
            and (show_archived or not f["archived"])]
    if not rows:
        st.success("You have read everything.", icon=":material/check_circle:")
    for f in rows:
        with st.container(border=True):
            face = d.FEEDBACK_RATINGS[f["rating"]] if f["rating"] else ("", "No rating")
            st.markdown(f"{face[0]} **{face[1]}** · {f['category']} · "
                        f"{c.nice_date(f['submitted_on'])} "
                        f"{c.badge('Archived' if f['archived'] else 'Reviewed' if f['reviewed'] else 'New')}")
            st.markdown(c.esc(f["message"]) or "_No message._")
            with st.container(horizontal=True):
                if not f["reviewed"] and st.button("Mark as reviewed", key=f"fb_done_{f['id']}",
                                                   icon=":material/done:"):
                    _review(store, user, f["id"], False)
                if not f["archived"] and st.button("Archive", key=f"fb_arch_{f['id']}",
                                                   icon=":material/archive:"):
                    _review(store, user, f["id"], True)


def _review(store, user, feedback_id, archive):
    try:
        s.mark_feedback_reviewed(store, user, feedback_id, archive=archive)
    except DomainError as e:
        st.error(str(e), icon=":material/error:")
    else:
        c.done("Archived." if archive else "Marked as reviewed.")


def audit_log():
    """FR-56 and FR-57: read-only history. Admins see sign-in and account events,
    Managers see stock and food events. Private details are never written here."""
    user = c.me()
    s.require(user, d.ADMIN, d.MANAGER)
    what = "sign-in and account" if user["role"] == d.ADMIN else "stock, food and queue"
    c.header("Audit log", f"Every {what} change, newest first. Nobody can edit or delete "
             "these entries.", "history")
    rows = s.audit_events(c.store(), user)
    actions = sorted({r["action"] for r in rows})
    chosen = st.multiselect("Only show", actions, key="audit_filter",
                            placeholder="All kinds of change")
    if chosen:
        rows = [r for r in rows if r["action"] in chosen]
    c.table([{"When": c.nice_when(r["at"]), "Who": r["actor_name"],
              "What": r["action"], "On": r["target"], "Details": r["details_text"]}
             for r in rows])
