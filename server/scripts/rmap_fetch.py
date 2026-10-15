"""rmap_fetch.py — fetch another group's watermarked PDF over RMAP.

Acts as an RMAP *client* against another group's Tatou server: runs the
four-message handshake (rmap-initiate / rmap-get-link), obtains the 32-hex
session link, then downloads the watermarked PDF from get-version/<link>.

This is the client side of the protocol described in the project's Phase I
addition. It is the right tool both for testing your own instance (point it
at your own server) and for retrieving another group's document (point it at
theirs), as the Phase II announcement asks groups to do.

Prerequisites (same RMAPClient API as scripts/handshake_test.py):
  - YOUR group's private key          (--client-priv)
  - the TARGET server's public key     (--server-pub)
  - your identity must be registered   (--identity, e.g. Group_19)
    in the target server's client key directory, or rmap-initiate returns 400.

Example — fetch from another group on the network:
    python scripts/rmap_fetch.py \
        --base http://softsec-group-21.dsv.local.su.se:5000/api \
        --identity Group_19 \
        --client-priv keys/our_group_priv.asc \
        --server-pub keys/group21_server_pub.asc \
        --out /tmp/group21_confidential.pdf

Example — smoke-test your own instance with the throwaway test identity:
    python scripts/rmap_fetch.py \
        --base http://127.0.0.1:5000/api \
        --identity Group_LIVETEST \
        --client-priv keys/test_client_priv.asc \
        --server-pub keys/server_pub.asc \
        --out /tmp/self_test.pdf
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests
from rmap import RMAPClient


def fetch(base: str, identity: str, client_priv: Path, server_pub: Path,
          out: Path, timeout: float = 30.0, passphrase: str | None = None) -> str:
    """Run the RMAP handshake against ``base`` and save the PDF to ``out``.

    Returns the 32-hex session link on success.
    """
    base = base.rstrip("/")

    # ``passphrase`` unlocks OUR client private key (--client-priv). It is the
    # passphrase on that key file, not the server's. If your group uses one
    # keypair for both roles, it's the same value you set as
    # RMAP_SERVER_KEY_PASSPHRASE in the container.
    client = RMAPClient(
        identity=identity,
        client_private_key_path=str(client_priv),
        server_public_key_path=str(server_pub),
        passphrase=passphrase,
    )

    # --- Message 1 -> Response 1 (identity + nonceClient, echo nonceServer) ---
    print(f"[*] rmap-initiate as {identity!r} -> {base}/rmap-initiate")
    r1 = requests.post(f"{base}/rmap-initiate", json=client.build_msg1(), timeout=timeout)
    if r1.status_code != 200:
        raise SystemExit(f"[!] rmap-initiate failed: {r1.status_code} {r1.text}")
    client.process_resp1(r1.json())
    print("    resp1 OK (server proved it could decrypt msg1)")

    # --- Message 2 -> Response 2 (prove nonceServer, receive link) ---
    print(f"[*] rmap-get-link -> {base}/rmap-get-link")
    r2 = requests.post(f"{base}/rmap-get-link", json=client.build_msg2(), timeout=timeout)
    if r2.status_code != 200:
        raise SystemExit(f"[!] rmap-get-link failed: {r2.status_code} {r2.text}")
    link = client.process_resp2(r2.json())
    print(f"    session link: {link}")

    # --- Download the watermarked PDF via the public get-version route ---
    print(f"[*] GET {base}/get-version/{link}")
    pdf = requests.get(f"{base}/get-version/{link}", timeout=timeout)
    if pdf.status_code != 200:
        raise SystemExit(f"[!] get-version failed: {pdf.status_code} {pdf.text}")
    if pdf.content[:5] != b"%PDF-":
        raise SystemExit(f"[!] response is not a PDF (first bytes: {pdf.content[:16]!r})")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(pdf.content)
    print(f"[+] saved {len(pdf.content)} bytes -> {out}")
    return link


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Fetch a watermarked PDF over RMAP.")
    p.add_argument("--base", required=True,
                   help="Target server API base, e.g. http://host:5000/api")
    p.add_argument("--identity", required=True,
                   help="Your group identity as registered on the target, e.g. Group_19")
    p.add_argument("--client-priv", required=True, type=Path,
                   help="Path to YOUR group's OpenPGP private key (.asc)")
    p.add_argument("--server-pub", required=True, type=Path,
                   help="Path to the TARGET server's OpenPGP public key (.asc)")
    p.add_argument("--out", required=True, type=Path,
                   help="Where to write the downloaded PDF")
    p.add_argument("--client-passphrase", default=os.environ.get("RMAP_CLIENT_KEY_PASSPHRASE"),
                   help="Passphrase for YOUR client private key (--client-priv). "
                        "Defaults to the RMAP_CLIENT_KEY_PASSPHRASE env var; omit if the key is unprotected.")
    p.add_argument("--timeout", type=float, default=30.0,
                   help="Per-request timeout in seconds (default: 30)")
    args = p.parse_args(argv)

    for label, path in (("--client-priv", args.client_priv),
                        ("--server-pub", args.server_pub)):
        if not path.exists():
            print(f"[!] {label} not found: {path}", file=sys.stderr)
            return 2

    link = fetch(args.base, args.identity, args.client_priv,
                 args.server_pub, args.out, args.timeout,
                 passphrase=args.client_passphrase)
    print(f"\nDone. link={link}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
