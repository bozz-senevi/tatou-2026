"""iman_wm.py

Fingerprinting watermark. The recipient ID (the "secret") is stored in THREE
independent places inside the PDF, each protected with an HMAC made from the
key:
  1. an extra stream object linked from the document catalog
  2. a custom entry in the Info (metadata) dictionary
  3. invisible text on every page (PDF text render mode 3: present in the
     page content, extractable, but not drawn on screen or in print)
read_secret tries all three, so removing any one or two locations does not
remove the mark. Without the key, nobody can create or change a mark that
passes the check.
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

    _CATALOG_KEY: Final[str] = "ImanWM"    # entry in the catalog -> our object
    _INFO_KEY: Final[str] = "ImanWM"       # entry in the Info dictionary
    _MARKER: Final[str] = "\u2063"         # invisible unicode char that wraps our text mark
    # Mixed into the HMAC so this method's marks can't be reused elsewhere
    _CONTEXT: Final[bytes] = b"wm:iman-wm:v1:"

    @staticmethod
    def get_usage() -> str:
        return ("Stores the secret plus an HMAC (made with the key) in three "
                "places: an extra PDF object linked from the catalog, a "
                "custom Info-dictionary entry, and invisible text on every "
                "page. Position is ignored.")

    def is_watermark_applicable(self, pdf: PdfSource, position: str | None = None) -> bool:
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
            self._write_catalog(doc, payload)
            self._write_info(doc, payload)
            self._write_page_text(doc, payload)
            # no_new_id keeps the output deterministic (same input -> same bytes)
            return doc.tobytes(no_new_id=True)
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
            last_error: Exception | None = None
            for reader in (self._read_catalog, self._read_info, self._read_page_text):
                payload = reader(doc)
                if payload is None:
                    continue
                try:
                    return self._check_payload(payload, key)
                except (InvalidKeyError, SecretNotFoundError) as exc:
                    last_error = exc
            if last_error is not None:
                raise last_error
            raise SecretNotFoundError("No iman-wm watermark found")
        finally:
            doc.close()

    # ---------------------
    # Location 1: catalog -> extra stream object
    # ---------------------

    def _write_catalog(self, doc, payload: bytes) -> None:
        xref = doc.get_new_xref()
        doc.update_object(xref, "<<>>")
        doc.update_stream(xref, payload, new=True)
        doc.xref_set_key(doc.pdf_catalog(), self._CATALOG_KEY, f"{xref} 0 R")

    def _read_catalog(self, doc) -> bytes | None:
        try:
            kind, value = doc.xref_get_key(doc.pdf_catalog(), self._CATALOG_KEY)
            if kind != "xref":
                return None
            return doc.xref_stream(int(value.split()[0])) or None
        except Exception:
            return None

    # ---------------------
    # Location 2: custom entry in the Info dictionary
    # ---------------------

    def _write_info(self, doc, payload: bytes) -> None:
        text = "(" + base64.urlsafe_b64encode(payload).decode("ascii") + ")"
        kind, value = doc.xref_get_key(-1, "Info")   # -1 = the trailer
        if kind == "xref":
            doc.xref_set_key(int(value.split()[0]), self._INFO_KEY, text)
        elif kind == "dict":
            doc.xref_set_key(-1, f"Info/{self._INFO_KEY}", text)
        else:
            new = doc.get_new_xref()
            doc.update_object(new, "<<>>")
            doc.xref_set_key(-1, "Info", f"{new} 0 R")
            doc.xref_set_key(new, self._INFO_KEY, text)

    def _read_info(self, doc) -> bytes | None:
        try:
            kind, value = doc.xref_get_key(-1, "Info")
            if kind == "xref":
                kind, value = doc.xref_get_key(int(value.split()[0]), self._INFO_KEY)
            elif kind == "dict":
                kind, value = doc.xref_get_key(-1, f"Info/{self._INFO_KEY}")
            else:
                return None
            if kind != "string":
                return None
            return base64.urlsafe_b64decode(value)
        except Exception:
            return None

    # ---------------------
    # Location 3: invisible text on every page
    # ---------------------

    def _write_page_text(self, doc, payload: bytes) -> None:
        # Wrap the base64 payload between two invisible marker characters so
        # we can find it back even among other page text.
        text = self._MARKER + base64.urlsafe_b64encode(payload).decode("ascii") + self._MARKER
        for page in doc:
            # render_mode=3 means "invisible": the text is in the content
            # stream and extractable, but nothing is drawn.
            page.insert_text((0, 10), text, fontsize=1, render_mode=3)

    def _read_page_text(self, doc) -> bytes | None:
        try:
            for page in doc:
                full_text = page.get_text()
                start = full_text.find(self._MARKER)
                if start == -1:
                    continue
                end = full_text.find(self._MARKER, start + len(self._MARKER))
                if end == -1:
                    continue
                b64 = full_text[start + len(self._MARKER):end]
                return base64.urlsafe_b64decode(b64)
            return None
        except Exception:
            return None

    # ---------------------
    # Payload helpers
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
