from __future__ import annotations
from typing import Final

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

    @staticmethod
    def get_usage() -> str:
        return "TODO: describe the method. Position is ignored."

    def is_watermark_applicable(self, pdf: PdfSource, position: str | None = None) -> bool:
        return True

    def add_watermark(self, pdf: PdfSource, secret: str, key: str, position: str | None = None) -> bytes:
        data = load_pdf_bytes(pdf)
        if not secret:
            raise ValueError("Secret must be a non-empty string")
        if not isinstance(key, str) or not key:
            raise ValueError("Key must be a non-empty string")
        raise NotImplementedError

    def read_secret(self, pdf: PdfSource, key: str) -> str:
        data = load_pdf_bytes(pdf)
        if not isinstance(key, str) or not key:
            raise ValueError("Key must be a non-empty string")
        raise NotImplementedError


__all__ = ["ImanWM"]
