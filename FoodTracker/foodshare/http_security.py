"""Same-origin cookie handoff using Streamlit 1.66's supported st.App routes.

Only a short-lived one-use handle is rendered into JavaScript. The real session
secret is set by an HTTP response with HttpOnly, never by document.cookie.
"""
import hmac
import secrets
import threading
import time
from urllib.parse import urlsplit

from starlette.responses import JSONResponse, Response
from starlette.routing import Route

COOKIE = "foodshare_session"
CSRF_COOKIE = "foodshare_csrf"
_HANDOFFS = {}
_LOCK = threading.Lock()


def cookie_handoff(token):
    with _LOCK:
        moment = time.monotonic()
        for handle, (created, _) in list(_HANDOFFS.items()):
            if moment - created >= 60:
                del _HANDOFFS[handle]
        handle = secrets.token_urlsafe(32)
        _HANDOFFS[handle] = (moment, token)
        return handle


def _same_origin(request):
    origin = request.headers.get("origin")
    if not origin:
        return False
    expected = urlsplit(str(request.url))
    actual = urlsplit(origin)
    return (actual.scheme, actual.netloc) == (expected.scheme, expected.netloc)


async def csrf(request):
    value = request.cookies.get(CSRF_COOKIE) or secrets.token_urlsafe(32)
    response = JSONResponse({"token": value}, headers={"Cache-Control": "no-store"})
    response.set_cookie(CSRF_COOKIE, value, max_age=600, secure=request.url.scheme == "https",
                        httponly=True, samesite="strict", path="/")
    return response


async def exchange(request):
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get("x-foodshare-csrf", "")
    if not _same_origin(request) or not cookie or not hmac.compare_digest(cookie, header):
        return Response(status_code=403)
    try:
        length = int(request.headers.get("content-length", "0") or "0")
    except ValueError:
        return Response(status_code=400)
    if length > 256:
        return Response(status_code=413)
    try:
        body = await request.body()
        if len(body) > 256:
            return Response(status_code=413)
        handle = body.decode("ascii")
    except (ValueError, UnicodeError):
        return Response(status_code=400)
    with _LOCK:
        pending = _HANDOFFS.pop(handle, None)
    if not pending or time.monotonic() - pending[0] >= 60:
        return Response(status_code=400)
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    token = pending[1]
    response.set_cookie(COOKIE, token, max_age=8 * 3600 if token else 0,
                        secure=request.url.scheme == "https", httponly=True,
                        samesite="strict", path="/")
    return response


def routes():
    return [Route("/foodshare/csrf", csrf, methods=["GET"]),
            Route("/foodshare/session", exchange, methods=["POST"])]
