"""The Streamlit pages, run headless with Streamlit's own test runner (AppTest).

Each test signs in as a demo person, opens a page, fills it in and clicks its
buttons, then checks the data file."""

from datetime import date, time, timedelta

import pytest
from streamlit.testing.v1 import AppTest

from foodshare import domain as d
from foodshare import services as s
from foodshare.views import nav
from conftest import NEW_PASSWORD, user, ready_pickup, send_feedback
from seed import DEMO_PASSWORD

APP = str(__import__("pathlib").Path(__file__).resolve().parent.parent / "app.py")
ROLE_USERNAMES = {None: None, d.RECIPIENT: "recipient", d.VOLUNTEER: "volunteer",
                  d.STAFF: "staff", d.MANAGER: "manager", d.ADMIN: "admin"}



def user_id(store, username):
    return store.reader().find_one("users", username=username)["id"]


def signed_in(at, store, username):
    """Give the test browser a real session, as signing in does."""
    person = user(store, username)
    at.session_state["session_token"] = s.start_session(store, person)
    at.session_state["user_id"] = person["id"]
    return at


def open_page(store, key, username=None):
    """Run one page as if it were chosen in the menu."""
    func = nav.PAGES[key][0]
    at = AppTest.from_string(f"from {func.__module__} import {func.__name__}\n"
                             f"{func.__name__}()\n", default_timeout=30)
    if username:
        signed_in(at, store, username)
    return at.run()


def click(at, label):
    next(b for b in at.button if b.label == label).click()
    return at.run()


def shown(at):
    """All the text on the page, to look for messages."""
    parts = [e.value for kind in ("markdown", "success", "error", "info", "warning", "caption")
             for e in getattr(at, kind)]
    return "\n".join(str(p) for p in parts)


def no_errors(at):
    assert not at.exception, [e.value for e in at.exception]


# ---------------------------------------------------------------- every page, every role

@pytest.mark.parametrize("role,key", [(role, key) for role, keys in nav.MENUS.items()
                                      for key in keys])
def test_every_menu_page_opens_for_its_role(store, role, key):
    no_errors(open_page(store, key, ROLE_USERNAMES[role]))


@pytest.mark.parametrize("key", ["inventory", "receive", "recipients", "allocations", "queue",
                                 "swaps", "tasks", "reports", "feedback_inbox", "alerts",
                                 "accounts"])
def test_team_pages_refuse_a_recipient(store, key):
    at = open_page(store, key, "recipient")
    assert at.exception and "do not have access" in at.exception[0].value


@pytest.mark.parametrize("username,greeting", [
    (None, "FoodShare Tracker"), ("recipient", "Hi Rina"), ("volunteer", "Hi Vic"),
    ("staff", "Hi Sam"), ("manager", "Hi Mia"), ("admin", "Hi Ivy")])
def test_app_opens_on_each_roles_home(store, username, greeting):
    at = AppTest.from_file(APP, default_timeout=30)
    if username:
        signed_in(at, store, username)
    at.run()
    no_errors(at)
    assert greeting in shown(at)
    assert any(b.label == "Sign out" for b in at.sidebar.button) == bool(username)


def test_sign_out(store):
    at = AppTest.from_file(APP, default_timeout=30)
    signed_in(at, store, "staff")
    at.run()
    next(b for b in at.sidebar.button if b.label == "Sign out").click()
    at.run()
    assert "user_id" not in at.session_state
    assert "You have signed out." in shown(at)


# ---------------------------------------------------------------- signing in

def test_sign_in(store):
    at = open_page(store, "sign_in")
    at.text_input[0].input("Staff ")
    at.text_input[1].input(DEMO_PASSWORD)
    at = click(at, "Sign in")
    assert at.session_state["user_id"] == user_id(store, "staff")


def test_wrong_password_is_refused(store):
    at = open_page(store, "sign_in")
    at.text_input[0].input("staff")
    at.text_input[1].input("nope")
    at = click(at, "Sign in")
    assert "user_id" not in at.session_state
    assert "incorrect" in shown(at)


def test_register_makes_a_recipient(store):
    at = open_page(store, "register")
    at.text_input[0].input("Rosa")
    at.text_input[1].input("rosa")
    at.text_input[2].input(NEW_PASSWORD)
    at = click(at, "Create account")
    new = store.reader().find_one("users", username="rosa")
    assert new["role"] == d.RECIPIENT and at.session_state["user_id"] == new["id"]


# ---------------------------------------------------------------- donors and feedback

def test_donation_status_by_reference(store):
    at = open_page(store, "donation_status")
    at.text_input[0].input("dn-demo01")
    at = click(at, "Check")
    no_errors(at)
    assert "DN-DEMO01" in shown(at) and "not been received" in shown(at)


def test_anonymous_feedback(store):
    at = open_page(store, "feedback", "recipient")  # signed in, still anonymous
    at.text_area[0].input("Lovely volunteers")
    at = click(at, "Send anonymously")
    no_errors(at)
    last = store.reader().all("feedback")[-1]
    assert last["message"] == "Lovely volunteers"
    assert set(last) == {"id", "message", "submitted_on", "reviewed",
                         "archived"}
    assert "Thank you" in shown(at)


# ---------------------------------------------------------------- staff and volunteers

def test_receive_a_donation(store):
    at = open_page(store, "receive", "volunteer")
    at.selectbox(key="recv_ref").select("DN-DEMO01")
    at.run()
    at.number_input(key=f"recv1_1_qty").set_value(4)
    at = click(at, "Record donation")
    no_errors(at)
    donation = s.find_donation(store, "DN-DEMO01")
    assert donation["status"] == d.COLLECTED
    assert [i["accepted_qty"] for i in donation["items"]] == [10, 4]
    assert "was received" in shown(at)


def test_staff_add_stock(store):
    at = open_page(store, "inventory", "staff")
    at.text_input(key="batchnew_name").input("Oats")
    at.number_input(key="batchnew_quantity").set_value(9)
    at = click(at, "Add to inventory")
    no_errors(at)
    oats = store.reader().find_one("batches", name="Oats")
    assert oats["quantity"] == 9 and "Stock saved." in shown(at)


def test_manager_cannot_change_stock(store):
    at = open_page(store, "inventory", "manager")
    assert not any(b.label == "Add to inventory" for b in at.button)


def test_staff_set_food_aside(store):
    at = open_page(store, "recipients", "staff")
    ravi = user_id(store, "recipient2")
    at.selectbox(key="rec_open").select(ravi)
    at.run()
    at.number_input(key=f"alloc{ravi}_2").set_value(3)  # canned chickpeas
    at = click(at, "Save allocation")
    no_errors(at)
    newest = store.reader().all("allocations")[-1]
    assert newest["recipient_id"] == ravi
    assert newest["items"] == [{"item_id": 1, "batch_id": 2, "name": "Canned chickpeas",
                                "quantity": 3}]


def test_unsafe_food_cannot_be_chosen(store):
    at = open_page(store, "recipients", "staff")
    rina = user_id(store, "recipient")
    at.selectbox(key="rec_open").select(rina)
    at.run()
    keys = {w.key for w in at.number_input}
    assert f"alloc{rina}_3" not in keys  # peanut butter: Rina is allergic
    assert "contains peanut" in str([df.value for df in at.dataframe])


def test_record_a_collection(store):
    ready_pickup(store)
    at = open_page(store, "allocations", "staff")
    at.selectbox(key="alloc_open").select(1)
    at.run()
    at = click(at, "Confirm collection")
    no_errors(at)
    assert store.reader().get("allocations", 1)["status"] == d.COLLECTED
    assert store.reader().get("batches", 1)["quantity"] == 18


def test_change_pickup_time_sends_a_notice(store):
    at = open_page(store, "allocations", "staff")
    at.selectbox(key="alloc_open").select(1)
    at.run()
    at.time_input(key="pick1_time").set_value(time(15, 30))
    at = click(at, "Save and notify")
    no_errors(at)
    assert store.reader().get("allocations", 1)["pickup_time"] == "15:30"
    rina = user_id(store, "recipient")
    assert store.reader().find_one("notifications", user_id=rina)["read"] is False


def test_queue_timing(store):
    at = open_page(store, "queue", "staff")
    at.number_input(key="queue_step").set_value(10)
    at = click(at, "Save timing")
    no_errors(at)
    assert store.reader().setting("minutes_per_pickup") == 10


def test_assign_a_task(store):
    at = open_page(store, "tasks", "manager")
    at.text_area(key="task_notes").input("Sort the bread")
    at = click(at, "Assign task")
    no_errors(at)
    assert store.reader().all("tasks")[-1]["instructions"] == "Sort the bread"


def test_volunteer_sees_only_their_tasks(store):
    at = open_page(store, "tasks", "volunteer")
    no_errors(at)
    assert not any(b.label == "Assign task" for b in at.button)
    assert "back door" in shown(at) and "Help at the pickup desk" in shown(at)


def test_manager_creates_a_volunteer(store):
    at = open_page(store, "accounts", "manager")
    at.text_input(key="acct_new_name").input("Val")
    at.selectbox(key="acct_new_role").select(d.VOLUNTEER)
    at.text_input(key="acct_new_username").input("val")
    at.text_input(key="acct_new_password").input(NEW_PASSWORD)
    at = click(at, "Create account")
    no_errors(at)
    assert store.reader().find_one("users", username="val")["role"] == d.VOLUNTEER


def test_staff_deactivate_a_recipient_needs_a_note(store):
    at = open_page(store, "accounts", "staff")
    ravi = user_id(store, "recipient2")
    at.selectbox(key="acct_off_who").select(ravi)
    at.checkbox(key="acct_off_sure").check()
    at = click(at, "Deactivate")
    assert "how the request was verified" in shown(at)
    at.text_input(key="acct_off_note").input("In person with ID")
    at = click(at, "Deactivate")
    assert store.reader().get("users", ravi)["active"] is False


def test_reports_csv(store):
    ready_pickup(store)
    s.record_collection(store, s.login(store, "staff", DEMO_PASSWORD), 1, {})
    at = open_page(store, "reports", "manager")
    no_errors(at)
    assert at.metric[1].value == "3"  # 2 rice + 1 chicken given out


def test_feedback_inbox_mark_reviewed(store):
    at = open_page(store, "feedback_inbox", "staff")
    at = click(at, "Mark as reviewed")
    no_errors(at)
    assert sum(f["reviewed"] for f in store.reader().all("feedback")) == 1


# ---------------------------------------------------------------- recipients

def test_recipient_home_shows_their_queue_place(store):
    at = open_page(store, "recipient_home", "recipient2")
    no_errors(at)
    values = [m.value for m in at.metric]
    assert "Check in when you arrive" in shown(at)
    assert not any("#None" in value for value in values)


def test_recipient_asks_for_a_private_swap(store):
    at = open_page(store, "my_food", "recipient")
    at.button(key="swapbtn_1_1").click()
    at.run()
    at.text_area(key="swap_note").input("No way to cook rice")
    at = click(at, "Send request")
    no_errors(at)
    sw = store.reader().find_one("swaps", item_id=1)
    assert sw["status"] == d.PENDING and sw["reason"] == "No way to cook rice"


def test_staff_approve_a_swap(store):
    rina = s.login(store, "recipient", DEMO_PASSWORD)
    s.request_swap(store, rina, 1, 1, "")
    at = open_page(store, "swaps", "staff")
    chickpeas = store.reader().find_one("batches", name="Canned chickpeas")["id"]
    at.radio(key="swap1_pick").set_value(chickpeas)
    at = click(at, "Approve swap")
    no_errors(at)
    assert store.reader().get("swaps", 1)["status"] == d.APPROVED
    assert store.reader().get("allocations", 1)["items"][0]["name"] == "Canned chickpeas"


def test_recipient_withdraws_a_swap(store):
    s.request_swap(store, s.login(store, "recipient", DEMO_PASSWORD), 1, 1, "")
    at = open_page(store, "my_swaps", "recipient")
    at = click(at, "Withdraw request")
    no_errors(at)
    assert store.reader().get("swaps", 1)["status"] == d.WITHDRAWN


def test_recipient_updates_their_needs(store):
    at = open_page(store, "my_needs", "recipient")
    at.multiselect(key=f"prof{user_id(store, 'recipient')}_allergies").set_value(["peanut", "sesame"])
    at = click(at, "Save needs")
    no_errors(at)
    profile = store.reader().find_one("profiles", recipient_id=user_id(store, "recipient"))
    assert profile["allergies"] == ["peanut", "sesame"]


def test_notices_are_marked_read_once_seen(store):
    staff = s.login(store, "staff", DEMO_PASSWORD)
    s.update_pickup(store, staff, 1, (date.today() + timedelta(days=2)).isoformat(), "10:00")
    rina = s.login(store, "recipient", DEMO_PASSWORD)
    assert s.unread_count(store, rina) == 1
    at = open_page(store, "notices", "recipient")
    no_errors(at)
    assert "Pickup change" in shown(at)
    assert s.unread_count(store, rina) == 0


# ---------------------------------------------------------------- two tabs at once

def test_stock_form_cannot_undo_someone_elses_change(store):
    ready_pickup(store)
    at = open_page(store, "inventory", "staff")
    at.selectbox(key="inv_fix").select(1)
    at.run()
    at.number_input(key="fix1_change").set_value(5)
    at.text_input(key="fix1_reason").input("Found a box")
    s.record_collection(store, s.login(store, "staff", DEMO_PASSWORD), 1, {})  # other tab
    at = click(at, "Save correction")
    assert "Someone changed this stock" in shown(at)
    assert store.reader().get("batches", 1)["quantity"] == 18


def test_needs_form_cannot_erase_a_new_allergy(store):
    rina = user_id(store, "recipient")
    at = open_page(store, "my_needs", "recipient")
    staff = s.login(store, "staff", DEMO_PASSWORD)
    s.save_profile(store, staff, rina, {"household_size": 4, "allergies": "peanut, egg"},
                   consent=True)  # staff add an allergy in another tab
    at.number_input(key=f"prof{rina}_household_size").set_value(5)
    at = click(at, "Save needs")
    assert "Someone else changed this profile" in shown(at)
    assert "egg" in store.reader().find_one("profiles", recipient_id=rina)["allergies"]


def test_collection_form_from_before_a_swap_is_refused(store):
    ready_pickup(store)
    at = open_page(store, "allocations", "staff")
    at.selectbox(key="alloc_open").select(1)
    at.run()
    staff = s.login(store, "staff", DEMO_PASSWORD)
    sw = s.request_swap(store, s.login(store, "recipient", DEMO_PASSWORD), 1, 1, "")
    chickpeas = store.reader().find_one("batches", name="Canned chickpeas")["id"]
    s.approve_swap(store, staff, sw["id"], chickpeas)
    at = click(at, "Confirm collection")
    assert "This allocation changed" in shown(at)
    assert store.reader().get("allocations", 1)["status"] == d.ALLOCATED


# ---------------------------------------------------------------- screens added for SRS v1.5

@pytest.fixture
def ten_am(monkeypatch):
    """Pretend it is 10:00 today, so same-day pickups and check-in behave the same
    whenever the tests run."""
    from datetime import datetime
    fixed = datetime.combine(date.today(), time(10, 0))
    monkeypatch.setattr(d, "now", lambda: fixed)
    return fixed


def pickup_today(store, at="11:00"):
    return s.create_allocation(store, user(store, "staff"), user_id(store, "recipient2"),
                               [{"batch_id": 2, "quantity": 1}], date.today().isoformat(), at)


def test_staff_cancel_a_pickup(store):
    at = open_page(store, "allocations", "staff")
    at.selectbox(key="alloc_open").select(1)
    at.run()
    at.text_input(key="cancel1_reason").input("Asked to cancel by phone")
    at.checkbox(key="cancel1_sure").check()
    at = click(at, "Cancel pickup")
    no_errors(at)
    assert store.reader().get("allocations", 1)["status"] == d.CANCELLED
    assert "back on the shelf" in shown(at)


def test_staff_correct_stock_and_undo_it(store):
    at = open_page(store, "inventory", "staff")
    at.selectbox(key="inv_fix").select(2)
    at.run()
    at.number_input(key="fix2_change").set_value(-2)
    at.text_input(key="fix2_reason").input("Two tins dented")
    at = click(at, "Save correction")
    no_errors(at)
    assert store.reader().get("batches", 2)["quantity"] == 10
    at.text_input(key="fix2_rev_reason").input("Tins were fine")
    at = click(at, "Undo correction")
    no_errors(at)
    assert store.reader().get("batches", 2)["quantity"] == 12


def test_recipient_checks_in_from_home(store, ten_am):
    alloc = pickup_today(store)
    at = open_page(store, "recipient_home", "recipient2")
    no_errors(at)
    at.button(key=f"checkin_{alloc['id']}").click()
    at.run()
    no_errors(at)
    assert store.reader().get("allocations", alloc["id"])["queue_state"] == d.WAITING


def test_staff_serve_from_the_queue_desk(store, ten_am):
    alloc = pickup_today(store)
    s.check_in(store, user(store, "recipient2"), alloc["id"])
    at = open_page(store, "queue", "staff")
    at.selectbox(key="queue_day").select(date.today().isoformat())
    at.run()
    at = click(at, "Start serving")
    no_errors(at)
    assert store.reader().get("allocations", alloc["id"])["queue_state"] == d.SERVING


def test_volunteer_records_todays_collection(store, ten_am):
    alloc = pickup_today(store)
    at = open_page(store, "allocations", "volunteer")
    no_errors(at)
    at = click(at, "Confirm collection")
    no_errors(at)
    assert store.reader().get("allocations", alloc["id"])["status"] == d.COLLECTED


def test_audit_page_shows_admins_sign_ins_only(store):
    at = open_page(store, "audit", "admin")
    no_errors(at)
    text = str([df.value for df in at.dataframe])
    assert "Signed in" in text and "Food set aside" not in text


def test_feedback_box_stops_after_five_in_one_session(store):
    at = open_page(store, "feedback")
    browser = at.session_state["_feedback_browser"]
    for _ in range(5):
        _, form = s.feedback_form(browser)
        s.submit_feedback(store, "A message", browser_token=browser, form_token=form)
    at.text_area[0].input("Sixth message")
    at = click(at, "Send anonymously")
    assert "ten minutes" in shown(at)
    assert len(store.dump()["feedback"]) == 8


def test_typed_names_are_not_turned_into_links(store):
    s.register_recipient(store, "trick", NEW_PASSWORD, "[Click me](http://bad.example)")
    at = open_page(store, "recipients", "staff")
    no_errors(at)
    assert "](http" not in "".join(m.value for m in at.markdown)
