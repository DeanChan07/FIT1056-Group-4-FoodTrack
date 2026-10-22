"""Review regressions and SRS boundary cases. Expected outcomes are policy decisions.

Every case uses an isolated database and a Malaysia-local business clock. No real
participant, browser usability or deployment certification is implied by pytest.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta
from threading import Barrier
import csv
import io
import sqlite3

import pytest

from foodshare import domain as d, services as s
from foodshare.domain import DomainError, PermissionDenied, EditConflict
from foodshare.storage import SqliteStore
from foodshare.services import public_controls as pc
from seed import seed, DEMO_PASSWORD


@pytest.fixture
def env(tmp_path, monkeypatch):
    clock = [datetime(2026, 10, 22, 10)]
    monkeypatch.setattr(d, 'now', lambda: clock[0])
    db = seed(str(tmp_path/'regressions.sqlite3'), today_pickup=None)
    actors = {name: s.login(db, name, DEMO_PASSWORD)
              for name in ('staff', 'volunteer', 'recipient', 'recipient2', 'manager', 'admin')}
    return db, actors, clock


def allocation(env, batch=2, quantity=1, recipient='recipient2'):
    db, actors, _ = env
    return s.create_allocation(db, actors['staff'], actors[recipient]['id'],
             [{'batch_id': batch, 'quantity': quantity}], d.today().isoformat(), '10:00')


def state(db, *tables):
    data = db.dump()
    return {name: data[name] for name in tables}


def test_latest_allergy_blocks_collection_without_partial_stock_changes(env):
    db, a, clock = env
    pickup = allocation(env, batch=5)
    s.save_profile(db, a['recipient2'], a['recipient2']['id'],
                   {'household_size': 1, 'allergies': 'wheat', 'allergies_confirmed': True})
    before = state(db, 'batches', 'allocations', 'distributions', 'adjustments')
    with pytest.raises(DomainError, match='contains wheat'):
        s.record_collection(db, a['staff'], pickup['id'], {})
    assert state(db, *before) == before


@pytest.mark.parametrize('field,value', [('allergies_confirmed', False), ('dietary_restrictions', ['vegan']),
                                         ('cultural_needs', ['kosher'])])
def test_latest_unknown_or_dietary_needs_block_collection(env, field, value):
    db, a, _ = env
    pickup = allocation(env)
    with db.transaction() as tx:
        tx.find_one('profiles', recipient_id=a['recipient2']['id'])[field] = value
    with pytest.raises(DomainError, match='not suitable'):
        s.record_collection(db, a['staff'], pickup['id'], {})
    assert db.dump()['distributions'] == []


def test_receipt_records_stock_history_atomically_and_repeat_is_rejected(env):
    db, a, _ = env
    donation = s.schedule_donation(db, [{'item_type': 'Oats', 'quantity': 5}],
                                  '2026-10-23', '10:00')
    accepted = [{'accepted_qty': 5, 'expiry_date': '2026-11-23', 'allergens_confirmed': True}]
    received = s.receive_donation(db, a['staff'], donation['reference'], accepted)
    batch_id = received['items'][0]['batch_id']
    history = s.stock_history(db, a['staff'], batch_id)
    assert len(history) == 1
    assert (history[0]['change'], history[0]['before_quantity'], history[0]['after_quantity']) == (5, 0, 5)
    assert history[0]['source_id'] == donation['id']
    before = state(db, 'batches', 'donations', 'adjustments')
    with pytest.raises(DomainError, match='already'):
        s.receive_donation(db, a['staff'], donation['reference'], accepted)
    assert state(db, *before) == before


def test_failed_receipt_rolls_back_batch_and_history(env, monkeypatch):
    from foodshare.storage import Tx
    db, a, _ = env
    original = Tx.insert
    def broken(self, table, record):
        if table == 'adjustments':
            raise RuntimeError('injected history failure')
        return original(self, table, record)
    before = state(db, 'donations', 'batches', 'adjustments', 'audit')
    monkeypatch.setattr(Tx, 'insert', broken)
    with pytest.raises(RuntimeError):
        s.receive_donation(db, a['staff'], 'DN-DEMO01', [
            {'accepted_qty': 1, 'expiry_date': '2026-11-23'}, {'accepted_qty': 0}])
    assert state(db, *before) == before


def test_deactivation_cancels_reservations_swaps_notices_and_sessions(env):
    db, a, _ = env
    pickup = allocation(env)
    swap = s.request_swap(db, a['recipient2'], pickup['id'], 1)
    token = s.start_session(db, a['recipient2'])
    s.check_in(db, a['staff'], pickup['id'])
    s.deactivate_account(db, a['staff'], a['recipient2']['id'], True, 'ID checked in person')
    after = db.dump()
    assert all(x['status'] == d.CANCELLED for x in after['allocations']
               if x['recipient_id'] == a['recipient2']['id'])
    assert next(x for x in after['swaps'] if x['id'] == swap['id'])['status'] == d.CANCELLED
    assert s.resume_session(db, token)[0] is None
    assert s.get_batch(db, a['staff'], 2)['reserved'] == 0
    assert after['queue_entries'][-1]['state'] == d.CANCELLED
    assert 'ID checked in person' not in str(after)
    assert s.deactivate_account(db, a['staff'], a['recipient2']['id'], True, 'Verified')['active'] is False


def test_overdue_release_is_idempotent_and_does_not_touch_collected_stock(env):
    db, a, clock = env
    late = allocation(env)
    swap = s.request_swap(db, a['recipient2'], late['id'], 1)
    before = s.get_batch(db, a['staff'], 2)['quantity']
    clock[0] += timedelta(days=1)
    assert s.expire_overdue_allocations(db) == 1
    assert s.expire_overdue_allocations(db) == 0
    assert s.get_batch(db, a['staff'], 2)['quantity'] == before
    assert s.get_batch(db, a['staff'], 2)['reserved'] == 0
    assert s.get_allocation(db, a['staff'], late['id'])['status'] == d.EXPIRED
    assert next(x for x in db.dump()['swaps'] if x['id'] == swap['id'])['status'] == d.EXPIRED
    with pytest.raises(DomainError):
        s.record_collection(db, a['staff'], late['id'], {}, exception_reason='Late arrival')


def test_late_staff_exception_still_allows_only_one_collection(env):
    db, a, clock = env
    pickup = allocation(env)
    clock[0] += timedelta(minutes=16)
    with pytest.raises(DomainError, match='window has ended'):
        s.check_in(db, a['recipient2'], pickup['id'])
    with pytest.raises(DomainError):
        s.check_in(db, a['staff'], pickup['id'])
    with pytest.raises(DomainError):
        s.record_collection(db, a['staff'], pickup['id'], {})
    s.check_in(db, a['staff'], pickup['id'], exception_reason='Transport delay')
    s.check_in(db, a['staff'], pickup['id'], exception_reason='Transport delay')
    assert len(db.dump()['queue_entries']) == 1
    s.record_collection(db, a['staff'], pickup['id'], {})
    before = state(db, 'batches', 'distributions')
    with pytest.raises(DomainError, match='already collected'):
        s.record_collection(db, a['staff'], pickup['id'], {}, exception_reason='Transport delay')
    assert state(db, *before) == before
    assert db.dump()['queue_entries'][0]['state'] == 'Completed'


def test_late_exception_never_bypasses_food_safety(env):
    db, a, clock = env
    pickup = allocation(env)
    clock[0] += timedelta(minutes=16)
    with db.transaction() as tx:
        tx.get('batches', 2)['on_hold'] = True
    with pytest.raises(DomainError, match='on hold'):
        s.record_collection(db, a['staff'], pickup['id'], {}, exception_reason='Transport delay')
    assert db.dump()['distributions'] == []


def test_two_connections_cannot_double_issue_a_late_exception(env):
    db, a, clock = env
    pickup = allocation(env)
    clock[0] += timedelta(minutes=16)
    barrier = Barrier(2)
    def issue(_):
        barrier.wait(timeout=10)
        try:
            s.record_collection(SqliteStore(db.path), a['staff'], pickup['id'], {}, exception_reason='Transport delay')
            return True
        except DomainError:
            return False
    with ThreadPoolExecutor(2) as pool:
        assert list(pool.map(issue, range(2))).count(True) == 1
    assert len(db.dump()['distributions']) == 1
    assert s.get_batch(db, a['staff'], 2)['quantity'] == 11


@pytest.mark.parametrize('value', ['=1+1', '+SUM(A1)', '-1+2', '@SUM(A1)', '\t=1', '\r=1', '\n=1', '  =1', '\ufeff=1'])
def test_csv_neutralizes_formula_text_without_changing_numeric_cells(value):
    report = {'start': '2026-10-22', 'end': '2026-10-22', 'rows': [
        {'type':value,'date':'2026-10-22','reference':value,'item':value,'quantity':2}],
        'total_donated':2,'total_distributed':0,'stock':[{'item':value,'quantity':2,'expired':0,'held':0}]}
    rows = list(csv.reader(io.StringIO(s.report_csv(report))))
    row = rows[3]
    assert row[0] == row[2] == row[3] == "'"+value
    assert row[4] == '2'
    assert rows[-1][0] == "'"+value


@pytest.mark.parametrize('word', ['peanut', 'peanuts', 'groundnut', 'groundnuts', 'Peanuts'])
def test_allergen_aliases_match(env, word):
    db, a, _ = env
    with db.transaction() as tx:
        tx.get('batches', 3)['allergens'] = [word]
    with pytest.raises(DomainError, match='contains peanut'):
        s.create_allocation(db, a['staff'], a['recipient']['id'],
                           [{'batch_id':3,'quantity':1}], '2026-10-22','10:00')


@pytest.mark.parametrize('table,key', [('batches','allergens_confirmed'),('profiles','allergies_confirmed')])
def test_unknown_allergen_info_is_not_treated_as_none(env, table, key):
    db,a,_ = env
    with db.transaction() as tx:
        row = tx.get('batches',2) if table == 'batches' else tx.find_one('profiles', recipient_id=a['recipient2']['id'])
        row[key] = False
    with pytest.raises(DomainError,match='confirmation'):
        allocation(env)


def test_cancelled_task_removes_receiving_and_distribution_authority(env):
    db,a,_ = env
    pickup = allocation(env)
    tasks = s.list_tasks(db,a['volunteer'])
    distribution = next(t for t in tasks if t['task_type']=='Distribution')
    receiving = next(t for t in tasks if t['task_type']=='Receiving')
    s.cancel_task(db,a['manager'],distribution['id'],'Shift changed',True)
    s.cancel_task(db,a['staff'],receiving['id'],'Shift changed',True)
    assert s.list_allocations(db,a['volunteer'],recipient_id=a['recipient2']['id']) == []
    with pytest.raises(PermissionDenied): s.check_in(db,a['volunteer'],pickup['id'])
    with pytest.raises(PermissionDenied): s.record_collection(db,a['volunteer'],pickup['id'],{})
    with pytest.raises(PermissionDenied): s.receive_donation(db,a['volunteer'],'DN-DEMO01',[])


def test_task_edit_conflict_permissions_and_cancellation(env):
    db,a,_=env
    task=s.list_tasks(db,a['staff'])[0]
    changed=s.update_task(db,a['staff'],task['id'],a['volunteer']['id'],'Receiving','2026-10-23','11:00','New instructions',loaded_version=0)
    assert changed['version']==1
    with pytest.raises(EditConflict):
        s.update_task(db,a['staff'],task['id'],a['volunteer']['id'],'Receiving','2026-10-23','12:00','Stale',loaded_version=0)
    with pytest.raises(PermissionDenied): s.cancel_task(db,a['volunteer'],task['id'],'No',True)
    with pytest.raises(DomainError): s.cancel_task(db,a['staff'],task['id'],'Changed',False)
    assert s.cancel_task(db,a['staff'],task['id'],'Changed',True)['status']==d.CANCELLED


def test_admin_management_requires_reauthentication_and_keeps_last_admin(env):
    db,a,_=env
    with pytest.raises(PermissionDenied):
        s.create_internal_account(db,a['admin'],'admin2',DEMO_PASSWORD,'Second',d.ADMIN)
    second=s.create_internal_account(db,a['admin'],'admin2',DEMO_PASSWORD,'Second',d.ADMIN,
                                    current_password=DEMO_PASSWORD,confirmed=True)
    token=s.start_session(db,second)
    s.update_account(db,a['admin'],second['id'],'Renamed',current_password=DEMO_PASSWORD,confirmed=True)
    s.deactivate_account(db,a['admin'],second['id'],True,current_password=DEMO_PASSWORD)
    assert s.resume_session(db,token)[0] is None
    with pytest.raises(DomainError,match='last active'):
        s.deactivate_account(db,a['admin'],a['admin']['id'],True,current_password=DEMO_PASSWORD)
    with pytest.raises(PermissionDenied):
        s.create_internal_account(db,a['manager'],'admin3',DEMO_PASSWORD,'No',d.ADMIN,
                                  current_password=DEMO_PASSWORD,confirmed=True)


def test_queue_wait_formula_and_volunteer_transitions(env):
    db,a,_=env
    first=allocation(env)
    second=allocation(env)
    assert s.queue_status(db,a['recipient2'],second['id'])['position'] is None
    s.check_in(db,a['volunteer'],first['id'])
    s.check_in(db,a['volunteer'],second['id'])
    q=s.queue_status(db,a['recipient2'],second['id'])
    assert (q['position'],q['ahead'],q['wait_min'],q['wait_max'])==(2,1,5,10)
    assert not {'recipient_id','recipient_name','allocation_id','queue'} & q.keys()
    s.move_in_queue(db,a['volunteer'],first['id'],'serve')
    assert s.queue_status(db,a['recipient2'],first['id'])['wait_min'] is None
    with pytest.raises(PermissionDenied): s.move_in_queue(db,a['volunteer'],second['id'],'no_show')
    s.record_collection(db,a['volunteer'],first['id'],{})
    q=s.queue_status(db,a['recipient2'],second['id'])
    assert (q['position'],q['wait_min'],q['wait_max'])==(1,0,5)
    s.set_queue_settings(db,a['manager'],5,15,True)
    q=s.queue_status(db,a['recipient2'],second['id'])
    assert q['wait_min'] is q['wait_max'] is q['window_start'] is None


def test_feedback_replay_rate_window_and_exact_storage_schema(env,monkeypatch):
    db,_,_=env
    moment=[100.0]
    monkeypatch.setattr(pc.time,'monotonic',lambda:moment[0])
    browser,form=s.feedback_form()
    first=s.submit_feedback(db,'  Respectful message  ',browser_token=browser,form_token=form)
    assert set(first)=={'id','message','submitted_on','reviewed','archived'}
    assert first['message']=='Respectful message'
    with pytest.raises(DomainError): s.submit_feedback(db,'Replay',browser_token=browser,form_token=form)
    for _ in range(4):
        browser,form=s.feedback_form(browser)
        s.submit_feedback(db,'Message',browser_token=browser,form_token=form)
    browser,form=s.feedback_form(browser)
    with pytest.raises(DomainError,match='ten minutes'):
        s.submit_feedback(db,'Sixth',browser_token=browser,form_token=form)
    moment[0]+=600
    with pytest.raises(DomainError): s.submit_feedback(db,'Expired',browser_token=browser,form_token=form)
    browser,form=s.feedback_form(browser)
    assert s.submit_feedback(db,'New window',browser_token=browser,form_token=form)


@pytest.mark.parametrize('message,accepted',[('',False),(' '*3,False),('x',True),('你'*500,True),('x'*501,False)])
def test_feedback_unicode_boundaries(env,message,accepted):
    db,_,_=env
    browser,form=s.feedback_form()
    if accepted:
        assert s.submit_feedback(db,message,browser_token=browser,form_token=form)['message']==message.strip()
    else:
        with pytest.raises(DomainError): s.submit_feedback(db,message,browser_token=browser,form_token=form)


def test_maintenance_deletes_only_old_feedback_and_invalid_sessions(env):
    db,a,clock=env
    token=s.start_session(db,a['recipient'])
    with db.transaction() as tx:
        for age in (89,90,91):
            tx.insert('feedback',{'message':str(age),'submitted_on':(d.today()-timedelta(days=age)).isoformat(),
                                 'reviewed':False,'archived':False})
    clock[0]+=timedelta(minutes=15)
    result=s.run_maintenance(db,force=True)
    assert result['feedback']==1 and result['sessions']==1
    assert not any(f['message']=='91' for f in db.dump()['feedback'])
    assert any(f['message']=='90' for f in db.dump()['feedback'])
    assert s.resume_session(db,token)[0] is None
    assert s.run_maintenance(db,force=True)['sessions']==0


def test_passive_session_checks_do_not_acquire_writer_lock(env,monkeypatch):
    db,a,_=env
    token=s.start_session(db,a['staff'])
    @contextmanager
    def forbidden():
        raise AssertionError('read-only session validation requested a writer')
        yield
    monkeypatch.setattr(db,'transaction',forbidden)
    assert s.resume_session(db,token,touch=False)[0]['id']==a['staff']['id']
    assert s.resume_session(db,token)[0]['id']==a['staff']['id']


def test_individual_item_thresholds_and_held_report_stock(env):
    db,a,_=env
    s.set_low_stock_threshold(db,a['manager'],100,'Rice 1kg')
    assert any(x['name']=='Rice 1kg' for x in s.stock_alerts(db,a['staff'])['low_stock'])
    with db.transaction() as tx: tx.get('batches',1)['on_hold']=True
    report=s.build_report(db,a['staff'],'2026-10-22','2026-10-22')
    rice=next(x for x in report['stock'] if x['item']=='Rice 1kg')
    assert rice['quantity']==0 and rice['held']==20


def test_swap_replacement_quantity_and_stale_version(env):
    db,a,_=env
    pickup=allocation(env)
    request=s.request_swap(db,a['recipient2'],pickup['id'],1)
    with pytest.raises(EditConflict):
        s.approve_swap(db,a['staff'],request['id'],1,2,loaded_version=0)
    s.approve_swap(db,a['staff'],request['id'],1,2,loaded_version=1)
    assert s.get_allocation(db,a['staff'],pickup['id'])['items'][0]['quantity']==2
    assert s.get_batch(db,a['staff'],1)['quantity']==20


def test_cookie_exchange_uses_httponly_csrf_and_one_use_handle(env):
    import asyncio
    import json
    from http.cookies import SimpleCookie
    from starlette.applications import Starlette
    from foodshare.http_security import routes, cookie_handoff
    db, a, _ = env
    token = s.start_session(db, a['staff'])
    app = Starlette(routes=routes())
    def request(path, body='', headers=None, method='POST'):
        messages=[]
        scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':method,
               'scheme':'https','path':path,'raw_path':path.encode(),'query_string':b'',
               'root_path':'','server':('foodshare.test',443),'client':('127.0.0.1',123),
               'headers':[(b'host',b'foodshare.test')]+[(k.lower().encode(),v.encode()) for k,v in (headers or {}).items()]}
        async def receive(): return {'type':'http.request','body':body.encode(),'more_body':False}
        async def send(message): messages.append(message)
        asyncio.run(app(scope,receive,send))
        head=next(m for m in messages if m['type']=='http.response.start')
        content=b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body')
        return head['status'], dict(head['headers']), content
    handle=cookie_handoff(token)
    status,headers,body=request('/foodshare/csrf',method='GET')
    csrf=json.loads(body)['token']
    jar=SimpleCookie(); jar.load(headers[b'set-cookie'].decode())
    cookie='foodshare_csrf='+jar['foodshare_csrf'].value
    assert request('/foodshare/session',handle)[0]==403
    assert request('/foodshare/session',handle,{'Origin':'https://evil.test','Cookie':cookie,'X-Foodshare-CSRF':csrf})[0]==403
    safe={'Origin':'https://foodshare.test','Cookie':cookie,'X-Foodshare-CSRF':csrf}
    status,headers,_=request('/foodshare/session',handle,safe)
    assert status==204
    saved=headers[b'set-cookie'].decode()
    assert 'HttpOnly' in saved and 'Secure' in saved and 'SameSite=strict' in saved
    assert token in saved
    assert request('/foodshare/session',handle,safe)[0]==400


def v1_database(path):
    """Small old-format database: explicit fixtures for migration preservation."""
    import json
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, deactivation_verification TEXT)')
        conn.execute('INSERT INTO users VALUES (1, ?, ?)',('existing',json.dumps({'note':'Private verification','by':2})))
        conn.execute('CREATE TABLE batches (id INTEGER PRIMARY KEY, name TEXT, quantity INTEGER, allergens TEXT)')
        conn.execute('INSERT INTO batches VALUES (1, ?, 7, ?)',('Original food','[]'))
        conn.execute('CREATE TABLE feedback (id INTEGER PRIMARY KEY, rating INTEGER, category TEXT, message TEXT, submitted_on TEXT, reviewed INTEGER, archived INTEGER)')
        conn.execute("INSERT INTO feedback VALUES (1, 5, 'General', 'Keep this message', '2026-10-22', 1, 0)")
        conn.execute('PRAGMA user_version=1')


def test_v1_migration_preserves_records_and_marks_safety_unknown(tmp_path):
    path=tmp_path/'old.sqlite3';v1_database(path)
    db=SqliteStore(str(path))
    after=db.dump()
    assert after['users'][0]['username']=='existing'
    assert after['users'][0]['deactivation_verification']=={'verified':True,'by':2}
    assert after['batches'][0]['quantity']==7
    assert not after['batches'][0]['allergens_confirmed']
    assert after['feedback'][0]['message']=='Keep this message'
    assert after['feedback'][0]['reviewed']
    assert set(after['feedback'][0])=={'id','message','submitted_on','reviewed','archived'}
    assert (tmp_path/'old.sqlite3.pre-v2.sqlite3').exists()


def test_failed_migration_restores_pre_update_database(tmp_path,monkeypatch):
    path=tmp_path/'old.sqlite3';v1_database(path)
    def broken(conn):
        conn.execute("UPDATE batches SET quantity=999 WHERE id=1")
        conn.execute('CREATE TABLE partial_update (id INTEGER)')
        raise RuntimeError('injected migration failure')
    monkeypatch.setattr(SqliteStore,'_create_tables',staticmethod(broken))
    with pytest.raises(RuntimeError): SqliteStore(str(path))
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT quantity FROM batches').fetchone()[0]==7
        assert conn.execute('PRAGMA user_version').fetchone()[0]==1
        assert not conn.execute("SELECT name FROM sqlite_master WHERE name='partial_update'").fetchall()


def test_no_show_cannot_be_recorded_early_and_collection_cannot_be_backdated(env):
    db,a,_=env
    pickup=allocation(env)
    with pytest.raises(DomainError,match='window has ended'):
        s.move_in_queue(db,a['staff'],pickup['id'],'no_show')
    with pytest.raises(DomainError,match='before'):
        s.record_collection(db,a['staff'],1,{},'2026-10-22')


def test_declined_swap_has_a_short_retry_cooldown(env):
    db,a,clock=env
    pickup=allocation(env)
    request=s.request_swap(db,a['recipient2'],pickup['id'],1)
    s.decline_swap(db,a['staff'],request['id'],'Please speak with Staff about another item.')
    with pytest.raises(DomainError,match='wait a minute'):
        s.request_swap(db,a['recipient2'],pickup['id'],1)
    clock[0]+=timedelta(minutes=1)
    assert s.request_swap(db,a['recipient2'],pickup['id'],1)['status']==d.PENDING


def test_archived_empty_batch_does_not_generate_low_stock_alerts(env):
    db,a,_=env
    batch=s.save_batch(db,a['staff'],{'name':'Discontinued','quantity':0,'expiry_date':'2026-11-22',
                                      'allergens_confirmed':True,'archived':True})
    assert not any(x['name']=='Discontinued' for x in s.stock_alerts(db,a['staff'])['low_stock'])
    assert batch['id'] not in [b['id'] for b in s.list_batches(db,a['staff'])]
    assert batch['id'] in [b['id'] for b in s.list_batches(db,a['staff'],include_archived=True)]
    with pytest.raises(DomainError):
        s.save_batch(db,a['staff'],{'name':'Rice 1kg','expiry_date':'2026-11-22','archived':True},1)


def test_public_rate_limit_survives_a_new_service_instance(env):
    db,_,_=env
    for _ in range(3): pc.public_limit(db,'test_public_limit',3)
    with pytest.raises(DomainError): pc.public_limit(SqliteStore(db.path),'test_public_limit',3)


def test_donation_references_are_long_unpredictable_tokens(env):
    db,_,_=env
    donation=s.schedule_donation(db,[{'item_type':'Rice','quantity':2}],'2026-10-23','10:00')
    assert donation['reference'].startswith('DN-') and len(donation['reference'])==27


def test_stock_correction_has_before_after_reason_code_and_source(env):
    db,a,_=env
    donation=s.schedule_donation(db,[{'item_type':'Rice','quantity':3}],'2026-10-23','10:00')
    donation=s.receive_donation(db,a['staff'],donation['reference'],
                              [{'accepted_qty':3,'expiry_date':'2026-11-22','allergens_confirmed':True}])
    batch_id=donation['items'][0]['batch_id']
    row=s.adjust_stock(db,a['staff'],batch_id,-1,'One unit was misrecorded',
                       reason_code='Donation correction',source_type='donations',source_id=donation['id'])
    assert (row['before_quantity'],row['after_quantity'],row['change'])==(3,2,-1)
    assert row['source_id']==donation['id']
    reversal=s.reverse_adjustment(db,a['staff'],row['id'],'Recount confirmed three units')
    assert (reversal['before_quantity'],reversal['after_quantity'])==(2,3)
    with pytest.raises(DomainError): s.reverse_adjustment(db,a['staff'],row['id'],'Again')


def test_unsafe_block_is_audited_after_business_rollback(env):
    db,a,_=env
    before=state(db,'allocations','batches')
    with pytest.raises(DomainError):
        s.create_allocation(db,a['staff'],a['recipient2']['id'],[{'batch_id':6,'quantity':1}],
                           '2026-10-22','10:00')
    assert state(db,*before)==before
    event=db.dump()['audit'][-1]
    assert event['action']=='Unsafe food blocked' and event['result']=='Denied'
    assert event['actor_id']==a['staff']['id']
    assert event['target']=='Batch 6' and event['details']=={}


def test_cross_midnight_queue_clock_is_not_clamped():
    from foodshare.services.queue import _clock
    assert _clock(23*60+55)=='23:55'
    assert _clock(24*60+5)=='00:05 (+1 day)'


def test_cross_midnight_pickup_expires_only_after_its_window(env):
    db,a,clock=env
    clock[0]=datetime(2026,10,22,23,55)
    pickup=s.create_allocation(db,a['staff'],a['recipient2']['id'],[{'batch_id':2,'quantity':1}],
                               '2026-10-22','23:55')
    clock[0]=datetime(2026,10,23,0,5)
    assert s.expire_overdue_allocations(db)==0
    assert s.get_allocation(db,a['recipient2'],pickup['id'])['status']==d.ALLOCATED
    clock[0]=datetime(2026,10,23,0,10)
    assert s.expire_overdue_allocations(db)==1
    assert s.get_allocation(db,a['staff'],pickup['id'])['status']==d.EXPIRED


def test_demo_today_pickup_has_confirmed_needs(tmp_path,monkeypatch):
    monkeypatch.setattr(d,'now',lambda:datetime(2026,10,22,10))
    db=seed(str(tmp_path/'demo.sqlite3'),today_pickup='10:30')
    staff=s.login(db,'staff',DEMO_PASSWORD)
    tom=s.login(db,'recipient3',DEMO_PASSWORD)
    profile=s.get_profile(db,tom,tom['id'])
    assert profile['allergies_confirmed']
    pickup=next(a for a in s.list_allocations(db,staff) if a['recipient_id']==tom['id'])
    assert s.record_collection(db,staff,pickup['id'],{})['recipient_id']==tom['id']


def test_needs_summary_minimizes_private_fields_without_ranking(env):
    db,a,_=env
    recipients=s.recipients_for_allocation(db,a['staff'])
    assert [r['display_name'] for r in recipients]==sorted([r['display_name'] for r in recipients],key=str.lower)
    summary=next(r['summary'] for r in recipients if r['id']==a['recipient']['id'])
    assert not {'accessibility_needs','preferred_pickup','username','recipient_id'} & summary.keys()


def test_pickup_notice_is_atomic_and_noop_change_does_not_duplicate_it(env,monkeypatch):
    from foodshare.storage import Tx
    db,a,_=env
    assert s.update_pickup(db,a['staff'],1,'2026-10-23','14:00') is None
    before=state(db,'allocations','notifications','queue_entries')
    original=Tx.insert
    def broken(self,table,record):
        if table=='notifications': raise RuntimeError('injected notice failure')
        return original(self,table,record)
    monkeypatch.setattr(Tx,'insert',broken)
    with pytest.raises(RuntimeError): s.update_pickup(db,a['staff'],1,'2026-10-23','15:00')
    assert state(db,*before)==before
    monkeypatch.setattr(Tx,'insert',original)
    s.update_pickup(db,a['staff'],1,'2026-10-23','15:00')
    s.update_pickup(db,a['staff'],1,'2026-10-23','15:00')
    assert len(db.dump()['notifications'])==1


def test_removed_swap_target_closes_before_a_stale_decision(env):
    db,a,_=env
    pickup=allocation(env)
    request=s.request_swap(db,a['recipient2'],pickup['id'],1)
    with db.transaction() as tx: tx.get('allocations',pickup['id'])['items']=[]
    assert s.get_swap(db,a['staff'],request['id'])['status']==d.CANCELLED
    before=state(db,'batches','allocations')
    with pytest.raises(DomainError): s.approve_swap(db,a['staff'],request['id'],1)
    assert state(db,*before)==before


def test_feedback_concurrent_replay_saves_once(env):
    db,_,_=env
    browser,form=s.feedback_form()
    def submit(_):
        try:
            s.submit_feedback(db,'Single message',browser_token=browser,form_token=form)
            return True
        except DomainError:return False
    with ThreadPoolExecutor(2) as pool:
        assert list(pool.map(submit,range(2))).count(True)==1
    assert len(db.dump()['feedback'])==4


def test_failures_older_than_fifteen_minutes_do_not_cause_lockout(env):
    db,a,clock=env
    for _ in range(4):
        with pytest.raises(DomainError): s.login(db,'staff','wrong')
    clock[0]+=timedelta(minutes=15)
    with pytest.raises(DomainError): s.login(db,'staff','wrong')
    assert s.login(db,'staff',DEMO_PASSWORD)['id']==a['staff']['id']
    assert any(e['action']=='Sign-in failed' and e['result']=='Denied' for e in db.dump()['audit'])


def test_queue_ties_use_checkin_entry_id_not_allocation_id(env):
    db,a,_=env
    first=allocation(env)
    second=allocation(env)
    s.check_in(db,a['staff'],second['id'])
    s.check_in(db,a['staff'],first['id'])
    assert s.queue_status(db,a['recipient2'],second['id'])['position']==1
    assert s.queue_status(db,a['recipient2'],first['id'])['position']==2


def test_late_collection_closes_expired_swap_as_expired_not_closed(env):
    db,a,clock=env
    pickup=allocation(env)
    request=s.request_swap(db,a['recipient2'],pickup['id'],1)
    clock[0]+=timedelta(minutes=16)
    s.record_collection(db,a['staff'],pickup['id'],{},exception_reason='Transport delay')
    assert next(x for x in db.dump()['swaps'] if x['id']==request['id'])['status']==d.EXPIRED
