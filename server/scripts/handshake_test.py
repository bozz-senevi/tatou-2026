"""Manual smoke test for the RMAP endpoints (rmap-initiate, rmap-get-link).

Plays the role of "another group" talking to this server over HTTP, using
the throwaway test identity Group_LIVETEST (its public key already lives
at server/keys/clients/Group_LIVETEST.asc; its private key at
server/keys/test_client_priv.asc -- neither is committed, server/keys/ is
gitignored).

Requires the server to already be running (docker compose up -d) and
reachable at BASE below. Run with:

    cd server && . .venv/bin/activate
    python scripts/handshake_test.py
"""
from pathlib import Path
import requests
from rmap import RMAPClient
from rmap.keygen import generate_keypair

REPO = Path(__file__).resolve().parent.parent.parent
KEYS_DIR = REPO / "server" / "keys"
BASE = "http://127.0.0.1:5000/api"

SERVER_PUB = KEYS_DIR / "server_pub.asc"
CLIENT_PRIV = KEYS_DIR / "test_client_priv.asc"
identity = "Group_LIVETEST"

client = RMAPClient(identity=identity, client_private_key_path=CLIENT_PRIV, server_public_key_path=SERVER_PUB)

print("=== msg1 / resp1 ===")
r1 = requests.post(f"{BASE}/rmap-initiate", json=client.build_msg1())
print("rmap-initiate status:", r1.status_code)
r1.raise_for_status()
client.process_resp1(r1.json())

print("=== msg2 / resp2 (first, real request) ===")
msg2 = client.build_msg2()  # capture the exact wire message once
r2 = requests.post(f"{BASE}/rmap-get-link", json=msg2)
print("rmap-get-link status:", r2.status_code)
r2.raise_for_status()
link1 = client.process_resp2(r2.json())
print("link:", link1)

print("\n=== get-version on the fresh link ===")
pdf = requests.get(f"{BASE}/get-version/{link1}")
print("status:", pdf.status_code, "bytes:", len(pdf.content), "is-pdf:", pdf.content[:5] == b"%PDF-")
assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"

print("\n=== Replay: resending the exact same captured msg2 bytes ===")
r2_replay = requests.post(f"{BASE}/rmap-get-link", json=msg2)
print("status:", r2_replay.status_code)
print("body ok to decrypt:", end=" ")
try:
    link_replay = client.process_resp2(r2_replay.json())
    print("yes, link:", link_replay, "matches original:", link_replay == link1)
except Exception as e:
    print("no -", e)

print("\n=== Second independent handshake for the SAME identity (fresh nonces) ===")
client2 = RMAPClient(identity=identity, client_private_key_path=CLIENT_PRIV, server_public_key_path=SERVER_PUB)
r1b = requests.post(f"{BASE}/rmap-initiate", json=client2.build_msg1())
client2.process_resp1(r1b.json())
r2b = requests.post(f"{BASE}/rmap-get-link", json=client2.build_msg2())
link2 = client2.process_resp2(r2b.json())
print("second link:", link2, "differs from first:", link2 != link1)

print("\n=== Negative: unknown identity ===")
evil_key = generate_keypair("Group_EVIL", "evil@example.com")
evil_priv = KEYS_DIR / "_evil_test_priv.asc"
evil_priv.write_text(str(evil_key))
evil_client = RMAPClient(identity="Group_EVIL", client_private_key_path=evil_priv, server_public_key_path=SERVER_PUB)
r_evil = requests.post(f"{BASE}/rmap-initiate", json=evil_client.build_msg1())
print("status:", r_evil.status_code, r_evil.json())
evil_priv.unlink(missing_ok=True)

print("\n=== Negative: malformed payload ===")
r_bad = requests.post(f"{BASE}/rmap-initiate", json={"nope": "bad"})
print("status:", r_bad.status_code, r_bad.json())