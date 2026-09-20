import pymupdf
import pytest

from iman_wm import ImanWM
from watermarking_method import SecretNotFoundError


@pytest.fixture
def marked_pdf() -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "hello")
    data = doc.tobytes()
    doc.close()
    return ImanWM().add_watermark(data, "Group 07", "k1")


def _strip(pdf_bytes: bytes, where: str) -> bytes:
    """Simulate an attacker removing one hiding place."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    if where == "catalog":
        doc.xref_set_key(doc.pdf_catalog(), "ImanWM", "null")
    else:  # "info": wipe the whole metadata dictionary
        doc.xref_set_key(-1, "Info", "null")
    out = doc.tobytes()
    doc.close()
    return out


@pytest.mark.parametrize("where", ["catalog", "info"])
def test_survives_removal_of_one_location(marked_pdf, where):
    stripped = _strip(marked_pdf, where)
    assert ImanWM().read_secret(stripped, "k1") == "Group 07"


def test_removing_both_locations_removes_the_mark(marked_pdf):
    both = _strip(_strip(marked_pdf, "catalog"), "info")
    with pytest.raises(SecretNotFoundError):
        ImanWM().read_secret(both, "k1")
