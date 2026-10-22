"""One or more tests for each problem found in the Flask vs Streamlit review
(the IDs C1, C4, M6 ... are the issue numbers in that review), plus the SRS v1.5
features that were added to this version: audit log, stock corrections, safety holds,
check-in queue, swap expiry, IT Admin recovery and sessions."""

import sqlite3
from datetime import date, datetime, timedelta

import pytest

import manage
from foodshare import domain as d
from foodshare import services as s
from foodshare.domain import DomainError, EditConflict, PermissionDenied
from foodshare.storage import SqliteStore
from foodshare.views.common import esc
from conftest import NEW_PASSWORD, user, ready_pickup, send_feedback
from seed import DEMO_PASSWORD, seed


class Clock:
    """Pretend it is a certain time, and move it forward, without waiting."""

    def __init__(self, monkeypatch, start):
        self.now = start
        monkeypatch.setattr(d, "now", lambda: self.now)
        monkeypatch.setattr(d, "today", lambda: self.now.date())

    def forward(self, **kwargs):
        self.now += timedelta(**kwargs)


@pytest.fixture
def clock(monkeypatch):
    return Clock(monkeypatch, datetime.combine(date.today(), datetime.min.time())
                 + timedelta(hours=10))  # 10:00 today


def day(n):
    return (d.today() + timedelta(days=n)).isoformat()


def today_pickup(store, at="11:00", recipient="recipient2", batch_id=2, qty=1):
    staff = user(store, "staff")
    return s.create_allocation(store, staff, user(store, recipient)["id"],
                               [{"batch_id": batch_id, "quantity": qty}], day(0), at)


# ---------------------------------------------------------------- C1 fresh install signs in

def test_c1_documented_demo_password_works_on_a_fresh_install(tmp_path):
    store = seed(str(tmp_path / "fresh.sqlite3"))
    for name in ("admin", "manager", "staff", "volunteer", "recipient", "recipient2"):
        assert s.login(store, name, DEMO_PASSWORD)["username"] == name
    with pytest.raises(DomainError):
        s.login(store, "staff", "password123")  # the old short password is gone


def test_c1_seed_refuses_to_overwrite_existing_data(tmp_path):
    path = str(tmp_path / "fresh.sqlite3")
    seed(path)
    with pytest.raises(SystemExit):
        seed(path)


# ---------------------------------------------------------------- C4 cancel an allocation

def test_c4_cancel_releases_stock_closes_swaps_and_tells_the_recipient(store):
    staff, rina = user(store, "staff"), user(store, "recipient")
    assert s.get_batch(store, staff, 1)["available"] == 18
    sw = s.request_swap(store, rina, 1, 1, "private reason")
    with pytest.raises(DomainError):
        s.cancel_allocation(store, staff, 1, confirmed=False, reason="Asked by phone")
    with pytest.raises(DomainError):
        s.cancel_allocation(store, staff, 1, confirmed=True, reason="")
    s.cancel_allocation(store, staff, 1, confirmed=True, reason="Asked by phone")
    assert s.get_batch(store, staff, 1)["available"] == 20
    assert store.reader().get("swaps", sw["id"])["status"] == d.CANCELLED
    assert s.list_notifications(store, rina)[0]["kind"] == "Pickup cancelled"
    with pytest.raises(DomainError):
        s.cancel_allocation(store, staff, 1, confirmed=True, reason="again")
    with pytest.raises(PermissionDenied):
        s.cancel_allocation(store, user(store, "volunteer"), 2, True, "no")


# ---------------------------------------------------------------- C5 and M10 volunteers

def test_c5_volunteer_sees_no_allocations_without_a_shift_that_day(store):
    vol = user(store, "volunteer")
    assert s.list_allocations(store, vol) == []  # pickups are tomorrow
    with pytest.raises(PermissionDenied):
        s.get_allocation(store, vol, 1)


def test_c5_volunteer_on_shift_sees_today_only_and_never_swap_reasons(store, clock):
    alloc = today_pickup(store)
    s.request_swap(store, user(store, "recipient2"), alloc["id"], 1, "my child is allergic")
    vol = user(store, "volunteer")  # seed gives Vic a Distribution shift today
    assert [a["id"] for a in s.list_allocations(store, vol)] == [alloc["id"]]
    seen = s.get_allocation(store, vol, alloc["id"])
    assert seen["swaps"] == [] and "allergic" not in str(seen)
    with pytest.raises(PermissionDenied):
        s.list_swaps(store, vol)


def test_m10_volunteer_needs_a_distribution_shift_on_the_collection_day(store, clock):
    alloc = today_pickup(store)
    vol = user(store, "volunteer")
    with store.transaction() as tx:  # move today's shift to next week
        for t in tx.find("tasks", task_type="Distribution"):
            t["shift_date"] = day(7)
    with pytest.raises(PermissionDenied):
        s.record_collection(store, vol, alloc["id"], {})
    with store.transaction() as tx:
        for t in tx.find("tasks", task_type="Distribution"):
            t["shift_date"] = day(0)
    s.record_collection(store, vol, alloc["id"], {})
    assert store.reader().get("allocations", alloc["id"])["status"] == d.COLLECTED


# ---------------------------------------------------------------- C7 sign-in rules (NFR-09)

def test_c7_passwords_must_be_15_to_128_characters(store):
    with pytest.raises(DomainError, match="15"):
        s.register_recipient(store, "shorty", "password123", "Shorty")
    with pytest.raises(DomainError):
        s.register_recipient(store, "longy", "x" * 129, "Longy")
    assert s.register_recipient(store, "okay", "x" * 15, "Okay")["role"] == d.RECIPIENT


def test_c7_five_failures_cause_a_fifteen_minute_pause(store, clock):
    for _ in range(5):
        with pytest.raises(DomainError, match="incorrect"):
            s.login(store, "staff", "wrong password guess")
    with pytest.raises(DomainError, match="incorrect"):
        s.login(store, "staff", DEMO_PASSWORD)
    clock.forward(minutes=14, seconds=59)
    with pytest.raises(DomainError):
        s.login(store, "staff", DEMO_PASSWORD)
    clock.forward(seconds=1)
    assert s.login(store, "staff", DEMO_PASSWORD)["username"] == "staff"


def test_c7_sign_in_attempts_are_audited_without_the_password(store):
    with pytest.raises(DomainError):
        s.login(store, "staff", "my secret guess!")
    rows = store.reader().all("audit")
    assert rows[-1]["action"] == "Sign-in failed"
    assert "secret guess" not in str(rows)


# ---------------------------------------------------------------- M15 and NFR-09 sessions

def test_m15_session_survives_refresh_and_ends_when_idle(store, clock):
    token = s.start_session(store, user(store, "staff"))
    assert s.resume_session(store, token)[0]["username"] == "staff"  # a refresh
    clock.forward(minutes=10)
    assert s.resume_session(store, token)[0]  # still active, and the clock is reset
    clock.forward(minutes=d.SESSION_IDLE_MINUTES + 1)
    who, reason = s.resume_session(store, token)
    assert who is None and "without activity" in reason
    assert s.resume_session(store, token) == (None, None)  # the session row is gone


def test_sessions_end_on_sign_out_deactivation_and_after_eight_hours(store, clock):
    token = s.start_session(store, user(store, "staff"))
    s.end_session(store, token)
    assert s.resume_session(store, token)[0] is None
    vol_token = s.start_session(store, user(store, "volunteer"))
    s.deactivate_account(store, user(store, "manager"), user(store, "volunteer")["id"], True)
    assert s.resume_session(store, vol_token)[0] is None
    long_token = s.start_session(store, user(store, "staff"))
    for _ in range(d.SESSION_MAX_HOURS * 6 + 1):  # active every 10 minutes for 8 hours
        clock.forward(minutes=10)
        who, reason = s.resume_session(store, long_token)
        if not who:
            break
    assert who is None and "8 hours" in reason


def test_only_a_hash_of_the_session_token_is_stored(store):
    token = s.start_session(store, user(store, "staff"))
    assert token not in str(store.dump()["sessions"])


# ---------------------------------------------------------------- M6 and N11 past dates, bad times

def test_m6_past_dates_are_refused_for_new_bookings(store, clock):
    staff = user(store, "staff")
    with pytest.raises(DomainError, match="past"):
        s.schedule_donation(store, [{"item_type": "Rice", "quantity": 1}], "2020-01-01", "10:00")
    with pytest.raises(DomainError, match="past"):
        s.schedule_donation(store, [{"item_type": "Rice", "quantity": 1}], day(0), "09:00")
    with pytest.raises(DomainError, match="past"):
        s.create_allocation(store, staff, user(store, "recipient2")["id"],
                            [{"batch_id": 2, "quantity": 1}], day(-30), "10:00")
    with pytest.raises(DomainError, match="past"):
        s.update_pickup(store, staff, 1, day(-1), "10:00")
    with pytest.raises(DomainError, match="past"):
        s.assign_task(store, staff, user(store, "volunteer")["id"], "Receiving", day(-1),
                      "09:00", "")


def test_n11_drop_off_time_must_be_a_real_time(store):
    with pytest.raises(DomainError, match="HH:MM"):
        s.schedule_donation(store, [{"item_type": "Rice", "quantity": 1}], day(1), "banana")


# ---------------------------------------------------------------- M8 and M9 swap lifecycle

def test_m8_waiting_swaps_expire_when_the_pickup_window_ends(store, clock):
    alloc = today_pickup(store, "11:00")
    ravi, staff = user(store, "recipient2"), user(store, "staff")
    sw = s.request_swap(store, ravi, alloc["id"], 1, "")
    clock.forward(hours=1, minutes=16)  # 11:16, after the 15-minute window
    with pytest.raises(DomainError, match="Pending|passed"):
        s.approve_swap(store, staff, sw["id"], 1)
    assert s.list_swaps(store, ravi)[0]["status"] == d.EXPIRED  # saved, not just shown
    assert store.reader().get("swaps", sw["id"])["status"] == d.EXPIRED
    with pytest.raises(DomainError, match="Pending|passed"):
        s.request_swap(store, ravi, alloc["id"], 1, "")


def test_m9_collection_closes_waiting_swaps_as_closed_not_declined(store):
    ready_pickup(store)
    sw = s.request_swap(store, user(store, "recipient"), 1, 1, "")
    s.record_collection(store, user(store, "staff"), 1, {})
    swap = store.reader().get("swaps", sw["id"])
    assert swap["status"] == d.CLOSED and "collected" in swap["response"]


# ---------------------------------------------------------------- M11 collection date

def test_m11_collection_date_is_saved_and_checked(store, clock):
    ready_pickup(store)
    staff = user(store, "staff")
    with pytest.raises(DomainError, match="future"):
        s.record_collection(store, staff, 1, {}, day(1))
    with pytest.raises(DomainError, match="before"):
        s.record_collection(store, staff, 1, {}, "1999-01-01")
    dist = s.record_collection(store, staff, 1, {}, day(0))
    assert dist["collected_date"] == day(0)


def test_partial_collection_puts_the_rest_back(store):
    ready_pickup(store)
    staff = user(store, "staff")
    s.record_collection(store, staff, 1, {1: 1, 2: 1})  # took 1 rice of the 2 set aside
    rice = s.get_batch(store, staff, 1)
    assert rice["quantity"] == 19 and rice["reserved"] == 0 and rice["available"] == 19


# ---------------------------------------------------------------- M12 and N13 stock figures

def test_m12_low_stock_counts_available_food_not_food_on_the_shelf(store):
    staff = user(store, "staff")
    s.set_low_stock_threshold(store, staff, 5)
    s.create_allocation(store, staff, user(store, "recipient2")["id"],
                        [{"batch_id": 2, "quantity": 7}], day(1), "15:00")  # 12 on shelf, 5 left
    low = {x["name"]: x["quantity"] for x in s.stock_alerts(store, staff)["low_stock"]}
    assert low["Canned chickpeas"] == 5
    assert low["Yoghurt"] == 0  # fully expired: still listed, as 0, not hidden


def test_n13_dashboard_and_inventory_show_the_same_units(store):
    staff = user(store, "staff")
    assert s.dashboard_stats(store, staff)["units"] == s.usable_units(s.list_batches(store, staff))


def test_report_splits_expired_stock(store):
    report = s.build_report(store, user(store, "staff"), day(-1), day(0))
    yoghurt = next(x for x in report["stock"] if x["item"] == "Yoghurt")
    assert yoghurt == {"item": "Yoghurt", "quantity": 0, "expired": 10, "held": 0}
    assert "Yoghurt,0,10" in s.report_csv(report)


# ---------------------------------------------------------------- M13 stock corrections (FR-41, FR-42)

def test_m13_editing_a_batch_never_changes_its_quantity(store):
    staff = user(store, "staff")
    s.save_batch(store, staff, {"name": "Rice 1kg", "quantity": 999,
                                "expiry_date": day(200)}, 1)
    assert store.reader().get("batches", 1)["quantity"] == 20


def test_m13_corrections_need_a_reason_keep_history_and_respect_reservations(store):
    staff = user(store, "staff")
    with pytest.raises(DomainError, match="reason"):
        s.adjust_stock(store, staff, 1, -3, "")
    with pytest.raises(DomainError, match="cannot go below 2"):
        s.adjust_stock(store, staff, 1, -19, "Flood")
    fix = s.adjust_stock(store, staff, 1, -3, "Bags torn")
    assert store.reader().get("batches", 1)["quantity"] == 17
    undo = s.reverse_adjustment(store, staff, fix["id"], "Bags were fine")
    assert undo["reverses_id"] == fix["id"] and undo["change"] == 3
    assert store.reader().get("batches", 1)["quantity"] == 20
    with pytest.raises(DomainError, match="already"):
        s.reverse_adjustment(store, staff, fix["id"], "again")
    with pytest.raises(DomainError):
        s.reverse_adjustment(store, staff, undo["id"], "undo the undo")
    history = s.stock_history(store, staff, 1)
    assert [h["change"] for h in history] == [3, -3, 20]
    with pytest.raises(PermissionDenied):
        s.adjust_stock(store, user(store, "manager"), 1, 1, "x")


def test_stock_history_and_audit_cannot_be_edited_or_deleted(store):
    s.adjust_stock(store, user(store, "staff"), 1, 1, "Found one")
    conn = sqlite3.connect(store.path)
    for sql in ("UPDATE adjustments SET change = 50", "DELETE FROM adjustments",
                "UPDATE audit SET action = 'x'", "DELETE FROM audit"):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(sql)
    conn.close()


# ---------------------------------------------------------------- FR-16 safety holds

def test_held_food_cannot_be_set_aside_swapped_in_or_handed_out(store):
    ready_pickup(store)
    staff = user(store, "staff")
    with pytest.raises(DomainError, match="why"):
        s.save_batch(store, staff, {"name": "Rice 1kg", "expiry_date": day(200),
                                    "on_hold": True}, 1)
    s.save_batch(store, staff, {"name": "Rice 1kg", "expiry_date": day(200),
                                "on_hold": True, "hold_reason": "Recall notice"}, 1)
    ravi = user(store, "recipient2")
    with pytest.raises(DomainError, match="on hold"):
        s.create_allocation(store, staff, ravi["id"], [{"batch_id": 1, "quantity": 1}],
                            day(1), "10:00")
    assert 1 not in [b["id"] for b in s.suitable_batches(store, staff, ravi["id"])]
    with pytest.raises(DomainError, match="on hold"):  # Rina's rice is still set aside ...
        s.record_collection(store, staff, 1, {})
    assert s.get_batch(store, staff, 1)["reserved"] == 2  # ... and stays reserved
    sw = s.request_swap(store, ravi, 2, 1)
    assert 1 not in [b["id"] for b in s.get_swap(store, staff, sw["id"])["options"]]


# ---------------------------------------------------------------- check-in queue (FR-50 to FR-55)

def test_check_in_opens_an_hour_before_and_is_safe_to_repeat(store, clock):
    alloc = today_pickup(store, "11:30")
    ravi = user(store, "recipient2")
    assert s.queue_status(store, ravi, alloc["id"])["can_check_in"] is False  # 10:00
    with pytest.raises(DomainError, match="check in"):
        s.check_in(store, ravi, alloc["id"])
    clock.forward(minutes=30)  # 10:30
    first = s.check_in(store, ravi, alloc["id"])["checked_in_at"]
    clock.forward(minutes=5)
    assert s.check_in(store, ravi, alloc["id"])["checked_in_at"] == first
    with pytest.raises(PermissionDenied):
        s.check_in(store, user(store, "recipient"), alloc["id"])


def test_people_who_have_arrived_are_served_first_in_arrival_order(store, clock):
    early = today_pickup(store, "10:30", "recipient2", 2)
    late = today_pickup(store, "10:15", "recipient", 1)
    staff = user(store, "staff")
    s.check_in(store, user(store, "recipient2"), early["id"])
    order = [r["allocation_id"] for r in s.pickup_queue(store, staff, day(0))["queue"]]
    assert order == [early["id"], late["id"]]  # booked later, but here first
    s.move_in_queue(store, staff, early["id"], "serve")
    row = s.pickup_queue(store, staff, day(0))["queue"][0]
    assert row["state"] == d.SERVING and row["window_start"] is None and row["wait_min"] is None
    with pytest.raises(DomainError):
        s.move_in_queue(store, staff, late["id"], "serve")  # not checked in yet


def test_no_show_puts_the_food_back_and_sends_a_notice(store, clock):
    alloc = today_pickup(store, "11:00", qty=4)
    staff = user(store, "staff")
    assert s.get_batch(store, staff, 2)["available"] == 8
    with pytest.raises(DomainError):
        s.move_in_queue(store, staff, 1, "no_show")  # tomorrow's pickup: too early
    clock.forward(hours=1, minutes=15)
    s.move_in_queue(store, staff, alloc["id"], "no_show")
    assert store.reader().get("allocations", alloc["id"])["status"] == d.NO_SHOW
    assert s.get_batch(store, staff, 2)["available"] == 12
    assert s.list_notifications(store, user(store, "recipient2"))[0]["kind"] == "Missed pickup"


def test_paused_queue_hides_estimates_from_recipients(store):
    staff, ravi = user(store, "staff"), user(store, "recipient2")
    s.set_queue_settings(store, staff, 6, 15, paused=True)
    assert s.queue_status(store, ravi, 2)["paused"] is True
    s.set_queue_settings(store, staff, 6, 15, paused=False)
    assert s.queue_status(store, ravi, 2)["paused"] is False


# ---------------------------------------------------------------- audit log (FR-56, FR-57)

def test_audit_log_is_split_by_role_and_keeps_private_details_out(store):
    staff, rina = user(store, "staff"), user(store, "recipient")
    sw = s.request_swap(store, rina, 1, 1, "my child is allergic to gluten")
    s.decline_swap(store, staff, sw["id"], "Sorry, nothing suitable")
    s.adjust_stock(store, staff, 2, -1, "Dented tin")
    admin_rows = s.audit_events(store, user(store, "admin"))
    manager_rows = s.audit_events(store, user(store, "manager"))
    assert {r["category"] for r in admin_rows} == {d.SECURITY}
    assert {r["category"] for r in manager_rows} == {d.OPERATIONS}
    assert {"Swap declined", "Stock corrected"} <= {r["action"] for r in manager_rows}
    everything = str(store.dump()["audit"])
    assert "allergic" not in everything and "gluten" not in everything
    for name in ("volunteer", "recipient"):
        with pytest.raises(PermissionDenied):
            s.audit_events(store, user(store, name))


# ---------------------------------------------------------------- IT Admin bootstrap and recovery

def test_admin_bootstrap_only_when_there_is_no_admin(store, tmp_path):
    with pytest.raises(DomainError, match="already"):
        s.bootstrap_admin(store, "admin2", NEW_PASSWORD, "Second admin")
    empty = SqliteStore(str(tmp_path / "empty.sqlite3"))
    s.bootstrap_admin(empty, "first", NEW_PASSWORD, "First admin")
    assert s.login(empty, "first", NEW_PASSWORD)["role"] == d.ADMIN


def test_admin_recovery_resets_the_pause_and_ends_old_sessions(store, clock):
    token = s.start_session(store, user(store, "admin"))
    for _ in range(d.FREE_LOGIN_ATTEMPTS + 1):
        with pytest.raises(DomainError):
            s.login(store, "admin", "forgot my password")
    s.recover_admin(store, "admin", NEW_PASSWORD)
    assert s.resume_session(store, token)[0] is None
    assert s.login(store, "admin", NEW_PASSWORD)["role"] == d.ADMIN
    with pytest.raises(DomainError):
        s.recover_admin(store, "staff", NEW_PASSWORD)  # only IT Admin accounts


# ---------------------------------------------------------------- M14 backup and restore (NFR-04)

def test_m14_backup_and_restore_bring_back_every_record(store, tmp_path, monkeypatch):
    monkeypatch.setattr(manage, "APP_DIR", str(tmp_path))
    before = store.dump()
    copy = manage.backup(str(tmp_path / "copy.sqlite3"))
    s.adjust_stock(store, user(store, "staff"), 1, -5, "Mistake to be undone by restore")
    manage.restore(copy)
    after = SqliteStore(store.path).dump()
    assert after["batches"] == before["batches"]
    assert len(after["adjustments"]) == len(before["adjustments"])


def test_restore_refuses_a_file_that_is_not_a_database(store, tmp_path):
    junk = tmp_path / "junk.sqlite3"
    junk.write_text("not a database")
    with pytest.raises(SystemExit):
        manage.restore(str(junk))


# ---------------------------------------------------------------- feedback (FR-48, FR-49)

def test_feedback_can_be_archived_and_old_feedback_is_removed(store, clock):
    staff = user(store, "staff")
    s.mark_feedback_reviewed(store, staff, 1, archive=True)
    inbox = s.feedback_inbox(store, staff)
    assert inbox["total"] == 2 and inbox["archived"] == 1
    assert "nobody made me feel awkward" not in str(store.dump()["audit"])
    clock.forward(days=d.FEEDBACK_KEEP_DAYS + 1)
    assert s.delete_old_feedback(store) == 3
    assert store.reader().all("feedback") == []


# ---------------------------------------------------------------- N12 typed text shown as typed

def test_n12_markdown_in_typed_text_is_escaped():
    assert esc("[win](http://x.y)") == r"\[win\]\(http\://x\.y\)"
    assert esc(":red[big]") == r"\:red\[big\]"
    assert esc(None) == ""


# ---------------------------------------------------------------- storage behaviour

def test_rows_changed_earlier_in_a_save_are_seen_by_later_queries(store):
    with store.transaction() as tx:
        tx.get("allocations", 1)["status"] = d.CANCELLED
        assert [a["id"] for a in tx.find("allocations", status=d.ALLOCATED)] == [2]
        assert tx.find_one("allocations", id=1) is tx.get("allocations", 1)
    assert store.reader().get("allocations", 1)["status"] == d.CANCELLED


def test_unknown_columns_are_refused_instead_of_silently_lost(store):
    with pytest.raises(ValueError):
        with store.transaction() as tx:
            tx.get("batches", 1)["colour"] = "red"
    assert "colour" not in store.reader().get("batches", 1)


def test_edit_conflict_on_batch_details(store):
    staff = user(store, "staff")
    version = store.reader().get("batches", 1)["version"]
    s.adjust_stock(store, staff, 1, 1, "Found one")  # someone else changes it
    with pytest.raises(EditConflict):
        s.save_batch(store, staff, {"name": "Rice", "expiry_date": day(100),
                                    "loaded_version": version}, 1)
