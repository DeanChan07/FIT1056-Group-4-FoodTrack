"""Public abuse controls. Feedback tokens stay in memory and never join stored feedback."""
import secrets
import threading
import time
from datetime import datetime

from .. import domain as d
from ..domain import DomainError

_LOCK = threading.RLock()
_BROWSERS = {}
_FORMS = {}
TTL = 600


def _prune(moment):
    for mapping in (_BROWSERS, _FORMS):
        for key, value in list(mapping.items()):
            if moment - value[0] >= TTL:
                del mapping[key]


def feedback_form(browser_token=None):
    """Issue a single-use form, bound to a transient anonymous ten-minute bucket."""
    with _LOCK:
        moment = time.monotonic()
        _prune(moment)
        if browser_token not in _BROWSERS:
            browser_token = secrets.token_urlsafe(24)
            _BROWSERS[browser_token] = [moment, 0]
        form = secrets.token_urlsafe(24)
        _FORMS[form] = (moment, browser_token)
        return browser_token, form


def save_feedback_once(browser_token, form_token, save):
    # Consume only after a successful commit. The lock serializes replay attempts.
    with _LOCK:
        _prune(time.monotonic())
        form = _FORMS.get(form_token)
        browser = _BROWSERS.get(browser_token)
        if not form or not browser or form[1] != browser_token:
            raise DomainError("This feedback form has expired or was already sent. Please open a new form.")
        if browser[1] >= 5:
            raise DomainError("Thank you. Please wait up to ten minutes before sending more feedback.")
        result = save()
        browser[1] += 1
        del _FORMS[form_token]
        return result


def public_limit(store, scope, limit, seconds=600, bucket="site"):
    """Shared SQLite cap survives refreshed tabs; no identity, IP or message is recorded.

    This conservative site-wide cap protects this single-site prototype. It is not
    a per-person quota and should be tuned to the organisation's expected traffic.
    """
    denied = False
    with store.transaction() as tx:
        row = tx.find_one("public_limits", scope=scope, bucket=bucket)
        moment = d.now()
        if not row:
            row = tx.insert("public_limits", {"scope": scope, "bucket": bucket,
                            "count": 0, "started_at": moment.isoformat()})
        if (moment - datetime.fromisoformat(row["started_at"])).total_seconds() >= seconds:
            row.update(count=0, started_at=moment.isoformat())
        if row["count"] >= limit:
            denied = True
        else:
            row["count"] += 1
    if denied:
        raise DomainError("This service is busy. Please wait a few minutes and try again.")
