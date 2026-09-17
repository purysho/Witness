"""Witness retrieval primitives."""

from .embeddings import (
    DeterministicHashEmbeddingProvider,
    EmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
)
from .hybrid import (
    HybridRetrievalResult,
    HybridRetriever,
    RetrievalTrace,
    reciprocal_rank_fusion,
)
from .index import EvidenceIndexError, LocalEvidenceIndex
from .lexical import LexicalRetriever
from .models import RetrievalCandidate
from .vector_index import LocalVectorIndex, VectorIndexError

__all__ = [
    "DeterministicHashEmbeddingProvider",
    "EmbeddingProvider",
    "EvidenceIndexError",
    "HybridRetrievalResult",
    "HybridRetriever",
    "LocalEvidenceIndex",
    "LocalVectorIndex",
    "RetrievalCandidate",
    "RetrievalTrace",
    "SentenceTransformerEmbeddingProvider",
    "VectorIndexError",
    "LexicalRetriever",
    "reciprocal_rank_fusion",
]
