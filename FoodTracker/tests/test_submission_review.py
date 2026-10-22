"""Regression evidence for the final review. Expected behavior comes from the SRS
and documented prototype policies, not calculated from implementation internals.
"""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest
from streamlit.testing.v1 import AppTest

import manage
from foodshare import domain as d, services as s
from foodshare.domain import DomainError, PermissionDenied
from foodshare.storage import SqliteStore
from conftest import user, send_feedback, ready_pickup


@pytest.fixture
def fixed_clock(monkeypatch):
    value = [datetime(2026, 10, 21, 10)]
    monkeypatch.setattr(d, 'now', lambda: value[0])
    monkeypatch.setattr(d, 'today', lambda: value[0].date())
    return value


@pytest.mark.parametrize('minutes', [15, 16])
def test_passive_session_checks_expire_without_renewal(store, fixed_clock, minutes):
    token = s.start_session(store, user(store, 'recipient'))
    fixed_clock[0] += timedelta(minutes=10)
    assert s.resume_session(store, token, touch=False)[0]
    fixed_clock[0] += timedelta(minutes=minutes - 10)
    who, reason = s.resume_session(store, token, touch=False)
    assert who is None and 'without activity' in reason
    assert s.resume_session(store, token) == (None, None)


def test_absolute_session_limit_is_inclusive(store, fixed_clock):
    token = s.start_session(store, user(store, 'staff'))
    for _ in range(47):
        fixed_clock[0] += timedelta(minutes=10)
        assert s.resume_session(store, token)[0]
    fixed_clock[0] += timedelta(minutes=10)
    who, reason = s.resume_session(store, token)
    assert who is None and '8 hours' in reason


def test_live_queue_card_rejects_an_expired_session(store, fixed_clock):
    person = user(store, 'recipient')
    token = s.start_session(store, person)
    fixed_clock[0] += timedelta(minutes=15)
    at = AppTest.from_string('from foodshare.views.common import live_queue_card\nlive_queue_card(1)',
                             default_timeout=30)
    at.session_state['session_token'] = token
    at.session_state['user_id'] = person['id']
    at.run()
    assert not at.exception
    assert any('session has ended' in x.value for x in at.info)
    assert not at.button
    assert 'user_id' not in at.session_state


def test_inactive_account_cannot_start_a_new_session(store):
    person = user(store, 'recipient')
    s.deactivate_account(store, user(store, 'staff'), person['id'], True, 'Verified in person')
    with pytest.raises(PermissionDenied):
        s.start_session(store, person)


@pytest.mark.parametrize('operation', [
    lambda db, a: s.list_allocations(db, a),
    lambda db, a: s.get_allocation(db, a, 1),
    lambda db, a: s.get_profile(db, a, a['id']),
    lambda db, a: s.list_swaps(db, a),
    lambda db, a: s.queue_status(db, a, 1),
    lambda db, a: s.check_in(db, a, 1),
    lambda db, a: s.mark_notifications_read(db, a),
])
def test_inactive_actor_cannot_use_recipient_shortcuts(store, operation):
    actor = dict(user(store, 'recipient'), active=False)
    with pytest.raises(PermissionDenied):
        operation(store, actor)


def test_recipient_filter_does_not_bypass_volunteer_shift_scope(store):
    volunteer, recipient = user(store, 'volunteer'), user(store, 'recipient')
    assert s.list_allocations(store, volunteer, recipient_id=recipient['id']) == []


@pytest.mark.parametrize('value', [1.5, True, '2.5', 'NaN', float('inf')])
def test_non_integer_quantities_are_rejected_without_saving(store, value):
    before = store.dump()
    with pytest.raises(DomainError, match='whole number'):
        s.schedule_donation(store, [{'item_type': 'Rice', 'quantity': value}],
                            (d.today() + timedelta(days=1)).isoformat(), '10:00')
    assert store.dump() == before


@pytest.mark.parametrize('value', [1.5, False, '-2.5'])
def test_non_integer_stock_corrections_are_rejected(store, value):
    staff = user(store, 'staff')
    before = store.dump()
    with pytest.raises(DomainError, match='whole number'):
        s.adjust_stock(store, staff, 1, value, 'Recount')
    assert store.dump() == before


@pytest.mark.parametrize('value', ['10:00junk', '10:00:30', '24:00', '10:7'])
def test_invalid_time_suffixes_and_boundaries_are_rejected(value):
    with pytest.raises(DomainError):
        d.parse_time(value)


def test_site_clock_uses_kuala_lumpur_even_on_a_utc_server(monkeypatch):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 21, 17, 30, tzinfo=timezone.utc).astimezone(tz)
    monkeypatch.setattr(d, 'datetime', FixedDateTime)
    assert d.now() == datetime(2026, 10, 22, 1, 30)
    assert d.today().isoformat() == '2026-10-22'


def test_feedback_review_audit_has_no_feedback_link(store):
    staff = user(store, 'staff')
    item = send_feedback(store, 4, 'General', 'Private feedback message')
    s.mark_feedback_reviewed(store, staff, item['id'])
    event = store.dump()['audit'][-1]
    assert event['action'] == 'Feedback reviewed' and event['actor_id'] == staff['id']
    assert event['target'] == '' and event['details'] == {}
    assert 'Private feedback message' not in str(event)


def test_reader_snapshot_is_consistent_and_connection_is_closed(store):
    with store.reader() as reader:
        assert reader.get('batches', 1)['quantity'] == 20
        with store.transaction() as writer:
            writer.get('batches', 1)['quantity'] = 19
        assert reader.get('batches', 2)['quantity'] == 12
        assert reader.find_one('batches', id=1)['quantity'] == 20
    with pytest.raises(sqlite3.ProgrammingError):
        reader.conn.execute('SELECT 1')
    with store.reader() as reader:
        assert reader.get('batches', 1)['quantity'] == 19
        with pytest.raises(sqlite3.OperationalError):
            reader.conn.execute('DELETE FROM sessions')


@pytest.mark.parametrize('kind', ['missing', 'users_only', 'future', 'bad_json'])
def test_restore_rejects_invalid_backups_without_changing_live_data(store, tmp_path, kind):
    before = store.dump()
    source = tmp_path / (kind + '.sqlite3')
    if kind == 'users_only':
        with sqlite3.connect(source) as conn:
            conn.execute('CREATE TABLE users (id INTEGER PRIMARY KEY)')
    elif kind in ('future', 'bad_json'):
        store.backup(str(source))
        with sqlite3.connect(source) as conn:
            if kind == 'future':
                conn.execute('PRAGMA user_version=999')
            else:
                conn.execute("UPDATE batches SET allergens='not json' WHERE id=1")
    with pytest.raises(SystemExit):
        manage.restore(str(source))
    assert store.dump() == before
    if kind == 'missing':
        assert not source.exists()


def test_backup_and_restore_reject_the_live_path(store):
    with pytest.raises(ValueError):
        store.backup(store.path)
    with pytest.raises(SystemExit):
        manage.restore(store.path)


def test_future_schema_is_not_downgraded(tmp_path):
    path = tmp_path / 'future.sqlite3'
    with sqlite3.connect(path) as conn:
        conn.execute('PRAGMA user_version=999')
    with pytest.raises(ValueError, match='newer'):
        SqliteStore(str(path))
    with sqlite3.connect(path) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 999


def test_check_in_rejects_closed_window_and_pause(store, monkeypatch):
    staff, recipient = user(store, 'staff'), user(store, 'recipient2')
    tomorrow = d.today() + timedelta(days=1)
    fixed = [datetime.combine(tomorrow, datetime.min.time()).replace(hour=10)]
    monkeypatch.setattr(d, 'now', lambda: fixed[0])
    monkeypatch.setattr(d, 'today', lambda: fixed[0].date())
    allocation = s.create_allocation(store, staff, recipient['id'],
                                    [{'batch_id': 2, 'quantity': 1}], tomorrow.isoformat(), '10:00')
    s.set_queue_settings(store, staff, 6, 15, paused=True)
    assert not s.queue_status(store, recipient, allocation['id'])['can_check_in']
    with pytest.raises(DomainError, match='paused'):
        s.check_in(store, recipient, allocation['id'])
    s.set_queue_settings(store, staff, 6, 15, paused=False)
    fixed[0] += timedelta(minutes=15)
    assert not s.queue_status(store, recipient, allocation['id'])['can_check_in']
    with pytest.raises(DomainError, match='window has ended'):
        s.check_in(store, recipient, allocation['id'])


def test_single_desk_cannot_serve_two_pickups_at_once(store, monkeypatch):
    staff = user(store, 'staff')
    tomorrow = d.today() + timedelta(days=1)
    fixed = datetime.combine(tomorrow, datetime.min.time()).replace(hour=14)
    monkeypatch.setattr(d, 'now', lambda: fixed)
    monkeypatch.setattr(d, 'today', lambda: fixed.date())
    s.check_in(store, staff, 1)
    s.check_in(store, staff, 2)
    s.move_in_queue(store, staff, 1, 'serve')
    with pytest.raises(DomainError, match='already serving'):
        s.move_in_queue(store, staff, 2, 'serve')
    assert s.get_allocation(store, staff, 2)['queue_state'] == d.WAITING


def test_fifty_rounds_of_two_connection_stock_collection_and_swap_contention(store):
    """50 rounds x 3 synchronized races = 150 races, not 150 pytest cases.
    Both connections target the same on-disk database. Each round checks all
    stock invariants, single completion, current swap state and report totals.
    """
    staff, recipient = user(store, 'staff'), user(store, 'recipient')
    other = SqliteStore(store.path)
    tomorrow = (d.today() + timedelta(days=1)).isoformat()

    def race(operation):
        barrier = Barrier(2)
        def run(db):
            barrier.wait(timeout=15)
            try:
                return operation(db)
            except DomainError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(run, (store, other)))

    for round_id in range(50):
        def batch(name):
            return s.save_batch(store, staff, {'name': f'{name} {round_id}', 'quantity': 1, 'allergens_confirmed': True,
                                'expiry_date': tomorrow, 'dietary_tags': 'halal'})['id']
        original, replacement = batch('Original'), batch('Replacement')
        allocations = race(lambda db: s.create_allocation(db, staff, recipient['id'],
                             [{'batch_id': original, 'quantity': 1}], tomorrow, '14:00'))
        assert sum(x is not None for x in allocations) == 1, f'oversell round {round_id}'
        allocation = next(x for x in allocations if x is not None)
        swap = s.request_swap(store, recipient, allocation['id'], 1)
        decisions = race(lambda db: s.approve_swap(db, staff, swap['id'], replacement))
        assert sum(x is not None for x in decisions) == 1, f'stale decision round {round_id}'
        ready_pickup(store, allocation['id'])
        issued = race(lambda db: s.record_collection(db, staff, allocation['id'], {}))
        assert sum(x is not None for x in issued) == 1, f'double collection round {round_id}'
        rows = s.list_batches(store, staff)
        assert all(0 <= b['reserved'] <= b['quantity'] for b in rows), f'stock round {round_id}'
        report = s.build_report(store, staff, d.today().isoformat(), tomorrow)
        actual = sum(i['quantity'] for x in store.dump()['distributions'] for i in x['items'])
        assert report['total_distributed'] == actual == round_id + 1


@pytest.mark.parametrize('scenario,expiry_offset,held,allergens,quantity,allowed', [
    ('baseline', 30, False, '', 1, True),
    ('expired only', -1, False, '', 1, False),
    ('held only', 30, True, '', 1, False),
    ('allergy only', 30, False, 'peanut', 1, False),
    ('shortage only', 30, False, '', 2, False),
])
def test_allocation_safety_decisions_change_independently(
        store, scenario, expiry_offset, held, allergens, quantity, allowed):
    """Decision table: each negative row changes one condition from the baseline.
    This is a focused MC/DC-style demonstration, not whole-program coverage.
    """
    staff, recipient = user(store, 'staff'), user(store, 'recipient')
    batch = s.save_batch(store, staff, {'name': scenario, 'quantity': 1,
                'expiry_date': (d.today() + timedelta(days=expiry_offset)).isoformat(),
                'on_hold': held, 'hold_reason': 'Safety check' if held else '',
                'allergens_confirmed': True, 'allergens': allergens, 'dietary_tags': 'halal'})
    before = store.dump()
    def allocate():
        return s.create_allocation(store, staff, recipient['id'],
                  [{'batch_id': batch['id'], 'quantity': quantity}],
                  (d.today() + timedelta(days=1)).isoformat(), '14:00')
    if allowed:
        assert allocate()['status'] == d.ALLOCATED
    else:
        with pytest.raises(DomainError):
            allocate()
        after = store.dump()
        for table in before:
            if table != "audit":
                assert after[table] == before[table], scenario
        if scenario in ("expired only", "held only"):
            assert after["audit"][-1]["result"] == "Denied"
        else:
            assert after["audit"] == before["audit"]
