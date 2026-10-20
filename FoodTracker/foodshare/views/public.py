"""Pages anyone can use without signing in: welcome, sign in, register,
donate food, check a donation and the anonymous feedback box."""

from datetime import date, time, timedelta

import streamlit as st

from foodshare import domain as d
from foodshare import services as s
from foodshare.domain import DomainError
from foodshare.views import common as c

DEMO_PASSWORD = "DemoPassword123!"  # the same as seed.py, shown only on this demo build
DEMO_ACCOUNTS = [
    {"Username": "staff", "Who": "Sam, Organisation Staff"},
    {"Username": "volunteer", "Who": "Vic, Volunteer"},
    {"Username": "recipient", "Who": "Rina, Recipient"},
    {"Username": "recipient2", "Who": "Ravi, Recipient"},
    {"Username": "recipient3", "Who": "Tom, Recipient (pickup later today)"},
    {"Username": "manager", "Who": "Mia, Organisation Manager"},
    {"Username": "admin", "Who": "Ivy, IT Admin"},
]


def welcome():
    c.hero("FoodShare Tracker",
           "Our community food bank. Donate food, check on a donation, or sign in to "
           "see your food and pickup time.")
    cards = [
        ("volunteer_activism", "Donate food",
         "No account needed. Tell us what you are bringing and when, and get a reference.",
         "donate"),
        ("search", "Check a donation",
         "Type your reference to see whether your donation has been received.",
         "donation_status"),
        ("sentiment_satisfied", "Share feedback",
         "Anonymous. We never store your name, account or the time you wrote.", "feedback"),
    ]
    for col, (icon, title, text, key) in zip(st.columns(3), cards):
        with col.container(border=True, height="stretch"):
            st.markdown(f"#### :material/{icon}: {title}")
            st.write(text)
            c.link(key, f"Go to {title.lower()}", ":material/arrow_forward:")
    with st.container(border=True):
        left, right = st.columns([3, 1], vertical_alignment="center")
        left.markdown("**Staff, volunteers and recipients:** sign in to see your own pages.")
        with right:
            c.link("sign_in", "Sign in", ":material/login:")


def sign_in():
    c.header("Sign in", "For staff, volunteers and recipients.", "login")
    form_col, help_col = st.columns([3, 2], gap="large")
    with form_col, st.form("sign_in_form"):
        username = st.text_input("Username", autocomplete="username")
        password = st.text_input("Password", type="password", autocomplete="current-password")
        if st.form_submit_button("Sign in", type="primary", icon=":material/login:",
                                 width="stretch"):
            try:
                user = s.login(c.store(), username, password)
            except DomainError as e:
                st.error(str(e), icon=":material/error:")
            else:
                c.sign_in(user)
                c.flash(f"Welcome, {user['display_name']}.")
                st.rerun()
    with help_col:
        with st.container(border=True):
            st.markdown("**New here?**")
            st.write("Recipients can make their own account.")
            c.link("register", "Create a Recipient account", ":material/person_add:")
        with st.expander("Demo accounts"):
            st.dataframe(DEMO_ACCOUNTS, hide_index=True, width="stretch")
            st.caption(f"Every demo password is `{DEMO_PASSWORD}`.")


def sign_in_first():
    st.info("Please sign in to open this page. You will come straight back here.",
            icon=":material/lock:")
    sign_in()


def register():
    c.header("Create a Recipient account",
             "Staff, volunteer and manager accounts are made by the food bank team.",
             "person_add")
    with st.form("register_form"):
        name = st.text_input("Your name", help="How staff will greet you.")
        username = st.text_input("Username", autocomplete="username")
        password = st.text_input("Password", type="password", autocomplete="new-password",
                                 help=f"{d.PASSWORD_MIN_LENGTH} to {d.PASSWORD_MAX_LENGTH} "
                                      "characters. A short sentence is easiest to remember.")
        if st.form_submit_button("Create account", type="primary", icon=":material/check:"):
            try:
                user = s.register_recipient(c.store(), username, password, name)
            except DomainError as e:
                st.error(str(e), icon=":material/error:")
            else:
                c.sign_in(user)
                c.flash("Your account is ready. Add your needs under My needs whenever you like.")
                st.rerun()


def donate():
    c.header("Donate food", "No account needed. You will get a reference to check on it later.",
             "volunteer_activism")
    if "donation_ref" in st.session_state:
        donation = s.find_donation(c.store(), st.session_state["donation_ref"])
        st.balloons()
        with st.container(border=True):
            st.success("Thank you! Your drop-off is booked.", icon=":material/favorite:")
            st.markdown(f"Your reference is **`{donation['reference']}`**. Keep it to check "
                        "whether your donation has been received.")
            st.write(f"Drop-off: {c.nice_date(donation['dropoff_date'])} at "
                     f"{donation['dropoff_time']}")
            c.table(donation["items"], {"item_type": "Item", "offered_qty": "Quantity"})
        if st.button("Book another donation", icon=":material/add:"):
            st.session_state.pop("donation_ref")
            st.rerun()
        return

    st.markdown("**What are you bringing?**")
    items = st.data_editor(
        [{"Item": "", "Quantity": 1}], num_rows="dynamic", width="stretch", key="donate_items",
        column_config={
            "Item": st.column_config.TextColumn("Item", help="For example: rice, canned beans"),
            "Quantity": st.column_config.NumberColumn("Quantity", min_value=1, step=1),
        })
    with st.form("donate_form"):
        a, b = st.columns(2)
        dropoff_date = a.date_input("Drop-off date", value=date.today() + timedelta(days=1),
                                    min_value=date.today(), format="DD/MM/YYYY")
        dropoff_time = b.time_input("Drop-off time", value=time(10, 0), step=900)
        donor_name = st.text_input("Your name or organisation (optional)")
        if st.form_submit_button("Book drop-off", type="primary", icon=":material/check:"):
            rows = [{"item_type": (r.get("Item") or "").strip(), "quantity": r.get("Quantity")}
                    for r in items]
            try:
                donation = s.schedule_donation(c.store(), rows, c.iso(dropoff_date),
                                               c.hhmm(dropoff_time), donor_name)
            except DomainError as e:
                st.error(str(e), icon=":material/error:")
            else:
                c.forget("donate_")
                st.session_state["donation_ref"] = donation["reference"]
                st.rerun()


def donation_status():
    c.header("Check a donation", "Type the reference you were given, for example DN-DEMO01.",
             "search")
    with st.form("status_form"):
        ref = st.text_input("Donation reference", placeholder="DN-XXXXXX")
        st.form_submit_button("Check", type="primary", icon=":material/search:")
    if not ref:
        return
    donation = s.find_donation(c.store(), ref)
    if not donation:
        st.error("We could not find a donation with that reference. Please check it and "
                 "try again.", icon=":material/error:")
        return
    with st.container(border=True):
        st.markdown(f"### {donation['reference']} {c.badge(donation['status'])}")
        if donation["status"] == d.COLLECTED:
            st.success(donation.get("receipt") or "Received. Thank you!",
                       icon=":material/check_circle:")
            c.table(donation["items"], {"item_type": "Item", "offered_qty": "Offered",
                                        "accepted_qty": "Accepted"})
        else:
            st.info(f"Booked for {c.nice_date(donation['dropoff_date'])} at "
                    f"{donation['dropoff_time']}. It has not been received yet.",
                    icon=":material/schedule:")
            c.table(donation["items"], {"item_type": "Item", "offered_qty": "Quantity"})


def feedback():
    c.header("Anonymous feedback",
             "Tell us how we are doing. We only keep your rating, topic, message and the "
             "date. No name, account, address or time of day.", "sentiment_satisfied")
    if st.session_state.get("feedback_sent"):
        st.balloons()
        st.success("Thank you. Your feedback has been passed on anonymously.",
                   icon=":material/favorite:")
        if st.button("Write more feedback", icon=":material/edit:"):
            st.session_state.pop("feedback_sent")
            st.rerun()
        return
    sent = st.session_state.get("_feedback_count", 0)
    if sent >= d.FEEDBACK_PER_SESSION:  # kept in this browser tab's memory only, never saved
        st.info("Thank you for all your feedback today. You can send more another time.",
                icon=":material/favorite:")
        return
    with st.container(border=True):
        st.markdown("**How was your experience?**")
        face = st.feedback("faces", key="feedback_face")
        if face is not None:
            emoji, label = d.FEEDBACK_RATINGS[face + 1]
            st.caption(f"You chose: {label}")
        topic = st.pills("Topic", d.FEEDBACK_CATEGORIES, default="General",
                         key="feedback_topic")
        message = st.text_area("Anything you'd like to tell us? (optional)",
                               max_chars=d.FEEDBACK_MAX_LENGTH, key="feedback_message")
        if st.button("Send anonymously", type="primary", icon=":material/send:"):
            try:
                s.submit_feedback(c.store(), None if face is None else face + 1,
                                  topic or "General", message)
            except DomainError as e:
                st.error(str(e), icon=":material/error:")
            else:
                c.forget("feedback_")
                st.session_state["feedback_sent"] = True
                st.session_state["_feedback_count"] = sent + 1
                st.rerun()
