"""The served app must trust the proxy's scheme header.

Behind Cloud Run, TLS terminates at the front end. Without `--proxy-headers`
uvicorn believes every request arrived over plain http, so every absolute URL
FastAPI generates comes out as `http://` — including the automatic
trailing-slash redirect:

    GET https://api.alafia.app/api/v1/notifications
      -> 307  location: http://api.alafia.app/api/v1/notifications/

A browser blocks that as mixed content. The Notifications page's fetch never
completed, the error was swallowed into `catch (e) { console.error(e) }`, and a
user holding 18 unread notifications was shown "No notifications".

This is a static check on purpose. The defect lives in how the process is
LAUNCHED, so no request-level test against TestClient can see it — TestClient
never goes through a proxy. §3ag: a static check beats behavioural tests for a
whole class of "the code is right, the wiring is not".
"""

from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"


def test_uvicorn_is_launched_with_proxy_headers():
    cmd = DOCKERFILE.read_text()
    assert "--proxy-headers" in cmd, (
        "uvicorn must run with --proxy-headers behind Cloud Run, or every "
        "generated URL (redirects included) is http:// and browsers block it."
    )
    assert "--forwarded-allow-ips" in cmd, (
        "--proxy-headers is ignored unless the proxy's address is trusted."
    )


def test_collection_routes_are_reachable_without_a_redirect_loop():
    """Every router mounted at a bare prefix answers '/' — so clients must send
    the trailing slash. This pins the shape so the reason is discoverable."""
    from app.main import app

    bare = sorted({
        r.path for r in app.routes
        if getattr(r, "path", "").startswith("/api/v1/") and r.path.endswith("/")
        and r.path.count("/") == 4
    })
    assert bare, "expected collection routes registered at the bare prefix"
    # A sample that the notifications incident came from.
    assert "/api/v1/notifications/" in bare
