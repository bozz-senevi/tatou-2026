# ---------------------------------------------------------------------------
# Watermark route tests (require a live database)
#
# End-to-end coverage for the watermarking API, driven through the Flask test
# client: create a user, log in, upload a PDF, create a watermark, download the
# watermarked version, list the available methods, and read the secret back.
# These create real users/documents, so they need a reachable DB; each one
# skips itself automatically if the database is not available.
# ---------------------------------------------------------------------------
import io
import uuid

import pytest

from server import create_app


# A minimal but valid PDF. "toy-eof" only needs the %PDF- header, but keeping a
# well-formed body makes the fixture robust if pointed at another method later.
_WM_MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
    b"trailer<</Size 4/Root 1 0 R>>\n"
    b"%%EOF\n"
)


@pytest.fixture()
def wm_client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def _wm_db_available(client):
    """True if the DB is reachable (login returns 400/401, not 503)."""
    r = client.post("/api/login", json={"email": "x@y.z", "password": "nope"})
    return r.status_code != 503


def _wm_auth_headers(client):
    """Create a fresh user, log in, and return Authorization headers."""
    uniq = uuid.uuid4().hex[:12]
    email = f"wm_{uniq}@example.com"
    login = f"wm_{uniq}"
    password = "Passw0rd!"

    r = client.post(
        "/api/create-user",
        json={"email": email, "login": login, "password": password},
    )
    assert r.status_code == 201, r.get_data(as_text=True)

    r = client.post("/api/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.get_data(as_text=True)
    token = r.get_json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _wm_upload_pdf(client, headers):
    """Upload the minimal PDF and return its document id."""
    data = {"file": (io.BytesIO(_WM_MINIMAL_PDF), "sample.pdf")}
    r = client.post(
        "/api/upload-document",
        headers=headers,
        data=data,
        content_type="multipart/form-data",
    )
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()["id"]


def test_wm_get_watermarking_methods(wm_client):
    """GET /api/get-watermarking-methods lists methods (no auth, no DB)."""
    r = wm_client.get("/api/get-watermarking-methods")
    assert r.status_code == 200
    body = r.get_json()
    assert "methods" in body
    assert body["count"] == len(body["methods"])
    names = {m["name"] for m in body["methods"]}
    assert "toy-eof" in names


def test_wm_create_and_read_watermark(wm_client):
    """upload -> create-watermark -> get-version -> read-watermark round-trip."""
    if not _wm_db_available(wm_client):
        pytest.skip("database not reachable")

    headers = _wm_auth_headers(wm_client)
    doc_id = _wm_upload_pdf(wm_client, headers)

    secret = "top-secret-42"
    key = "correct horse battery staple"

    # create-watermark
    r = wm_client.post(
        f"/api/create-watermark/{doc_id}",
        headers=headers,
        json={
            "method": "toy-eof",
            "intended_for": "alice",
            "secret": secret,
            "key": key,
        },
    )
    assert r.status_code == 201, r.get_data(as_text=True)
    created = r.get_json()
    assert created["documentid"] == doc_id
    link = created["link"]
    assert link

    # get-version: the watermarked PDF is downloadable via its link token
    r = wm_client.get(f"/api/get-version/{link}")
    assert r.status_code == 200
    assert r.data.startswith(b"%PDF-")

    # read-watermark: the secret round-trips with the correct key
    r = wm_client.post(
        f"/api/read-watermark/{doc_id}",
        headers=headers,
        json={"method": "toy-eof", "key": key},
    )
    assert r.status_code == 201, r.get_data(as_text=True)
    assert r.get_json()["secret"] == secret


def test_wm_read_watermark_wrong_key_is_rejected(wm_client):
    """A wrong key must not recover the secret."""
    if not _wm_db_available(wm_client):
        pytest.skip("database not reachable")

    headers = _wm_auth_headers(wm_client)
    doc_id = _wm_upload_pdf(wm_client, headers)

    r = wm_client.post(
        f"/api/create-watermark/{doc_id}",
        headers=headers,
        json={
            "method": "toy-eof",
            "intended_for": "bob",
            "secret": "another-secret",
            "key": "the-right-key",
        },
    )
    assert r.status_code == 201, r.get_data(as_text=True)

    # Wrong key fails authentication; the route maps that to a 400 error.
    r = wm_client.post(
        f"/api/read-watermark/{doc_id}",
        headers=headers,
        json={"method": "toy-eof", "key": "the-wrong-key"},
    )
    assert r.status_code == 400
