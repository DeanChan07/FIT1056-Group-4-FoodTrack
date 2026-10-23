"""Several browser tabs using the app at the same time. Every save is one SQLite
transaction (BEGIN IMMEDIATE), so only one writer runs at a time."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pytest

from foodshare import domain as d
from foodshare import services as s
from foodshare.domain import DomainError, EditConflict
from conftest import NEW_PASSWORD, user, ready_pickup, send_feedback
from seed import DEMO_PASSWORD



def test_simultaneous_saves_are_all_kept(store):
    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(lambda n: send_feedback(store, "4", "General", f"note {n}"), range(40)))
    rows = store.reader().all("feedback")
    assert len(rows) == 43
    assert len({f["id"] for f in rows}) == 43


def test_simultaneous_allocations_never_oversell(store):
    staff = s.login(store, "staff", DEMO_PASSWORD)
    ravi = s.login(store, "recipient2", DEMO_PASSWORD)
    tomorrow = (d.today() + timedelta(days=1)).isoformat()
    available = s.get_batch(store, staff, 1)["available"]

    def allocate(_):
        try:
            s.create_allocation(store, staff, ravi["id"], [{"batch_id": 1, "quantity": 1}],
                                tomorrow, "10:00")
            return True
        except DomainError:
            return False

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(allocate, range(available + 10)))
    assert results.count(True) == available
    assert s.get_batch(store, staff, 1)["available"] == 0


def test_stale_correction_form_cannot_undo_a_collection(store):
    ready_pickup(store)
    staff = s.login(store, "staff", DEMO_PASSWORD)
    loaded = store.reader().get("batches", 1)["quantity"]  # the form showed 20
    s.record_collection(store, staff, 1, {})  # someone else gives out 2 while the form is open
    with pytest.raises(EditConflict):
        s.adjust_stock(store, staff, 1, 5, "Found a box", loaded_quantity=loaded)
    assert store.reader().get("batches", 1)["quantity"] == 18


def test_stale_needs_form_cannot_erase_a_new_allergy(store):
    staff = s.login(store, "staff", DEMO_PASSWORD)
    rina = s.login(store, "recipient", DEMO_PASSWORD)
    version = str(s.get_profile(store, rina, rina["id"]).get("version", 0))
    staff_form = {"household_size": "2", "allergies": "", "loaded_version": version}
    # Rina adds an allergy while staff have the same profile open.
    s.save_profile(store, rina, rina["id"], dict(staff_form, allergies="Peanuts"))
    with pytest.raises(EditConflict):
        s.save_profile(store, staff, rina["id"], staff_form, consent=True)
    assert "peanut" in str(s.get_profile(store, rina, rina["id"])["allergies"]).lower()


def test_collection_form_from_before_a_swap_is_refused(store):
    ready_pickup(store)
    staff = s.login(store, "staff", DEMO_PASSWORD)
    rina = s.login(store, "recipient", DEMO_PASSWORD)
    shown = {i["item_id"]: str(i["batch_id"]) for i in s.get_allocation(store, staff, 1)["items"]}
    sw = s.request_swap(store, rina, 1, 1)
    chickpeas = next(b for b in store.reader().all("batches") if b["name"] == "Canned chickpeas")
    s.approve_swap(store, staff, sw["id"], chickpeas["id"])
    before = store.reader().all("batches")
    with pytest.raises(EditConflict):
        s.record_collection(store, staff, 1, {}, batch_ids=shown)
    assert store.reader().get("allocations", 1)["status"] == d.ALLOCATED
    assert store.reader().all("batches") == before


def test_reading_notices_leaves_a_newer_one_unread(store):
    staff = s.login(store, "staff", DEMO_PASSWORD)
    rina = s.login(store, "recipient", DEMO_PASSWORD)
    shown = {n["id"] for n in s.list_notifications(store, rina)}
    tomorrow = (d.today() + timedelta(days=1)).isoformat()
    new = s.update_pickup(store, staff, 1, tomorrow, "15:00")  # arrives while the page loads
    s.mark_notifications_read(store, rina, shown)
    assert s.unread_count(store, rina) == 1
    assert store.reader().get("notifications", new["id"])["read"] is False
