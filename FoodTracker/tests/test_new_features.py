"""Rules for the anonymous feedback box, the estimated pickup queue and swap withdrawal.
The pages themselves are tested in test_app.py."""

from datetime import date, timedelta

import pytest

from foodshare import domain as d
from foodshare import services as s
from foodshare.domain import DomainError, PermissionDenied
from conftest import NEW_PASSWORD, user
from seed import DEMO_PASSWORD


def day(n):
    return (date.today() + timedelta(days=n)).isoformat()




# ---------------------------------------------------------------- anonymous feedback

def test_feedback_needs_a_rating_or_message(store):
    with pytest.raises(DomainError):
        s.submit_feedback(store, "", "General", "   ")
    with pytest.raises(DomainError):
        s.submit_feedback(store, "9", "General", "")
    with pytest.raises(DomainError):
        s.submit_feedback(store, "", "General", "x" * (d.FEEDBACK_MAX_LENGTH + 1))


def test_feedback_stores_nothing_identifying(store):
    item = s.submit_feedback(store, "4", "Pickup and waiting", "Quick and friendly")
    assert set(item) == {"id", "rating", "category", "message", "submitted_on", "reviewed",
                         "archived"}
    assert len(item["submitted_on"]) == 10  # date only, no time of day
    s.submit_feedback(store, "", "Not a real category", "Hello")
    assert store.reader().all("feedback")[-1]["category"] == "General"


def test_feedback_inbox_is_staff_and_manager_only(store):
    s.submit_feedback(store, "2", "Food quality", "")
    inbox = s.feedback_inbox(store, user(store, "staff"))
    assert inbox["total"] == 4 and inbox["new"] == 4 and inbox["by_rating"][2] == 1
    assert s.feedback_inbox(store, user(store, "manager"))["total"] == 4
    for name in ("volunteer", "recipient", "admin"):
        with pytest.raises(PermissionDenied):
            s.feedback_inbox(store, user(store, name))


def test_mark_feedback_reviewed(store):
    staff = user(store, "staff")
    s.mark_feedback_reviewed(store, staff, 1)
    assert s.feedback_inbox(store, staff)["new"] == 2


# ---------------------------------------------------------------- pickup queue

def test_queue_staggers_people_booked_at_the_same_time(store):
    staff = user(store, "staff")
    q = s.pickup_queue(store, staff, day(1))
    assert [row["position"] for row in q["queue"]] == [1, 2]
    first, second = q["queue"]
    assert (first["window_start"], first["window_end"]) == ("14:00", "14:15")
    assert (second["window_start"], second["delay"]) == ("14:06", 6)


def test_recipient_sees_only_their_own_place(store):
    rina, ravi = user(store, "recipient"), user(store, "recipient2")
    mine = s.queue_status(store, ravi, 2)
    assert mine["position"] == 2 and mine["ahead"] == 1 and mine["total"] == 2
    assert "recipient_name" not in mine
    with pytest.raises(PermissionDenied):
        s.queue_status(store, rina, 2)
    with pytest.raises(PermissionDenied):
        s.pickup_queue(store, rina)


def test_queue_moves_up_after_collection(store):
    staff, ravi = user(store, "staff"), user(store, "recipient2")
    s.record_collection(store, staff, 1, {})
    mine = s.queue_status(store, ravi, 2)
    assert mine["position"] == 1 and mine["ahead"] == 0 and mine["window_start"] == "14:00"
    assert s.queue_status(store, user(store, "recipient"), 1) is None


def test_queue_follows_rescheduled_pickups_and_settings(store):
    staff, ravi = user(store, "staff"), user(store, "recipient2")
    s.update_pickup(store, staff, 2, day(1), "13:30")
    assert s.queue_status(store, ravi, 2)["position"] == 1
    s.set_queue_settings(store, staff, 10, 20)
    rina = s.queue_status(store, user(store, "recipient"), 1)
    assert (rina["window_start"], rina["window_end"]) == ("14:00", "14:20")
    with pytest.raises(DomainError):
        s.set_queue_settings(store, staff, 0, 20)


def test_bad_pickup_time_is_rejected(store):
    staff = user(store, "staff")
    with pytest.raises(DomainError):
        s.update_pickup(store, staff, 1, day(1), "2pm")


def test_queue_defaults_to_next_day_with_pickups(store):
    q = s.pickup_queue(store, user(store, "staff"))
    assert q["date"] == day(1) and q["upcoming"] == [(day(1), 2)]


# ---------------------------------------------------------------- private swap: withdraw

def test_recipient_can_withdraw_and_ask_again(store):
    rina, ravi = user(store, "recipient"), user(store, "recipient2")
    sw = s.request_swap(store, rina, 1, 1, "I can't eat this")
    with pytest.raises(PermissionDenied):
        s.withdraw_swap(store, ravi, sw["id"])
    s.withdraw_swap(store, rina, sw["id"])
    assert s.list_swaps(store, rina)[0]["status"] == d.WITHDRAWN
    with pytest.raises(DomainError):
        s.withdraw_swap(store, rina, sw["id"])
    assert s.request_swap(store, rina, 1, 1)["status"] == d.PENDING


def test_withdrawn_swap_cannot_be_approved(store):
    rina, staff = user(store, "recipient"), user(store, "staff")
    sw = s.request_swap(store, rina, 1, 1)
    s.withdraw_swap(store, rina, sw["id"])
    with pytest.raises(DomainError):
        s.approve_swap(store, staff, sw["id"], 2)
