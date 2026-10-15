"""rmap_keycheck.py — diagnose RMAP keypair mismatches.

"Cannot decrypt the provided message with this key" on process_resp1 means
the private key you passed is not the pair of the public key the server used
to encrypt Response 1. The server encrypts to whatever public key it has
stored for your identity (its clients/<Identity>.asc).

This prints the PGP fingerprint of each key so you can see which ones match.
The private key's fingerprint must equal the fingerprint of the public key
the *target server* holds for your identity.

Usage:
    python scripts/rmap_keycheck.py \
        --client-priv keys/your_group_priv.asc \
        --client-passphrase 'secret' \
        --registered-pub keys/clients/Group_19.asc    # the pub the server has for you
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from pgpy import PGPKey


def info(path: Path, passphrase: str | None = None) -> None:
    key, _ = PGPKey.from_file(str(path))
    kind = "PRIVATE" if key.is_public is False else "PUBLIC"
    uids = ", ".join(str(u) for u in key.userids) or "(no uid)"
    print(f"\n{path}")
    print(f"  type:        {kind}")
    print(f"  fingerprint: {key.fingerprint}")
    print(f"  key id:      {key.fingerprint.keyid}")
    print(f"  user ids:    {uids}")
    print(f"  protected:   {key.is_protected}")
    if key.is_protected and passphrase and not key.is_public:
        try:
            with key.unlock(passphrase):
                print("  unlock:      OK (passphrase correct)")
        except Exception as e:
            print(f"  unlock:      FAILED ({e})")


def main() -> int:
    p = argparse.ArgumentParser(description="Compare RMAP key fingerprints.")
    p.add_argument("--client-priv", type=Path, required=True,
                   help="Private key you pass to rmap_fetch (--client-priv)")
    p.add_argument("--registered-pub", type=Path, required=True,
                   help="Public key the server has for your identity (clients/<Identity>.asc)")
    p.add_argument("--client-passphrase", default=os.environ.get("RMAP_CLIENT_KEY_PASSPHRASE"),
                   help="Passphrase for the private key (defaults to RMAP_CLIENT_KEY_PASSPHRASE)")
    args = p.parse_args()

    info(args.client_priv, args.client_passphrase)
    info(args.registered_pub)

    priv, _ = PGPKey.from_file(str(args.client_priv))
    pub, _ = PGPKey.from_file(str(args.registered_pub))
    print("\n" + "=" * 60)
    if priv.fingerprint == pub.fingerprint:
        print("MATCH: private key pairs with the registered public key.")
        print("If decryption still fails, the server may hold a DIFFERENT")
        print("public key for your identity than this --registered-pub file.")
    else:
        print("MISMATCH: these are different keys.")
        print("Response 1 is encrypted to the server's stored public key, which")
        print("this private key cannot decrypt. Use the private key that pairs")
        print("with the public key the server actually has for your identity.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
