"""Headless UI regressions for the new controls; these are not real-browser tests."""
from datetime import datetime
import pytest
from foodshare import domain as d, services as s
from conftest import user, ready_pickup
from test_app import open_page, click, shown, no_errors
from seed import DEMO_PASSWORD


def test_demo_credentials_are_hidden_by_default(store,monkeypatch):
    monkeypatch.delenv('FOODSHARE_DEMO',raising=False)
    at=open_page(store,'sign_in')
    assert DEMO_PASSWORD not in shown(at)
    assert not any(e.label=='Demo accounts' for e in at.expander)


def test_demo_credentials_require_explicit_demo_mode(store,monkeypatch):
    monkeypatch.setenv('FOODSHARE_DEMO','1')
    at=open_page(store,'sign_in')
    assert DEMO_PASSWORD in shown(at)


def test_staff_can_cancel_a_volunteer_task_in_the_ui(store):
    at=open_page(store,'tasks','staff')
    task_id=at.selectbox(key='task_edit_id').value
    prefix=f'taskedit{task_id}_'
    at.text_input(key=prefix+'reason').input('Shift cancelled')
    at.checkbox(key=prefix+'confirmed').check()
    at=click(at,'Cancel task')
    no_errors(at)
    assert store.dump()['tasks'][task_id-1]['status']==d.CANCELLED


def test_unknown_allergens_are_visible_and_confirmable(store):
    at=open_page(store,'inventory','staff')
    at.text_input(key='batchnew_name').input('New food')
    at.number_input(key='batchnew_quantity').set_value(3)
    at.checkbox(key='batchnew_confirmed').check()
    at=click(at,'Add to inventory')
    no_errors(at)
    assert next(b for b in store.dump()['batches'] if b['name']=='New food')['allergens_confirmed']


def test_admin_can_create_a_second_admin_only_with_current_password(store):
    at=open_page(store,'accounts','admin')
    at.selectbox(key='acct_new_role').select(d.ADMIN)
    at.text_input(key='acct_new_name').input('Second Admin')
    at.text_input(key='acct_new_username').input('admin2')
    at.text_input(key='acct_new_password').input(DEMO_PASSWORD)
    at.text_input(key='acct_new_auth').input(DEMO_PASSWORD)
    at.checkbox(key='acct_new_confirm').check()
    at=click(at,'Create account')
    no_errors(at)
    assert next(u for u in store.dump()['users'] if u['username']=='admin2')['role']==d.ADMIN


def test_feedback_requires_a_message_even_when_signed_in(store):
    at=open_page(store,'feedback','recipient')
    at=click(at,'Send anonymously')
    assert '1 to 500 characters' in shown(at)
    assert len(store.dump()['feedback'])==3


def test_queue_failure_keeps_last_confirmed_timestamp(store,monkeypatch):
    from streamlit.testing.v1 import AppTest
    from test_app import signed_in
    at=AppTest.from_string('from foodshare.views.common import live_queue_card\nlive_queue_card(1)',default_timeout=30)
    signed_in(at,store,'recipient');at.run();no_errors(at)
    last=at.session_state['_queue_last_1']
    def broken(*args,**kwargs): raise d.DomainError('Simulated refresh failure')
    monkeypatch.setattr(s,'queue_status',broken)
    at.run();no_errors(at)
    assert 'Estimate unavailable' in shown(at) and 'Last confirmed update' in shown(at)
    assert at.session_state['_queue_last_1']==last


def test_profile_fields_explain_required_optional_and_purpose(store):
    at=open_page(store,'my_needs','recipient')
    text=shown(at)
    labels=[w.label for kind in ('number_input','text_input','multiselect','segmented_control')
            for w in getattr(at,kind)]
    for key,label,required,why in d.PROFILE_FIELDS:
        assert f"{label} ({'required' if required else 'optional'})" in labels
        assert why in text


def test_staff_queue_timer_does_not_keep_an_idle_session_alive(store,monkeypatch):
    from datetime import timedelta
    from streamlit.testing.v1 import AppTest
    from test_app import signed_in
    clock=[d.now()]
    monkeypatch.setattr(d,'now',lambda:clock[0])
    at=AppTest.from_string('from foodshare.views.food import queue_table\nqueue_table("'+d.today().isoformat()+'")',default_timeout=30)
    signed_in(at,store,'staff');at.run();no_errors(at)
    token=at.session_state['session_token']
    initial=store.dump()['sessions'][0]['last_seen']
    clock[0]+=timedelta(minutes=10)
    at.run();no_errors(at)
    assert store.dump()['sessions'][0]['last_seen']==initial
    clock[0]+=timedelta(minutes=5)
    at.run();no_errors(at)
    assert 'session has ended' in shown(at)
    assert not at.button
    assert s.resume_session(store,token)[0] is None
