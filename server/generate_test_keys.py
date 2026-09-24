from pathlib import Path
from rmap.keygen import generate_keypair

keys_dir = Path("server/keys")
clients_dir = keys_dir / "clients"

keys_dir.mkdir(parents=True, exist_ok=True)
clients_dir.mkdir(parents=True, exist_ok=True)

key = generate_keypair(
    "Group_LIVETEST",
    "livetest@example.com"
)

# Private key used by handshake_test.py
(keys_dir / "test_client_priv.asc").write_text(str(key))

# Public key used by the server to recognize Group_LIVETEST
(clients_dir / "Group_LIVETEST.asc").write_text(str(key.pubkey))

print("Generated:")
print("  server/keys/test_client_priv.asc")
print("  server/keys/clients/Group_LIVETEST.asc")