"""
Security tests for T.CROSS_USER / O.ACCESS_CONTROL:
an authenticated user must not be able to read or delete
a document owned by another user.
Added as the SAMM Security Testing improvement (Assurance assignment).
"""
import io
import uuid

import pytest

from server import app

MINIMAL_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


@pytest.fixture
def client():
    c = app.test_client()
    # These tests create real users/documents, so they need a live database.
    # When none is reachable (e.g. the no-DB CI unit-test job), skip instead of
    # failing — matching the pattern in test_document_routes.py. A reachable DB
    # answers a bad-credential login with 400/401; an unreachable one gives 503.
    probe = c.post("/api/login", json={"email": "x@y.z", "password": "nope"})
    if probe.status_code == 503:
        pytest.skip("database not reachable; skipping DB-backed access-control tests")
    return c


def _make_user(client):
    tag = uuid.uuid4().hex[:8]
    email = f"u{tag}@test.local"
    password = f"Test-pass-{tag}"
    r = client.post("/api/create-user",
                    json={"email": email, "login": f"u{tag}", "password": password})
    assert r.status_code == 201, r.get_json()
    r = client.post("/api/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.get_json()
    return {"Authorization": f"Bearer {r.get_json()['token']}"}


def _upload(client, headers):
    data = {"file": (io.BytesIO(MINIMAL_PDF), "owned.pdf"), "name": "owned.pdf"}
    r = client.post("/api/upload-document", headers=headers, data=data,
                    content_type="multipart/form-data")
    assert r.status_code == 201, r.get_json()
    return r.get_json()["id"]


def test_other_user_cannot_get_document(client):
    owner = _make_user(client)
    attacker = _make_user(client)
    doc_id = _upload(client, owner)
    r = client.get(f"/api/get-document/{doc_id}", headers=attacker)
    assert r.status_code in (403, 404)
    r = client.get(f"/api/get-document/{doc_id}", headers=owner)
    assert r.status_code == 200


def test_other_user_cannot_delete_document(client):
    owner = _make_user(client)
    attacker = _make_user(client)
    doc_id = _upload(client, owner)
    r = client.delete(f"/api/delete-document/{doc_id}", headers=attacker)
    assert r.status_code in (403, 404)
    r = client.get(f"/api/get-document/{doc_id}", headers=owner)
    assert r.status_code == 200


def test_unauthenticated_cannot_delete_document(client):
    owner = _make_user(client)
    doc_id = _upload(client, owner)
    r = client.delete(f"/api/delete-document/{doc_id}")
    assert r.status_code == 401
    r = client.get(f"/api/get-document/{doc_id}", headers=owner)
    assert r.status_code == 200
