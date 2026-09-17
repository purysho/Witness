"""Witness document ingestion pipeline.

Phase 2 introduces structured extraction boundaries while preserving
Phase 1 evidence identity guarantees.
"""

from .models import ExtractedBlock, ExtractedDocument
from .registry import (
    UnsupportedDocumentError,
    extract_document,
    extractor_for,
    supported_extensions,
)

__all__ = [
    "ExtractedBlock",
    "ExtractedDocument",
    "UnsupportedDocumentError",
    "extract_document",
    "extractor_for",
    "supported_extensions",
]
