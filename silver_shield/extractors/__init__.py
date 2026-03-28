"""Bank statement extractors."""

from .base import BaseExtractor, Statement, Transaction
from .centier import CentierExtractor
from .usaa import USAAExtractor
from .ocr import OCRExtractor

PARSERS = {
    "centier": CentierExtractor,
    "usaa": USAAExtractor,
    "ocr": OCRExtractor,
    "generic": OCRExtractor,  # fallback
}


def get_extractor(parser_name: str) -> type:
    """Get extractor class by parser name."""
    return PARSERS.get(parser_name, OCRExtractor)
