# Specialization A — Fuzzing (Iman · iman-prog)

My Phase II specialization: a fuzzing campaign against Tatou, run at two levels.

## Contents
- `fuzz_methods.py`       — method-level mutation fuzzer (watermarking methods)
- `fuzz_api.py`           — API-level fuzzer (HTTP endpoints, past auth + validation)
- `results.txt`          — raw findings from the method fuzzer
- `api_results.txt`      — raw findings from the API fuzzer
- `FINDINGS.md`          — triaged findings: root cause, severity, fix per bug
- `test_fuzz_findings.py` — regression tests for the method-level findings
- `test_api_findings.py`  — regression tests for the API-level findings (C1–C3)

The runnable, path-correct copies live in the repo at `fuzz/` and
`server/test/`; the files here are the collected snapshot for grading.

## How to run (from the repo)
Method fuzzer (no server needed):
    cd server
    pip install pymupdf --break-system-packages
    TATOU_SRC=$PWD/src python3 ../fuzz/fuzz_methods.py 2>/dev/null | grep -E "CRASH|ROUNDTRIP" | sort | uniq -c

Method regression tests:
    cd server
    TATOU_SRC=$PWD/src python3 -m pytest test/test_fuzz_findings.py -v

API fuzzer + API tests (stack running: `docker compose up -d`):
    python3 fuzz/fuzz_api.py
    cd server && python3 -m pytest test/test_api_findings.py -v

## Findings summary
Method level:
- Bug A (HIGH): sussann-watermark silently corrupts secrets containing control
  bytes (stored raw in PDF metadata). Caught by the round-trip oracle. Fixed with base64.
- Bug B (MED): sussann + iman-wm leaked raw PyMuPDF exceptions from add_watermark,
  violating the interface contract. Fixed by wrapping as WatermarkingError.

API level (create-watermark):
- C1 (HIGH): a non-string field crashes the endpoint with a 500.
- C2 (MED): an empty secret/key returns 500 instead of 400.
- C3 (MED): database errors leak the raw pymysql message to the client.
C1–C3 fixes proposed in PR #15; verified locally (all 4 API tests pass).

After fixes: the method fuzzer reports 0 findings and all regression tests pass.
