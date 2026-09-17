"""Witness retrieval primitives.

Phase 2 begins with deterministic lexical retrieval before dense retrieval.
"""

from .index import EvidenceIndexError, LocalEvidenceIndex
from .lexical import LexicalRetriever
from .models import RetrievalCandidate

__all__ = [
    "EvidenceIndexError",
    "LocalEvidenceIndex",
    "RetrievalCandidate",
    "LexicalRetriever",
]
