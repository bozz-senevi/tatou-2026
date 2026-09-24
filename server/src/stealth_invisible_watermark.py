"""stealth_invisible_watermark.py

Watermarking method that embeds an HMAC-authenticated secret through two
structurally independent PDF channels, so that a stripping technique
aimed at one channel does not remove the other:

1. Invisible text (PDF text-rendering mode 3 -- present in the content
   stream and extractable via normal text-extraction tools, but never
   rendered visibly by any viewer) duplicated on every page, so cropping
   or extracting a subset of pages still carries a copy.
2. The document's ``/Keywords`` metadata field -- fully independent of
   the content stream, so a tool that strips invisible text runs (or
   flattens pages to images) does not touch it, and vice versa.

Both channels carry the exact same authenticated token (HMAC-SHA256 over
the secret, keyed by the caller-provided ``key``, same envelope shape as
:mod:`add_after_eof`), so recovering either channel is sufficient, and
whichever one is found is verified identically.

Security note
-------------
Like ``add_after_eof``, this does not encrypt the secret -- it is
base64-encoded and HMAC-authenticated. This is not a claim of perfect
robustness: an attacker who rasterizes every page to a flat image and
rebuilds the PDF from scratch would defeat both channels. The goal is
"expensive and detectable to strip without also destroying the
document," not an absolute guarantee.
"""
from __future__ import annotations

from typing import Final
import base64
import hashlib
import hmac
import json
import re

import fitz  # PyMuPDF

from watermarking_method import (
    InvalidKeyError,
    PdfSource,
    SecretNotFoundError,
    WatermarkingError,
    WatermarkingMethod,
    load_pdf_bytes,
)


class StealthInvisibleWatermark(WatermarkingMethod):
    """Dual-channel invisible-text + metadata watermarking method."""

    name: Final[str] = "stealth-invisible"

    # Plain ASCII delimiters on purpose: invisibility comes from
    # render_mode=3, not from the character choice. An exotic Unicode
    # delimiter (e.g. U+2063 INVISIBLE SEPARATOR) is *not* in the base
    # font's glyph set, and a full PDF re-save silently substitutes it
    # with a different, visually-similar glyph -- breaking exact-match
    # recovery. Confirmed by testing: plain ASCII survives a re-save,
    # the exotic codepoint did not.
    _MARK_PREFIX: Final[str] = "~~WMBEGIN~~:"
    _MARK_SUFFIX: Final[str] = ":~~WMEND~~"
    _KEYWORDS_PREFIX: Final[str] = "wm:"
    _CONTEXT: Final[bytes] = b"wm:stealth-invisible:v1:"

    # ---------------------
    # Public API overrides
    # ---------------------

    @staticmethod
    def get_usage() -> str:
        return (
            "Embeds an authenticated secret twice: invisible text (render "
            "mode 3) on every page, and the document's Keywords metadata "
            "field. Position is ignored."
        )

    def add_watermark(
        self,
        pdf: PdfSource,
        secret: str,
        key: str,
        position: str | None = None,
    ) -> bytes:
        data = load_pdf_bytes(pdf)
        if not secret:
            raise ValueError("Secret must be a non-empty string")
        if not isinstance(key, str) or not key:
            raise ValueError("Key must be a non-empty string")

        token = self._build_token(secret, key)

        try:
            doc = fitz.open(stream=data, filetype="pdf")
        except Exception as exc:
            raise WatermarkingError(f"Failed to open PDF: {exc}") from exc

        try:
            marked_text = f"{self._MARK_PREFIX}{token}{self._MARK_SUFFIX}"
            for page in doc:
                # Tiny and invisible (render_mode=3): present in the
                # content stream and extractable as text, but never
                # painted by any viewer. Tucked near the origin so it
                # can never visually intrude even if render_mode were
                # ignored by some non-conformant reader.
                page.insert_text(
                    (2, 10),
                    marked_text,
                    fontsize=1,
                    render_mode=3,
                )

            meta = dict(doc.metadata or {})
            existing_keywords = meta.get("keywords") or ""
            kept = [
                part for part in existing_keywords.split(",")
                if part.strip() and not part.strip().startswith(self._KEYWORDS_PREFIX)
            ]
            kept.append(f"{self._KEYWORDS_PREFIX}{token}")
            meta["keywords"] = ",".join(kept)
            doc.set_metadata(meta)

            out = doc.tobytes(garbage=0, deflate=True)
        except Exception as exc:
            raise WatermarkingError(f"Failed to embed watermark: {exc}") from exc
        finally:
            doc.close()

        return out

    def is_watermark_applicable(
        self,
        pdf: PdfSource,
        position: str | None = None,
    ) -> bool:
        data = load_pdf_bytes(pdf)
        try:
            doc = fitz.open(stream=data, filetype="pdf")
        except Exception:
            return False
        try:
            return doc.page_count > 0
        finally:
            doc.close()

    def read_secret(self, pdf: PdfSource, key: str) -> str:
        data = load_pdf_bytes(pdf)
        if not isinstance(key, str) or not key:
            raise ValueError("Key must be a non-empty string")

        try:
            doc = fitz.open(stream=data, filetype="pdf")
        except Exception as exc:
            raise SecretNotFoundError(f"Could not open PDF: {exc}") from exc

        try:
            token = self._find_token_in_text(doc)
            if token is None:
                token = self._find_token_in_metadata(doc)
        finally:
            doc.close()

        if token is None:
            raise SecretNotFoundError(
                "No stealth-invisible watermark found in page text or metadata"
            )

        return self._verify_token(token, key)

    # ---------------------
    # Internal helpers
    # ---------------------

    _TOKEN_RE: Final[re.Pattern[str]] = re.compile(
        re.escape("~~WMBEGIN~~:") + r"(.*?)" + re.escape(":~~WMEND~~")
    )

    def _find_token_in_text(self, doc: "fitz.Document") -> str | None:
        for page in doc:
            text = page.get_text("text")
            m = self._TOKEN_RE.search(text)
            if m:
                return m.group(1)
        return None

    def _find_token_in_metadata(self, doc: "fitz.Document") -> str | None:
        meta = doc.metadata or {}
        keywords = meta.get("keywords") or ""
        for part in keywords.split(","):
            part = part.strip()
            if part.startswith(self._KEYWORDS_PREFIX):
                return part[len(self._KEYWORDS_PREFIX):]
        return None

    def _build_token(self, secret: str, key: str) -> str:
        secret_bytes = secret.encode("utf-8")
        mac_hex = self._mac_hex(secret_bytes, key)
        obj = {
            "v": 1,
            "alg": "HMAC-SHA256",
            "mac": mac_hex,
            "secret": base64.b64encode(secret_bytes).decode("ascii"),
        }
        j = json.dumps(obj, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        return base64.urlsafe_b64encode(j).decode("ascii")

    def _verify_token(self, token: str, key: str) -> str:
        try:
            payload_json = base64.urlsafe_b64decode(token.encode("ascii"))
            payload = json.loads(payload_json)
        except Exception as exc:
            raise SecretNotFoundError("Malformed watermark payload") from exc

        if not (isinstance(payload, dict) and payload.get("v") == 1):
            raise SecretNotFoundError("Unsupported watermark version or format")
        if payload.get("alg") != "HMAC-SHA256":
            raise WatermarkingError(f"Unsupported MAC algorithm: {payload.get('alg')!r}")

        try:
            mac_hex = str(payload["mac"])
            secret_b64 = str(payload["secret"]).encode("ascii")
            secret_bytes = base64.b64decode(secret_b64)
        except Exception as exc:
            raise SecretNotFoundError("Invalid payload fields") from exc

        expected = self._mac_hex(secret_bytes, key)
        if not hmac.compare_digest(mac_hex, expected):
            raise InvalidKeyError("Provided key failed to authenticate the watermark")

        return secret_bytes.decode("utf-8")

    def _mac_hex(self, secret_bytes: bytes, key: str) -> str:
        hm = hmac.new(key.encode("utf-8"), self._CONTEXT + secret_bytes, hashlib.sha256)
        return hm.hexdigest()


__all__ = ["StealthInvisibleWatermark"]