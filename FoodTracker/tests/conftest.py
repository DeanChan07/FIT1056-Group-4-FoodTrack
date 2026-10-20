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
