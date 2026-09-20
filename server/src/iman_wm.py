"""iman_wm.py

Fingerprinting watermark. The recipient ID (the "secret") is stored inside
the PDF as an extra object, together with an HMAC computed from the key.
Without the key, nobody can create or change a mark that passes the check.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Final

import pymupdf as fitz  # PyMuPDF

from watermarking_method import (
    InvalidKeyError,
    SecretNotFoundError,
    WatermarkingError,
    WatermarkingMethod,
    PdfSource,
    load_pdf_bytes,
)


class ImanWM(WatermarkingMethod):
    name: Final[str] = "iman-wm"

    # Name of the entry we add to the PDF catalog to point at our object
    _CATALOG_KEY: Final[str] = "ImanWM"
    # Mixed into the HMAC so this method's marks can't be reused elsewhere
    _CONTEXT: Final[bytes] = b"wm:iman-wm:v1:"

    @staticmethod
    def get_usage() -> str:
        return ("Stores the secret plus an HMAC (made with the key) in an extra "
                "PDF object linked from the catalog. Position is ignored.")

    def is_watermark_applicable(self, pdf: PdfSource, position: str | None = None) -> bool:
        # Applicable if PyMuPDF can open the PDF and it is not password-protected
        try:
            doc = fitz.open(stream=load_pdf_bytes(pdf), filetype="pdf")
            ok = (not doc.needs_pass) and doc.page_count > 0
            doc.close()
            return ok
        except Exception:
            return False

    def add_watermark(self, pdf: PdfSource, secret: str, key: str, position: str | None = None) -> bytes:
        data = load_pdf_bytes(pdf)
        if not secret:
            raise ValueError("Secret must be a non-empty string")
        if not isinstance(key, str) or not key:
            raise ValueError("Key must be a non-empty string")

        try:
            doc = fitz.open(stream=data, filetype="pdf")
        except Exception as exc:
            raise WatermarkingError("Could not open PDF") from exc
        try:
            if doc.needs_pass:
                raise WatermarkingError("PDF is password-protected")
            payload = self._build_payload(secret, key)
            # 1. create a new empty object and put the payload in its stream
            xref = doc.get_new_xref()
            doc.update_object(xref, "<<>>")
            doc.update_stream(xref, payload, new=True)
            # 2. link it from the catalog so it is part of the document
            doc.xref_set_key(doc.pdf_catalog(), self._CATALOG_KEY, f"{xref} 0 R")
            return doc.tobytes()
        finally:
            doc.close()

    def read_secret(self, pdf: PdfSource, key: str) -> str:
        data = load_pdf_bytes(pdf)
        if not isinstance(key, str) or not key:
            raise ValueError("Key must be a non-empty string")

        try:
            doc = fitz.open(stream=data, filetype="pdf")
        except Exception as exc:
            raise WatermarkingError("Could not open PDF") from exc
        try:
            kind, value = doc.xref_get_key(doc.pdf_catalog(), self._CATALOG_KEY)
            if kind != "xref":
                raise SecretNotFoundError("No iman-wm watermark found")
            payload = doc.xref_stream(int(value.split()[0]))
            if not payload:
                raise SecretNotFoundError("Watermark object is empty")
            return self._check_payload(payload, key)
        finally:
            doc.close()

    # ---------------------
    # Internal helpers
    # ---------------------

    def _mac_hex(self, secret_bytes: bytes, key: str) -> str:
        """HMAC-SHA256 over the secret, using the key."""
        return hmac.new(key.encode("utf-8"), self._CONTEXT + secret_bytes,
                        hashlib.sha256).hexdigest()

    def _build_payload(self, secret: str, key: str) -> bytes:
        """Compact JSON holding the secret (base64) and its MAC. Deterministic."""
        secret_bytes = secret.encode("utf-8")
        obj = {
            "v": 1,
            "mac": self._mac_hex(secret_bytes, key),
            "secret": base64.b64encode(secret_bytes).decode("ascii"),
        }
        return json.dumps(obj, separators=(",", ":")).encode("ascii")

    def _check_payload(self, payload: bytes, key: str) -> str:
        """Parse the payload and verify the MAC; return the secret."""
        try:
            obj = json.loads(payload)
            mac_hex = str(obj["mac"])
            secret_bytes = base64.b64decode(str(obj["secret"]))
        except Exception as exc:
            raise SecretNotFoundError("Malformed watermark payload") from exc
        if not hmac.compare_digest(mac_hex, self._mac_hex(secret_bytes, key)):
            raise InvalidKeyError("Key failed to authenticate the watermark")
        return secret_bytes.decode("utf-8")


__all__ = ["ImanWM"]
