# Test coverage report — Tatou (Group 30)

This folder holds the group's test artifacts for the final hand-in:

- `coverage/` — the HTML test coverage report (open `coverage/index.html`).
- `specification_test_mapping.html` — the specification-to-test traceability matrix.

## How to regenerate the coverage report

The suite has two kinds of tests (see the mapping for which is which):

- **In-process tests** run with a plain `pytest` — the watermarking methods, the
  interface conformance, the fuzzing regression guards, and the auth/server unit
  tests.
- **Live-server tests** (`test_api_findings.py`, findings C1–C3) are black-box HTTP
  tests that need the stack running, and they cover the `server.py` request paths.

To produce the **complete** report, bring the stack up first so the live-server
tests run and `server.py` is covered:

```bash
# from the repo root
docker compose up -d --build          # start the stack (DB + server on :5000)

cd server
pip install pytest pytest-cov
TATOU_BASE=http://localhost:5000 \
PYTHONPATH=src python -m pytest test/ \
    --cov=src \
    --cov-report=html:../artifacts/common/coverage \
    --cov-report=term-missing
```

For a quick **methods-only** report without the stack (what is committed here as a
starting point), run the in-process tests only:

```bash
cd server
PYTHONPATH=src python -m pytest \
    test/test_watermarking_all_methods.py \
    test/test_iman_wm.py \
    test/test_iman_wm_redundancy.py \
    test/test_fuzz_findings.py \
    --cov=src --cov-report=html:../artifacts/common/coverage --cov-report=term-missing
```

## What the committed report currently reflects

The `coverage/` report in this folder was generated from the **in-process** unit tests (the watermarking methods, interface conformance, and fuzzing regression guards), which is why those modules are well covered and `server.py` reads low here. `server.py` is exercised mainly through the API tests (`test_api.py` in-process and `test_api_findings.py` over HTTP), but measuring its coverage must be done in the server's own runtime: the application imports `rmap`, which depends on a standard-library module removed in Python 3.13, so the server code only loads under Python 3.12 (the version used inside the Docker image). On a host running Python 3.13 or newer the server module cannot be imported, so host-side coverage captures the method layer only. To measure `server.py` coverage, run the suite inside the container (Python 3.12).

In-process snapshot (branch `main`):

| Module | Coverage |
|---|---|
| `iman_wm.py` | 79% |
| `add_after_eof.py` | 81% |
| `sussann_watermark.py` | 78% |
| `watermarking_method.py` | 80% |
| `stealth_invisible_watermark.py` | 29% |
| `watermarking_utils.py` | 41% |
| `server.py` | measured inside the container (Python 3.12) |

> Note: `test_api.py` uses Flask's in-process test client and would add `server.py`
> coverage, but importing `server` needs the full runtime dependencies (including
> `rmap`/`pgpy`), which is why it is cleanest to generate the full report on the
> running stack rather than in a bare environment.
