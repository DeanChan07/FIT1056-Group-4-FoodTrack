"""Service tests named after the SRS acceptance criteria (AC-xx)."""

import json
from datetime import date, timedelta

import pytest

from foodshare import domain as d
from foodshare import services as s
from foodshare.domain import DomainError, PermissionDenied
from conftest import NEW_PASSWORD, user
from seed import DEMO_PASSWORD


def day(n):
    return (date.today() + timedelta(days=n)).isoformat()




# F-01 accounts

def test_ac01_self_registration_creates_recipient(store):
    u = s.register_recipient(store, "newbie", NEW_PASSWORD, "New Person")
    assert u["role"] == d.RECIPIENT


def test_ac02_self_registration_rejects_internal_role(store):
    with pytest.raises(PermissionDenied):
        s.register_recipient(store, "sneaky", NEW_PASSWORD, "Sneaky", role="admin")
    with pytest.raises(DomainError):
        s.login(store, "sneaky", NEW_PASSWORD)


def test_ac04_volunteer_cannot_read_recipient_profile(store):
    vol, rec = user(store, "volunteer"), user(store, "recipient")
    with pytest.raises(PermissionDenied):
        s.get_profile(store, vol, rec["id"])


def test_ac05_manager_deactivates_volunteer_after_confirmation(store):
    mgr, vol = user(store, "manager"), user(store, "volunteer")
    with pytest.raises(DomainError):
        s.deactivate_account(store, mgr, vol["id"], confirmed=False)
    s.deactivate_account(store, mgr, vol["id"], confirmed=True)
    with pytest.raises(DomainError):
        user(store, "volunteer")


def test_ac06_admin_creates_manager_only(store):
    admin = user(store, "admin")
    m = s.create_internal_account(store, admin, "mgr2", NEW_PASSWORD, "M2", d.MANAGER)
    assert m["role"] == d.MANAGER
    with pytest.raises(PermissionDenied):
        s.create_internal_account(store, admin, "st2", NEW_PASSWORD, "S2", d.STAFF)


def test_ac07_recipient_deactivation_keeps_verification(store):
    staff, rec = user(store, "staff"), user(store, "recipient2")
    with pytest.raises(DomainError):
        s.deactivate_account(store, staff, rec["id"], True, "")
    u = s.deactivate_account(store, staff, rec["id"], True, "Asked in person, ID checked")
    assert not u["active"] and u["deactivation_verification"]["note"]


# F-02 donations

def test_ac08_to_ac10_schedule_and_unique_reference(store):
    a = s.schedule_donation(store, [{"item_type": "Pasta", "quantity": 3}], day(1), "10:00")
    b = s.schedule_donation(store, [{"item_type": "Oats", "quantity": 2}], day(1), "11:00")
    assert a["reference"] and a["reference"] != b["reference"]
    with pytest.raises(DomainError):
        s.schedule_donation(store, [{"item_type": "", "quantity": ""}], day(1), "10:00")


def test_ac11_ac12_receive_adds_only_accepted(store):
    vol = user(store, "volunteer")
    dn = s.schedule_donation(store, [{"item_type": "Soup", "quantity": 7}], day(1), "10:00")
    done = s.receive_donation(store, vol, dn["reference"],
                              [{"accepted_qty": 5, "expiry_date": day(60)}])
    assert done["status"] == d.COLLECTED and "received" in done["receipt"]
    soup = [b for b in store.reader().all("batches") if b["name"] == "Soup"]
    assert soup[0]["quantity"] == 5
    assert s.find_donation(store, dn["reference"].lower())["status"] == d.COLLECTED


# F-03 inventory

def test_ac15_ac16_near_expiry_boundary():
    assert d.is_near_expiry({"expiry_date": day(7)})
    assert not d.is_near_expiry({"expiry_date": day(8)})
    assert d.is_expired({"expiry_date": day(-1)})


def test_ac17_expired_batch_cannot_be_allocated(store):
    staff, rec = user(store, "staff"), user(store, "recipient2")
    yoghurt = next(b for b in store.reader().all("batches") if b["name"] == "Yoghurt")
    with pytest.raises(DomainError):
        s.create_allocation(store, staff, rec["id"],
                            [{"batch_id": yoghurt["id"], "quantity": 1}], day(1), "10:00")
    assert store.reader().get("batches", yoghurt["id"])["quantity"] == 10


# F-04 profiles

def test_ac19_staff_needs_permission(store):
    staff, rec = user(store, "staff"), user(store, "recipient2")
    with pytest.raises(DomainError):
        s.save_profile(store, staff, rec["id"], {"household_size": 2})
    p = s.save_profile(store, staff, rec["id"], {"household_size": 2}, consent=True)
    assert p["updated_by"] == staff["id"]


# F-05 allocation

def test_ac23_allergy_conflict_blocked(store):
    staff, rec = user(store, "staff"), user(store, "recipient")
    pb = next(b for b in store.reader().all("batches") if b["name"] == "Peanut butter")
    with pytest.raises(DomainError, match="not suitable"):
        s.create_allocation(store, staff, rec["id"], [{"batch_id": pb["id"], "quantity": 1}],
                            day(1), "10:00")


def test_ac26_collection_subtracts_stock(store):
    staff = user(store, "staff")
    s.record_collection(store, staff, 1, {})
    rice = store.reader().get("batches", 1)
    assert rice["quantity"] == 18


def test_ac27_cannot_issue_more_than_stock(store):
    staff = user(store, "staff")
    with store.transaction() as tx:
        tx.get("batches", 1)["quantity"] = 1  # less than the 2 allocated
    with pytest.raises(DomainError):
        s.record_collection(store, staff, 1, {})
    assert store.reader().get("batches", 1)["quantity"] == 1
    assert store.reader().all("distributions") == []


# F-06 tasks

def test_ac29_ac32_task_rules(store):
    staff, vol = user(store, "staff"), user(store, "volunteer")
    with pytest.raises(DomainError):
        s.assign_task(store, staff, vol["id"], "Receiving", day(1), "", "")
    with pytest.raises(PermissionDenied):
        s.assign_task(store, vol, vol["id"], "Receiving", day(1), "09:00", "")
    assert all(t["volunteer_id"] == vol["id"] for t in s.list_tasks(store, vol))


# F-07 notices

def test_ac33_pickup_change_creates_unread_notice(store):
    staff, rec = user(store, "staff"), user(store, "recipient")
    s.update_pickup(store, staff, 1, day(2), "15:00")
    assert s.unread_count(store, rec) == 1
    assert s.get_allocation(store, rec, 1)["pickup_time"] == "15:00"


def test_ac36_ac37_low_stock_threshold(store):
    staff = user(store, "staff")
    s.set_low_stock_threshold(store, staff, 6)
    names = [x["name"] for x in s.stock_alerts(store, staff)["low_stock"]]
    assert "Halal chicken" in names and "Bread loaf" in names


# F-08 reports

def test_ac39_bad_range_and_ac42_volunteer_denied(store):
    staff, vol = user(store, "staff"), user(store, "volunteer")
    with pytest.raises(DomainError):
        s.build_report(store, staff, day(1), day(0))
    with pytest.raises(PermissionDenied):
        s.build_report(store, vol, day(-1), day(0))


def test_ac41_csv_matches_totals(store):
    staff = user(store, "staff")
    s.record_collection(store, staff, 1, {})
    report = s.build_report(store, staff, day(-1), day(0))
    text = s.report_csv(report)
    assert report["total_distributed"] == 3
    assert "Total distributed units,3" in text


# F-09 swaps

def test_ac44_to_ac46_swap_request_rules(store):
    rec = user(store, "recipient")
    sw = s.request_swap(store, rec, 1, 1)
    assert sw["status"] == d.PENDING
    with pytest.raises(DomainError):
        s.request_swap(store, rec, 1, 1)


def test_ac45_no_swap_after_collection(store):
    staff, rec = user(store, "staff"), user(store, "recipient")
    s.record_collection(store, staff, 1, {})
    with pytest.raises(DomainError):
        s.request_swap(store, rec, 1, 1)


def test_ac47_volunteer_cannot_see_reason(store):
    rec, vol = user(store, "recipient"), user(store, "volunteer")
    s.request_swap(store, rec, 1, 1, "Prefer something else")
    with pytest.raises(PermissionDenied):
        s.list_swaps(store, vol)


def test_ac48_ac49_approve_swap(store):
    staff, rec = user(store, "staff"), user(store, "recipient")
    sw = s.request_swap(store, rec, 1, 1)
    pb = next(b for b in store.reader().all("batches") if b["name"] == "Peanut butter")
    with pytest.raises(DomainError):
        s.approve_swap(store, staff, sw["id"], pb["id"])
    chickpeas = next(b for b in store.reader().all("batches") if b["name"] == "Canned chickpeas")
    s.approve_swap(store, staff, sw["id"], chickpeas["id"])
    alloc = s.get_allocation(store, rec, 1)
    assert alloc["items"][0]["name"] == "Canned chickpeas"
    assert s.get_batch(store, staff, chickpeas["id"])["available"] == 10
    assert s.get_batch(store, staff, 1)["available"] == 20


def test_ac50_decline_visible_to_recipient(store):
    staff, rec = user(store, "staff"), user(store, "recipient")
    sw = s.request_swap(store, rec, 1, 2)
    s.decline_swap(store, staff, sw["id"], "Sorry, nothing suitable today.")
    mine = s.list_swaps(store, rec)
    assert mine[0]["status"] == d.DECLINED and mine[0]["response"]


# NFR-03: failed saves leave the file unchanged

def test_failed_transaction_writes_nothing(store):
    before = json.dumps(store.dump(), sort_keys=True)
    with pytest.raises(RuntimeError):
        with store.transaction() as tx:
            tx.get("batches", 1)["quantity"] = 0
            raise RuntimeError("boom")
    assert json.dumps(store.dump(), sort_keys=True) == before
