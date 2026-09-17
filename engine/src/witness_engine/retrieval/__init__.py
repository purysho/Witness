"""Witness retrieval primitives.

Phase 2 begins with deterministic lexical retrieval before dense retrieval.
"""

from .models import RetrievalCandidate
from .lexical import LexicalRetriever

__all__ = ["RetrievalCandidate", "LexicalRetriever"]
