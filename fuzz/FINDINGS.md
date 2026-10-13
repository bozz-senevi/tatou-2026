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
