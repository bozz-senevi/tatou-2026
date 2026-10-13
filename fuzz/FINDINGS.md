# Fuzzing Findings — Specialization A (Iman)

**Target:** Tatou watermarking methods, via `watermarking_utils.METHODS`
(`toy-eof`, `iman-wm`, `sussann-watermark`, `stealth-invisible-watermark`).
**Fuzzer:** `fuzz/fuzz_methods.py` — structure-aware mutation fuzzer.
**Seed:** a minimal valid PDF, byte-mutated each iteration (fixed RNG seed 1337,
so every run reproduces). 1000 iterations/run.
**Oracle (what counts as a failure):**
1. `add_watermark`/`read_secret` raises anything other than the types the
   interface declares (`ValueError`, `WatermarkingError` and subclasses).
2. Round-trip breaks: a secret written by `add_watermark` does not read back
   identically via `read_secret`.

Raw results are in `fuzz/results.txt`. The 5 output lines group into 2 root causes.

---

## Bug A — sussann-watermark silently corrupts secrets (HIGH)

**Observed:** `wrote 'a\x00b\x01c' but read 'a·b·c'` (230 hits/run).

**Root cause:** `SussannWatermark` stores the secret in the PDF metadata
`keywords` field. PDF metadata is a text field, so non-printable bytes are
replaced on serialization. The exact secret is unrecoverable.

**Why it's real / why it matters:** no exception is raised — the method reports
success and returns the wrong secret. A watermark that cannot reproduce its own
payload fails the platform's core guarantee (fingerprint traceability). A
crash-only fuzzer would never see this; the round-trip oracle caught it.

**Severity:** HIGH — correctness/integrity, silent.

**Fix:** encode the secret (e.g. base64) before storing, decode on read — as
`toy-eof` and `iman-wm` already do.

---

## Bug B — raw PyMuPDF exceptions leak from add_watermark (MEDIUM)

**Observed (4 crash signatures):**
- `sussann-watermark → FileDataError: Failed to open stream` (17 hits)
- `sussann-watermark → FzErrorSyntax: invalid key in dict` (3 hits)
- `iman-wm → FzErrorArgument: not a dict (null)` (3 hits)
- `iman-wm → FzErrorFormat: malformed page tree` (2 hits)

**Root cause:** on malformed PDF bytes, PyMuPDF raises its own exception types
(`FzError*`, `FileDataError`). Neither method wraps these, so they escape
`add_watermark` directly, violating the interface contract in
`watermarking_method.py` (which declares only `ValueError`/`WatermarkingError`).

**Why it matters:** in `server.py`, `create_watermark` turns an unexpected
exception into an HTTP 500 that echoes the raw library string — a robustness
failure and an information leak. Callers cannot tell "bad input" from "server
broke".

**Severity:** MEDIUM — robustness + contract violation. (`iman-wm` only leaks on
already-malformed input; on valid PDFs it round-trips every secret correctly.)

**Fix:** wrap each method body: re-raise `ValueError`/`WatermarkingError`,
convert any other exception to `WatermarkingError` (or `SecretNotFoundError` in
`read_secret`).

---

## Limitations of this campaign

- The fuzzer targets the watermarking methods directly (the most
  PDF-parsing-heavy, "interesting" code), not the HTTP API surface. This was a
  deliberate scope choice; a complementary API-level pass (auth + JSON layers)
  is future work.
- Mutation is random, not coverage-guided; a coverage-guided fuzzer
  (Atheris/libFuzzer) would likely reach deeper paths.
- `stealth-invisible-watermark` produced no findings in this campaign — either
  robust to these inputs, or under-exercised by this seed.

---

# API-level findings (fuzz/fuzz_api.py)

A second campaign fuzzed the HTTP API past authentication and JSON parsing:
register a user, log in, upload a document, then inject malformed values one
field at a time into the authenticated endpoints. Oracle: any 5xx response, or
an internal error string leaked in the body. Raw output in `fuzz/api_results.txt`.

## Bug C1 - non-string field crashes create-watermark (HTTP 500) (HIGH)

Observed: `intended_for = {"x":"y"}` -> HTML `500 Internal Server Error`.
Root cause: `create_watermark` checks `if not intended_for` (a dict is truthy,
so it passes) but never checks the type; a non-string then breaks downstream
filename handling with an uncaught exception.
Impact: an authenticated client crashes the endpoint with a well-formed request.
Fix: require `isinstance(intended_for, str)` and return 400 otherwise.

## Bug C2 - empty string bypasses validation, 500 instead of 400 (MEDIUM)

Observed: `key = ""` or `secret = ""` -> `500 "watermarking failed: Key/Secret
must be a non-empty string"`.
Root cause: validation uses `isinstance(key, str)`, which accepts `""`; the empty
value reaches the method, which raises `ValueError`, and the generic handler
turns a bad-input case into a 500.
Impact: bad input reported as a server error (wrong status) and internal message
leaked.
Fix: reject empty strings at validation time (400); catch method `ValueError` as
400, not 500.

## Bug C3 - raw database error leaked to client (MEDIUM, info-leak)

Observed: `503 "database error during version insert: (pymysql.err.
IntegrityError) (1062, 'Duplicate entry ...')"`.
Root cause: `create_watermark` returns the raw exception string on DB errors.
The duplicate arises because the version `link` is `sha1(filename)`, and repeated
requests for the same document produce colliding filenames/links.
Honest caveat: the collision was provoked by the fuzzer reusing one document; a
normal client would not trivially hit it. The leak of raw pymysql internals to
the client is the real standalone finding.
Fix: log DB errors server-side and return a generic message; handle a duplicate
link deterministically (reuse or 409) instead of a raw 503.

## Note

All three live in `server.py`, which is owned/edited by other group members and
currently carries the SQLi/IDOR fixes. These are reported with recommended fixes
and flagged to the team rather than patched here, to avoid colliding with that
work.
