from __future__ import annotations

import hashlib
from typing import Final

import fitz  # PyMuPDF

from watermarking_method import (
    InvalidKeyError,
    PdfSource,
    SecretNotFoundError,
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

        document = fitz.open(stream=data, filetype="pdf")

        metadata = document.metadata

        key_hash = hashlib.sha256(key.encode()).hexdigest()

        metadata["keywords"] = secret
        metadata["producer"] = key_hash
        document.set_metadata(metadata)

        watermarked_pdf = document.tobytes()
        document.close()

        return watermarked_pdf

    def is_watermark_applicable(
        self,
        pdf: PdfSource,
        position: str | None = None,
    ) -> bool:
        return True

    def read_secret(
        self,
        pdf: PdfSource,
        key: str,
    ) -> str:
        """Read the secret stored in the watermark."""
        data = load_pdf_bytes(pdf)

        document = fitz.open(stream=data, filetype="pdf")

        secret = document.metadata.get("keywords")
        saved_key_hash = document.metadata.get("producer")

        document.close()

        if not secret:
            raise SecretNotFoundError("No watermark found")

        key_hash = hashlib.sha256(key.encode()).hexdigest()

        if key_hash != saved_key_hash:
            raise InvalidKeyError("Invalid key")

        return secret


__all__ = ["SussannWatermark"]