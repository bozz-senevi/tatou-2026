# ---------------------------------------------------------------------------
# Remaining-route tests: home and the two RMAP endpoints.
#
# These complete coverage so that every route in the app is touched by at
# least one test. The RMAP happy path requires a full PGP handshake, which is
# out of scope here; instead we exercise each RMAP route's input validation
# and error handling, which runs the handler and returns a 4xx/5xx. None of
# these need a database or authentication.
# ---------------------------------------------------------------------------
import pytest

from server import create_app


@pytest.fixture()
def misc_client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_home_route_responds(misc_client):
    """GET / runs the home handler (any non-server-error response is fine)."""
    r = misc_client.get("/")
    assert r.status_code < 500


def test_rmap_initiate_rejects_bad_payload(misc_client):
    """POST /api/rmap-initiate validates the body and handles handshake errors."""
    # A non-dict body is rejected by the up-front validation branch.
    r = misc_client.post("/api/rmap-initiate", json=[])
    assert r.status_code == 400

    # A dict body passes validation but fails the handshake, exercising the
    # route body and its error handling (RMAPError -> 400, or unavailable -> 503).
    r = misc_client.post("/api/rmap-initiate", json={"payload": "not-a-valid-message"})
    assert r.status_code in (400, 503)


def test_rmap_get_link_rejects_bad_payload(misc_client):
    """POST /api/rmap-get-link validates the body and handles handshake errors."""
    r = misc_client.post("/api/rmap-get-link", json=[])
    assert r.status_code == 400

    r = misc_client.post("/api/rmap-get-link", json={"payload": "not-a-valid-message"})
    assert r.status_code in (400, 503)
