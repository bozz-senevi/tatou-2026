#!/usr/bin/env python3
"""API-level fuzzer for Tatou (Specialization A, part 2).

Fuzzes the HTTP API past authentication and JSON parsing. Registers a user,
logs in, uploads a document, then throws malformed values at the authenticated
endpoints. A finding = the server returns 5xx (unhandled) or leaks internal
error text (info leak). A clean 4xx is correct input handling, not a bug.
Deterministic (fixed seed).
"""
import os, sys, random
import requests

BASE = os.environ.get("TATOU_BASE", "http://localhost:5000")
rng = random.Random(1337)

MINIMAL_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
    b"trailer<</Root 1 0 R/Size 4>>\n%%EOF\n"
)

# malformed values injected one field at a time
WEIRD = [
    None, "", "A" * 20000, 0, -1, 1.5, True, False, [], {}, {"x": "y"},
    "null", "\x00\x01\x02", "💥" * 200, "../../etc/passwd",
    "' OR '1'='1", "%n%n%n%n", 10 ** 40, "\n\n\n", " ",
]

# substrings that mean the server leaked its internals
LEAKS = ["traceback", "database error", "fzerror", "filedataerror",
         "sqlalchemy", "pymysql", "watermarking failed:"]

def bug(r):
    if r.status_code >= 500:
        return f"HTTP {r.status_code}"
    low = r.text.lower()
    for s in LEAKS:
        if s in low:
            return f"info-leak('{s}')"
    return None

def setup():
    u = f"apifuzz_{rng.randint(0, 10**9)}"
    em = u + "@example.com"
    requests.post(f"{BASE}/api/create-user",
                  json={"email": em, "login": u, "password": "pw123456"}, timeout=10)
    tok = requests.post(f"{BASE}/api/login",
                        json={"email": em, "password": "pw123456"}, timeout=10).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{BASE}/api/upload-document", headers=H,
                      files={"file": ("t.pdf", MINIMAL_PDF, "application/pdf")},
                      data={"name": "t"}, timeout=10)
    return H, r.json()["id"]

def fuzz_endpoint(name, url, H, base_body, n=300):
    found = {}
    for _ in range(n):
        body = dict(base_body)
        field = rng.choice(list(base_body))
        body[field] = rng.choice(WEIRD)
        try:
            r = requests.post(url, headers=H, json=body, timeout=15)
        except Exception as e:
            found.setdefault(f"{name}: request error {type(e).__name__}", str(body)[:120])
            continue
        b = bug(r)
        if b:
            found.setdefault(f"{name}: {b} [field={field}]",
                             f"value={repr(body[field])[:60]} -> {r.text[:100]}")
    return found

def main():
    print(f"[*] target {BASE}")
    try:
        hz = requests.get(f"{BASE}/healthz", timeout=10)
        print("[*] healthz:", hz.status_code, hz.text[:80])
    except Exception as e:
        print("[!] server not reachable:", e); sys.exit(1)
    H, doc_id = setup()
    print(f"[*] authenticated, test doc id={doc_id}")

    found = {}
    found.update(fuzz_endpoint(
        "create-watermark", f"{BASE}/api/create-watermark/{doc_id}", H,
        {"method": "toy-eof", "intended_for": "g", "secret": "s", "key": "k"}))
    found.update(fuzz_endpoint(
        "read-watermark", f"{BASE}/api/read-watermark/{doc_id}", H,
        {"method": "toy-eof", "key": "k"}))

    print(f"\n=== API FINDINGS: {len(found)} unique ===")
    for k, v in sorted(found.items()):
        print(f"\n[{k}]\n    {v}")
    if not found:
        print("none - the API's input validation held for these inputs")

if __name__ == "__main__":
    main()
