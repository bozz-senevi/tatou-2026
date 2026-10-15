#!/usr/bin/env bash
# rmap_fetch_all.sh — sweep Group_1..Group_34 over RMAP and collect links.
#
# For each group N it fetches the watermarked PDF from that group's server,
# encrypting to their published key at $CLIENTS_DIR/Group_N.asc. Groups whose
# key is missing, whose server is unreachable, or whose handshake fails are
# skipped; the sweep keeps going and records the failure.
#
# Run from the repo root (paths below are relative to it):
#     export RMAP_CLIENT_KEY_PASSPHRASE='<your server key passphrase>'
#     bash server/scripts/rmap_fetch_all.sh
#
# Everything is overridable via env vars, e.g.:
#     START=1 END=10 TIMEOUT=10 bash server/scripts/rmap_fetch_all.sh
#
# Results: a CSV at $RESULTS (group,host,status,link,pdf) plus the PDFs in
# $OUT_DIR. The passphrase is read by the python script from
# RMAP_CLIENT_KEY_PASSPHRASE — export it before running.

set -u

# --- config (override via env) ---
FETCH_SCRIPT="${FETCH_SCRIPT:-server/scripts/rmap_fetch.py}"
CLIENT_PRIV="${CLIENT_PRIV:-server/keys/server_priv.asc}"
CLIENTS_DIR="${CLIENTS_DIR:-server/keys/clients}"
IDENTITY="${IDENTITY:-Group_30}"              # our own identity
OUT_DIR="${OUT_DIR:-/tmp/rmap_pdfs}"
RESULTS="${RESULTS:-/tmp/rmap_links.csv}"
HOST_FMT="${HOST_FMT:-softsec-group-%d.dsv.local.su.se}"  # %d = group number
PORT="${PORT:-5000}"
TIMEOUT="${TIMEOUT:-20}"                       # per-request seconds
START="${START:-1}"
END="${END:-34}"
SELF="${SELF:-30}"                             # skip our own group number

mkdir -p "$OUT_DIR"
echo "group,host,status,link,pdf" > "$RESULTS"

ok=0 fail=0 skip=0

for n in $(seq "$START" "$END"); do
    if [ "$n" = "$SELF" ]; then
        echo "[=] Group_$n: skipped (self)"
        skip=$((skip + 1)); continue
    fi

    # Locate this group's public key. Try unpadded then zero-padded names.
    key=""
    for cand in "Group_${n}.asc" "$(printf 'Group_%02d.asc' "$n")"; do
        if [ -f "$CLIENTS_DIR/$cand" ]; then key="$CLIENTS_DIR/$cand"; break; fi
    done
    if [ -z "$key" ]; then
        echo "[-] Group_$n: no public key in $CLIENTS_DIR, skipping"
        echo "$n,,no-key," >> "$RESULTS"
        skip=$((skip + 1)); continue
    fi

    host=$(printf "$HOST_FMT" "$n")
    base="http://${host}:${PORT}/api"
    out="$OUT_DIR/group${n}_confidential.pdf"

    echo "[*] Group_$n -> $base"
    log=$(python "$FETCH_SCRIPT" \
            --base "$base" \
            --identity "$IDENTITY" \
            --client-priv "$CLIENT_PRIV" \
            --server-pub "$key" \
            --out "$out" \
            --timeout "$TIMEOUT" 2>&1)
    rc=$?

    # The python script prints "Done. link=<32hex>" on success.
    link=$(printf '%s\n' "$log" | sed -n 's/^Done\. link=//p' | tail -n1)

    if [ "$rc" -eq 0 ] && [ -n "$link" ]; then
        echo "    OK  link=$link  -> $out"
        echo "$n,$host,ok,$link,$out" >> "$RESULTS"
        ok=$((ok + 1))
    else
        echo "    FAILED (rc=$rc)"
        printf '%s\n' "$log" | tail -n2 | sed 's/^/      /'
        echo "$n,$host,fail,," >> "$RESULTS"
        fail=$((fail + 1))
    fi
done

echo
echo "Summary: ok=$ok fail=$fail skip=$skip"
echo "Links/CSV: $RESULTS"
echo "PDFs:      $OUT_DIR"
