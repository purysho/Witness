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
    OpenClipVisualEmbeddingProvider,
    VisualEmbeddingProvider,
)
from .store import VisualEvidenceStore

__all__ = [
    "DeterministicHashVisualEmbeddingProvider",
    "LocalVisualVectorIndex",
    "NormalizedRegion",
    "OpenClipVisualEmbeddingProvider",
    "PdfVisualExtractionResult",
    "VisualEmbeddingProvider",
    "VisualEvidence",
    "VisualEvidenceStore",
    "VisualModality",
    "VisualRetrievalCandidate",
    "index_pdf_visual_evidence",
]
