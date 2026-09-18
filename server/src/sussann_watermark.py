"""sussann_watermark.py

Watermarking method implemented by Sussann.

This class follows the WatermarkingMethod interface used by Tatou.
"""

from __future__ import annotations

from typing import Final
import fitz  # PyMuPDF

from watermarking_method import (
    PdfSource,
    SecretNotFoundError,
    WatermarkingMethod,
    load_pdf_bytes,
)


class SussannWatermark(WatermarkingMethod):
    """Sussann's watermarking method."""

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
        metadata["keywords"] = secret
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
        document.close()

        if not secret:
            raise SecretNotFoundError("No watermark found")

        return secret


__all__ = ["SussannWatermark"]