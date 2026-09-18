"""Multimodal evidence contracts, persistence, and deterministic retrieval."""

from .index import LocalVisualVectorIndex
from .models import (
    NormalizedRegion,
    VisualEvidence,
    VisualModality,
    VisualRetrievalCandidate,
)
from .pdf import PdfVisualExtractionResult, index_pdf_visual_evidence
from .providers import (
    DeterministicHashVisualEmbeddingProvider,
    VisualEmbeddingProvider,
)
from .store import VisualEvidenceStore

__all__ = [
    "DeterministicHashVisualEmbeddingProvider",
    "LocalVisualVectorIndex",
    "NormalizedRegion",
    "PdfVisualExtractionResult",
    "VisualEmbeddingProvider",
    "VisualEvidence",
    "VisualEvidenceStore",
    "VisualModality",
    "VisualRetrievalCandidate",
    "index_pdf_visual_evidence",
]
