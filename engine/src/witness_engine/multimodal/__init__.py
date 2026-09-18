"""Multimodal evidence contracts, persistence, and deterministic retrieval."""

from .index import LocalVisualVectorIndex
from .models import (
    NormalizedRegion,
    VisualEvidence,
    VisualModality,
    VisualRetrievalCandidate,
)
from .providers import (
    DeterministicHashVisualEmbeddingProvider,
    VisualEmbeddingProvider,
)
from .store import VisualEvidenceStore

__all__ = [
    "DeterministicHashVisualEmbeddingProvider",
    "LocalVisualVectorIndex",
    "NormalizedRegion",
    "VisualEmbeddingProvider",
    "VisualEvidence",
    "VisualEvidenceStore",
    "VisualModality",
    "VisualRetrievalCandidate",
]
