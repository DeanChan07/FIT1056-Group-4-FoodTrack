"""Shared test setup: every test gets its own fresh demo database."""

import pytest

from foodshare import services as s
from foodshare.storage import SqliteStore
from seed import DEMO_PASSWORD, seed

NEW_PASSWORD = "a long enough new password"


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = str(tmp_path / "test.sqlite3")
    seed(path, today_pickup=None)  # tests that need a same-day pickup add their own
    monkeypatch.setenv("FOODSHARE_DB", path)
    return SqliteStore(path)


def user(store, username):
    return s.login(store, username, DEMO_PASSWORD)


def ready_pickup(store, allocation_id=1):
    """Arrange a same-day pickup for tests whose subject is collection, not booking."""
    from foodshare import domain as d
    with store.transaction() as tx:
        row = tx.get("allocations", allocation_id)
        row["pickup_date"] = d.today().isoformat()
        row["pickup_time"] = d.now().strftime("%H:%M")


def send_feedback(store, rating, category, message):
    """Obtain an actual single-use form for legacy service scenarios."""
    browser, form = s.feedback_form()
    return s.submit_feedback(store, message, browser_token=browser, form_token=form)
