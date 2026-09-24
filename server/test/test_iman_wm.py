import pymupdf
import pytest

from iman_wm import ImanWM
from watermarking_method import InvalidKeyError, SecretNotFoundError


@pytest.fixture
def real_pdf() -> bytes:
    """A small but real one-page PDF."""
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "hello")
    data = doc.tobytes()
    doc.close()
    return data


def test_roundtrip(real_pdf):
    m = ImanWM()
    out = m.add_watermark(real_pdf, "Group 07", "k1")
    assert m.read_secret(out, "k1") == "Group 07"


def test_wrong_key_rejected(real_pdf):
    m = ImanWM()
    out = m.add_watermark(real_pdf, "Group 07", "k1")
    with pytest.raises(InvalidKeyError):
        m.read_secret(out, "wrong")


def test_unmarked_pdf_has_no_secret(real_pdf):
    with pytest.raises(SecretNotFoundError):
        ImanWM().read_secret(real_pdf, "k1")


def test_deterministic(real_pdf):
    m = ImanWM()
    first = m.add_watermark(real_pdf, "Group 07", "k1")
    second = m.add_watermark(real_pdf, "Group 07", "k1")
    assert first == second


def test_different_secrets_give_different_files(real_pdf):
    m = ImanWM()
    a = m.add_watermark(real_pdf, "Group 07", "k1")
    b = m.add_watermark(real_pdf, "Group 08", "k1")
    assert a != b
