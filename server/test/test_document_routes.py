# ---------------------------------------------------------------------------
# Document-management route tests (require a live database)
#
# Covers the document and version listing/retrieval/deletion routes end to end
# through the Flask test client: list-documents, get-document, list-versions,
# list-all-versions, and delete-document. These create real users and
# documents, so each DB-backed test skips itself if no database is reachable.
# ---------------------------------------------------------------------------
import io
import uuid

import pytest

from server import create_app


_DOC_MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
    b"trailer<</Size 4/Root 1 0 R>>\n"
    b"%%EOF\n"
)


@pytest.fixture()
def doc_client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def _doc_db_available(client):
    """True if the DB is reachable (login returns 400/401, not 503)."""
    r = client.post("/api/login", json={"email": "x@y.z", "password": "nope"})
    return r.status_code != 503


def _doc_auth_headers(client):
    """Create a fresh user, log in, and return Authorization headers."""
    uniq = uuid.uuid4().hex[:12]
    email = f"doc_{uniq}@example.com"
    login = f"doc_{uniq}"
    password = "Passw0rd!"

    r = client.post(
        "/api/create-user",
        json={"email": email, "login": login, "password": password},
    )
    assert r.status_code == 201, r.get_data(as_text=True)

    r = client.post("/api/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.get_data(as_text=True)
    return {"Authorization": f"Bearer {r.get_json()['token']}"}


def _doc_upload(client, headers):
    """Upload the minimal PDF and return its document id."""
    data = {"file": (io.BytesIO(_DOC_MINIMAL_PDF), "sample.pdf")}
    r = client.post(
        "/api/upload-document",
        headers=headers,
        data=data,
        content_type="multipart/form-data",
    )
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()["id"]


def test_doc_list_documents_requires_auth(doc_client):
    """list-documents without a token is rejected before any DB access."""
    r = doc_client.get("/api/list-documents")
    assert r.status_code == 401


def test_doc_get_document_not_found(doc_client):
    """get-document for an id the caller does not own returns 404."""
    if not _doc_db_available(doc_client):
        pytest.skip("database not reachable")

    headers = _doc_auth_headers(doc_client)
    r = doc_client.get("/api/get-document/999999999", headers=headers)
    assert r.status_code == 404


def test_doc_document_lifecycle(doc_client):
    """upload -> list -> get -> watermark -> list versions -> delete."""
    if not _doc_db_available(doc_client):
        pytest.skip("database not reachable")

    headers = _doc_auth_headers(doc_client)
    doc_id = _doc_upload(doc_client, headers)

    # list-documents: the new document shows up for its owner
    r = doc_client.get("/api/list-documents", headers=headers)
    assert r.status_code == 200
    ids = {d["id"] for d in r.get_json()["documents"]}
    assert doc_id in ids

    # get-document: the stored PDF is returned inline
    r = doc_client.get(f"/api/get-document/{doc_id}", headers=headers)
    assert r.status_code == 200
    assert r.data.startswith(b"%PDF-")

    # create a watermark so there is a version to list
    r = doc_client.post(
        f"/api/create-watermark/{doc_id}",
        headers=headers,
        json={
            "method": "toy-eof",
            "intended_for": "carol",
            "secret": "lifecycle-secret",
            "key": "lifecycle-key",
        },
    )
    assert r.status_code == 201, r.get_data(as_text=True)

    # list-versions (for this document) includes the new version
    r = doc_client.get(f"/api/list-versions/{doc_id}", headers=headers)
    assert r.status_code == 200
    doc_versions = r.get_json()["versions"]
    assert any(v["documentid"] == doc_id for v in doc_versions)

    # list-all-versions (for the whole user) also includes it
    r = doc_client.get("/api/list-all-versions", headers=headers)
    assert r.status_code == 200
    all_versions = r.get_json()["versions"]
    assert any(v["documentid"] == doc_id for v in all_versions)

    # delete-document removes it
    r = doc_client.delete(f"/api/delete-document/{doc_id}", headers=headers)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["deleted"] is True

    # it is gone afterwards
    r = doc_client.get(f"/api/get-document/{doc_id}", headers=headers)
    assert r.status_code == 404
