"""API-level regression tests for findings C1-C3 (Specialization A).

Black-box HTTP tests: they call the RUNNING server and assert the correct
behaviour. They do NOT modify server.py. They are expected to FAIL until the
server.py fixes are applied, then pass - that is the non-regression guard.

Requires a running server (docker compose up). Fails if it is unreachable.
Run:  TATOU_BASE=http://localhost:5000 pytest -v test/test_api_findings.py
"""
import os
import random
import pytest
import requests

BASE = os.environ.get("TATOU_BASE", "http://localhost:5000")

MINIMAL_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
    b"trailer<</Root 1 0 R/Size 4>>\n%%EOF\n"
)


@pytest.fixture(scope="module")
def api():
    try:
        requests.get(f"{BASE}/healthz", timeout=5)
    except Exception as exc:
        pytest.fail(f"Tatou server not reachable at {BASE} (start it with docker compose up): {exc}")
    u = f"reg_{random.randint(0, 10**9)}"
    em = u + "@example.com"
    requests.post(f"{BASE}/api/create-user",
                  json={"email": em, "login": u, "password": "pw123456"}, timeout=10)
    tok = requests.post(f"{BASE}/api/login",
                        json={"email": em, "password": "pw123456"}, timeout=10).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{BASE}/api/upload-document", headers=H,
                      files={"file": ("t.pdf", MINIMAL_PDF, "application/pdf")},
                      data={"name": "t"}, timeout=10)
    return BASE, H, r.json()["id"]


def _cw(base, H, doc_id, **over):
    body = {"method": "toy-eof", "intended_for": "g", "secret": "s", "key": "k"}
    body.update(over)
    return requests.post(f"{base}/api/create-watermark/{doc_id}", headers=H, json=body, timeout=15)


# C1: a non-string field must not crash the server (should be a clean 400)
def test_C1_nonstring_intended_for_not_500(api):
    base, H, doc_id = api
    r = _cw(base, H, doc_id, intended_for={"x": "y"})
    assert r.status_code != 500, f"non-string intended_for crashed server ({r.status_code})"


# C2: empty secret / key are bad input -> must be 400, not 500
def test_C2_empty_secret_not_500(api):
    base, H, doc_id = api
    r = _cw(base, H, doc_id, secret="")
    assert r.status_code != 500, f"empty secret returned 500: {r.text[:120]}"


def test_C2_empty_key_not_500(api):
    base, H, doc_id = api
    r = _cw(base, H, doc_id, key="")
    assert r.status_code != 500, f"empty key returned 500: {r.text[:120]}"


# C3: the server must not leak raw database/library internals to the client
def test_C3_no_internal_error_leak(api):
    base, H, doc_id = api
    payload_over = {"intended_for": "dup-probe"}
    _cw(base, H, doc_id, **payload_over)              # first write
    r = _cw(base, H, doc_id, **payload_over)          # second -> duplicate link path
    body = r.text.lower()
    leaks = ["pymysql", "traceback", "sqlalchemy", "integrityerror"]
    assert not any(l in body for l in leaks), f"leaked internals: {r.text[:160]}"
