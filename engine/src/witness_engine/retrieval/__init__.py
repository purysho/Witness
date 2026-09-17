"""Witness retrieval primitives."""

from .adaptive import AdaptiveRetrievalResult, AdaptiveRetrievalTrace, RoutedRetriever
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
from .query import QueryFeatures, analyze_query
from .rerank import (
    CrossEncoderReranker,
    DeterministicTokenReranker,
    RerankProvider,
    RerankResult,
    RerankTraceItem,
    rerank_candidates,
)
from .routing import RetrievalPlan, RouteDecision, TransparentRetrievalRouter
from .vector_index import LocalVectorIndex, VectorIndexError

__all__ = [
    "AdaptiveRetrievalResult",
    "AdaptiveRetrievalTrace",
    "CrossEncoderReranker",
    "DeterministicHashEmbeddingProvider",
    "DeterministicTokenReranker",
    "EmbeddingProvider",
    "EvidenceIndexError",
    "HybridRetrievalResult",
    "HybridRetriever",
    "LexicalRetriever",
    "LocalEvidenceIndex",
    "LocalVectorIndex",
    "QueryFeatures",
    "RerankProvider",
    "RerankResult",
    "RerankTraceItem",
    "RetrievalCandidate",
    "RetrievalPlan",
    "RetrievalTrace",
    "RouteDecision",
    "RoutedRetriever",
    "SentenceTransformerEmbeddingProvider",
    "TransparentRetrievalRouter",
    "VectorIndexError",
    "analyze_query",
    "reciprocal_rank_fusion",
    "rerank_candidates",
]
