"""Regression tests for the fuzzing findings (Specialization A).

Each test encodes the CONTRACT a finding violates:
  - fails on the current (buggy) code  -> documents the bug
  - passes once the fix in FINDINGS.md is applied -> guards against regression
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from watermarking_utils import apply_watermark, read_watermark
from watermarking_method import WatermarkingError, SecretNotFoundError, InvalidKeyError

MINIMAL_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
    b"trailer<</Root 1 0 R/Size 4>>\n%%EOF\n"
)

OK_ADD = (ValueError, WatermarkingError)


# --- Bug A: sussann must preserve a secret containing control bytes ---
def test_bugA_sussann_preserves_control_bytes():
    s = "a\x00b\x01c"
    wm = apply_watermark(method="sussann-watermark", pdf=MINIMAL_PDF, secret=s, key="key123")
    back = read_watermark(method="sussann-watermark", pdf=wm, key="key123")
    assert back == s, f"secret corrupted: wrote {s!r}, read {back!r}"


# --- Bug B: methods must only raise declared types on malformed input ---
@pytest.mark.parametrize("method", ["sussann-watermark", "iman-wm", "toy-eof"])
def test_bugB_add_watermark_wraps_exceptions(method):
    garbage = b"%PDF-1.4\n" + bytes(range(256)) * 3
    try:
        apply_watermark(method=method, pdf=garbage, secret="test", key="key123")
    except OK_ADD:
        pass  # declared types are fine
    except Exception as e:  # anything else = contract violation
        pytest.fail(f"{method} leaked {type(e).__name__}: {e}")


# --- Positive guard: valid round-trips must still work after any fix ---
@pytest.mark.parametrize("method", ["iman-wm", "toy-eof"])
def test_valid_roundtrip_still_works(method):
    wm = apply_watermark(method=method, pdf=MINIMAL_PDF, secret="hello", key="key123")
    assert read_watermark(method=method, pdf=wm, key="key123") == "hello"
