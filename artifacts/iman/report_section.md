# Phase II Specialization: Fuzzing (Iman)

## Objective
Design and run a fuzzing campaign against Tatou to find robustness and
correctness problems, triage them, fix the real bugs, and lock the fixes in
with regression tests. I ran the campaign at two levels — the watermarking
methods directly, and the HTTP API — because they fail in different ways and
together cover the stack an attacker actually reaches.

## Level 1 — Method fuzzing
A structure-aware mutation fuzzer (`fuzz_methods.py`) starts from a valid PDF,
applies random byte mutations, and drives every registered method through the
same apply/read entry points the server uses. The key design decision is the
oracle: a finding is (1) a method raising an exception outside the types its
interface declares, or (2) a broken round-trip, where a secret does not read
back identically. The second criterion is what separates this from a crash-only
campaign. The run is deterministic (fixed seed).

Findings:
- Bug A (HIGH): sussann-watermark silently corrupts secrets containing control
  bytes. It stored the secret in the PDF Keywords metadata, which only keeps
  printable text, so bytes like \x00 were dropped on save and the secret read
  back wrong — with no exception. Only the round-trip oracle caught it. Root
  cause compounded by the method not binding the key to the secret (it checks
  only a key hash), so corruption passed the key check. Fixed by base64-encoding
  the secret before storing and decoding on read.
- Bug B (MEDIUM): sussann-watermark and my own iman-wm leaked raw PyMuPDF
  exceptions (FzError*, FileDataError) out of add_watermark, violating the
  interface contract and surfacing as HTTP 500s. Fixed by wrapping the calls so
  failures become WatermarkingError.

## Level 2 — API fuzzing
An HTTP-level fuzzer (`fuzz_api.py`) registers a user, authenticates, uploads a
document, and injects malformed values one field at a time into the
authenticated endpoints — reaching past authentication, JSON parsing, and input
validation. The oracle flags any 5xx response or internal error string leaked in
the body.

Findings in create-watermark:
- C1 (HIGH): a non-string field (e.g. a JSON object) crashes the endpoint with
  an unhandled 500. Fix: type-check inputs, return 400.
- C2 (MEDIUM): an empty secret/key passes the isinstance check, reaches the
  method, and returns 500 instead of 400. Fix: reject empty strings at validation.
- C3 (MEDIUM): database errors return the raw pymysql message to the client
  (information leak). Fix: log server-side, return a generic error; handle a
  duplicate link as 409.

## What I changed as a result
Fixed both method-level bugs on my branch (base64 for sussann, exception
wrapping for sussann and iman-wm) and added one regression test per finding;
they failed on the original code and pass after the fixes. The three API-level
bugs all live in server.py (owned and co-edited by teammates); I reported them
with concrete fixes, verified those fixes locally (all four API regression tests
pass against the patched server), and submitted them as PR #15 for review rather
than editing the shared file unilaterally.

## Limitations
Mutation is random, not coverage-guided; a coverage-guided fuzzer (Atheris)
would likely reach deeper paths. The RMAP endpoints and upload handling were out
of scope. stealth-invisible produced no findings — possibly robust, possibly
under-exercised by the seed, which I can't distinguish without coverage data.

## Artifacts
fuzz_methods.py, fuzz_api.py, results.txt, api_results.txt, FINDINGS.md,
test_fuzz_findings.py, test_api_findings.py (this folder); the runnable copies
live in the repo at fuzz/ and server/test/.
