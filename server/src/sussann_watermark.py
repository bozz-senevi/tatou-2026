from __future__ import annotations

import base64
import hashlib
from typing import Final

import fitz  # PyMuPDF

from watermarking_method import (
    InvalidKeyError,
    PdfSource,
    SecretNotFoundError,
    WatermarkingError,
    WatermarkingMethod,
    load_pdf_bytes,
)


class SussannWatermark(WatermarkingMethod):

    name: Final[str] = "sussann-watermark"

    @staticmethod
    def get_usage() -> str:
        """Describe how the watermarking method is used."""
        return "Sussann's watermarking method."

    def add_watermark(
        self,
        pdf: PdfSource,
        secret: str,
        key: str,
        position: str | None = None,
    ) -> bytes:
        """Add the watermark to the PDF."""
        data = load_pdf_bytes(pdf)

        try:
            document = fitz.open(stream=data, filetype="pdf")
        except Exception as exc:
            raise WatermarkingError("Could not open PDF") from exc

        try:
            metadata = document.metadata

            key_hash = hashlib.sha256(key.encode()).hexdigest()

            # Base64-encode so control/non-printable bytes survive storage in
            # the PDF metadata (which only keeps printable text).
            encoded_secret = base64.b64encode(secret.encode("utf-8")).decode("ascii")

            metadata["keywords"] = encoded_secret
            metadata["producer"] = key_hash
            document.set_metadata(metadata)

            watermarked_pdf = document.tobytes()
        except (ValueError, WatermarkingError):
            raise
        except Exception as exc:
            raise WatermarkingError("Failed to embed watermark") from exc
        finally:
            document.close()

        return watermarked_pdf

    def is_watermark_applicable(
        self,
        pdf: PdfSource,
        position: str | None = None,
    ) -> bool:
        try:
            document = fitz.open(
                stream=load_pdf_bytes(pdf),
                filetype="pdf"
            )
            applicable = not document.needs_pass and document.page_count > 0
            document.close()
            return applicable
        except Exception:
            return False


    def read_secret(
        self,
        pdf: PdfSource,
        key: str,
    ) -> str:
        """Read the secret stored in the watermark."""
        data = load_pdf_bytes(pdf)

        try:
            document = fitz.open(stream=data, filetype="pdf")
        except Exception as exc:
            raise WatermarkingError("Could not open PDF") from exc

        try:
            stored = document.metadata.get("keywords")
            saved_key_hash = document.metadata.get("producer")
        finally:
            document.close()

        if not stored:
            raise SecretNotFoundError("No watermark found")

        key_hash = hashlib.sha256(key.encode()).hexdigest()

        if key_hash != saved_key_hash:
            raise InvalidKeyError("Invalid key")

        # Decode the base64 secret back to its original bytes.
        try:
            return base64.b64decode(stored).decode("utf-8")
        except Exception as exc:
            raise SecretNotFoundError("Malformed watermark payload") from exc


__all__ = ["SussannWatermark"]