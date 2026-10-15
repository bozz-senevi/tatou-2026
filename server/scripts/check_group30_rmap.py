"""check_group30_rmap.py — verify Group 30's RMAP endpoints work.

Hand this to another group. It plays the RMAP *client* against Group 30's
Tatou server: runs the four-message handshake (rmap-initiate / rmap-get-link),
obtains the session link, and downloads the watermarked PDF. If it prints a
link and saves a %PDF, Group 30's RMAP is healthy from your side.

You (the testing group) need:
  - your OWN group's OpenPGP private key          (--client-priv)
  - your identity as registered in the course keys (--identity, e.g. Group_07)
  - Group 30's server public key                   (--server-pub)
        This is Group_30.asc from the shared course key directory
        (same key Group 30 published). Default below assumes that filename.

Depends only on: pip install rmap requests   (rmap: the course RMAP library)

Example:
    python check_group30_rmap.py \
        --identity Group_07 \
        --client-priv keys/Group_07_priv.asc \
        --server-pub  Group_30.asc \
        --client-passphrase 'your-key-passphrase'   # omit if key is unprotected
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests
from rmap import RMAPClient

# Group 30's server. Override with --base if the host/port differs.
DEFAULT_BASE = "http://softsec-group-30.dsv.local.su.se:5000/api"


def main() -> int:
    p = argparse.ArgumentParser(description="Check Group 30's RMAP PDF retrieval.")
    p.add_argument("--identity", required=True,
                   help="YOUR group identity, as registered in the course keys (e.g. Group_07)")
    p.add_argument("--client-priv", required=True, type=Path,
                   help="Path to YOUR group's OpenPGP private key (.asc)")
    p.add_argument("--server-pub", type=Path, default=Path("Group_30.asc"),
                   help="Group 30's server public key (course bundle Group_30.asc)")
    p.add_argument("--client-passphrase", default=os.environ.get("RMAP_CLIENT_KEY_PASSPHRASE"),
                   help="Passphrase for your private key (or set RMAP_CLIENT_KEY_PASSPHRASE)")
    p.add_argument("--base", default=DEFAULT_BASE, help="Target API base URL")
    p.add_argument("--out", type=Path, default=Path("group30_watermarked.pdf"))
    p.add_argument("--timeout", type=float, default=30.0)
    args = p.parse_args()

    for label, path in (("--client-priv", args.client_priv), ("--server-pub", args.server_pub)):
        if not path.exists():
            print(f"[!] {label} not found: {path}", file=sys.stderr)
            return 2

    base = args.base.rstrip("/")
    client = RMAPClient(
        identity=args.identity,
        client_private_key_path=str(args.client_priv),
        server_public_key_path=str(args.server_pub),
        passphrase=args.client_passphrase,
    )

    print(f"[*] rmap-initiate as {args.identity!r} -> {base}/rmap-initiate")
    r1 = requests.post(f"{base}/rmap-initiate", json=client.build_msg1(), timeout=args.timeout)
    if r1.status_code != 200:
        print(f"[!] rmap-initiate failed: {r1.status_code} {r1.text}")
        return 1
    client.process_resp1(r1.json())
    print("    resp1 OK — server decrypted msg1 and echoed the nonce")

    print(f"[*] rmap-get-link -> {base}/rmap-get-link")
    r2 = requests.post(f"{base}/rmap-get-link", json=client.build_msg2(), timeout=args.timeout)
    if r2.status_code != 200:
        print(f"[!] rmap-get-link failed: {r2.status_code} {r2.text}")
        return 1
    link = client.process_resp2(r2.json())
    print(f"    session link: {link}")

    print(f"[*] GET {base}/get-version/{link}")
    pdf = requests.get(f"{base}/get-version/{link}", timeout=args.timeout)
    if pdf.status_code != 200 or pdf.content[:5] != b"%PDF-":
        print(f"[!] download failed: HTTP {pdf.status_code}, first bytes {pdf.content[:16]!r}")
        return 1
    args.out.write_bytes(pdf.content)
    print(f"[+] SUCCESS — saved {len(pdf.content)} bytes to {args.out}")
    print(f"\nGroup 30's RMAP works. link={link}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
