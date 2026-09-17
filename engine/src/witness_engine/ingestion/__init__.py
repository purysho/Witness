"""Witness document ingestion pipeline.

Phase 2 introduces structured extraction boundaries while preserving
Phase 1 evidence identity guarantees.
"""

from .models import ExtractedDocument, ExtractedBlock

__all__ = ["ExtractedDocument", "ExtractedBlock"]
