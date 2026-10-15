#!/usr/bin/env python3
"""One-off: generate everything needed for local RMAP testing.

Writes two independent keypairs into server/keys/ (gitignored, never
committed):

  1. This machine's own server keypair (server_pub.asc / server_priv.asc)
     -- used by the local server to receive and reply to handshakes.
  2. A throwaway test identity (default name: Group_LIVETEST) -- used by
     scripts/handshake_test.py to pretend to be "another group" testing
     against this same local server.

Both are self-contained to this machine: nothing here needs to be
shared with or copied from anyone else's copy of the repo.

Run once, from server/:
    .venv/bin/python scripts/setup_test_keys.py

Optionally pick a different test identity name:
    .venv/bin/python scripts/setup_test_keys.py MyTestGroup
"""
import sys
from pathlib import Path
from rmap.keygen import generate_keypair

KEYS_DIR = Path(__file__).resolve().parent.parent / "keys"


def main() -> None:
    identity = sys.argv[1] if len(sys.argv) > 1 else "Group_LIVETEST"

    KEYS_DIR.mkdir(parents=True, exist_ok=True)
    (KEYS_DIR / "clients").mkdir(exist_ok=True)

    server_priv_path = KEYS_DIR / "server_priv.asc"
    server_pub_path = KEYS_DIR / "server_pub.asc"
    client_priv_path = KEYS_DIR / "test_client_priv.asc"
    client_pub_path = KEYS_DIR / "clients" / f"{identity}.asc"

    if server_priv_path.exists() or server_pub_path.exists():
        print(f"Server keypair already exists in {KEYS_DIR}, skipping.")
    else:
        server_key = generate_keypair("Tatou Server", "server@tatou.local")
        server_priv_path.write_text(str(server_key))
        server_pub_path.write_text(str(server_key.pubkey))
        server_priv_path.chmod(0o600)
        print(f"Wrote {server_priv_path}")
        print(f"Wrote {server_pub_path}")

    if client_priv_path.exists() or client_pub_path.exists():
        print(f"Test identity '{identity}' already exists, skipping.")
    else:
        client_key = generate_keypair(identity, "test@example.com")
        client_priv_path.write_text(str(client_key))
        client_pub_path.write_text(str(client_key.pubkey))
        client_priv_path.chmod(0o600)
        print(f"Wrote {client_priv_path}")
        print(f"Wrote {client_pub_path}")

    print("\nDone. Restart the server (docker compose restart server) so it")
    print("picks up the new client identity, then run scripts/handshake_test.py.")


if __name__ == "__main__":
    main()
