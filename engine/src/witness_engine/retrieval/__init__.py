"""Witness retrieval primitives."""

from .adaptive import AdaptiveRetrievalResult, AdaptiveRetrievalTrace, RoutedRetriever
from .embeddings import (
    DeterministicHashEmbeddingProvider,
    EmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
)
from .graph import GraphRetrievalResult, GraphTraceItem, LocalEvidenceGraph
from .hierarchical import (
    HierarchicalRetrievalResult,
    HierarchyTraceItem,
    LocalHierarchyIndex,
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
from .temporal import (
    LocalTemporalIndex,
    TemporalRetrievalResult,
    TemporalSelection,
)
from .vector_index import LocalVectorIndex, VectorIndexError

__all__ = [
    "AdaptiveRetrievalResult",
    "AdaptiveRetrievalTrace",
    "CrossEncoderReranker",
    "DeterministicHashEmbeddingProvider",
    "DeterministicTokenReranker",
    "EmbeddingProvider",
    "EvidenceIndexError",
    "GraphRetrievalResult",
    "GraphTraceItem",
    "HierarchicalRetrievalResult",
    "HierarchyTraceItem",
    "HybridRetrievalResult",
    "HybridRetriever",
    "LexicalRetriever",
    "LocalEvidenceGraph",
    "LocalEvidenceIndex",
    "LocalHierarchyIndex",
    "LocalTemporalIndex",
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
    "TemporalRetrievalResult",
    "TemporalSelection",
    "TransparentRetrievalRouter",
    "VectorIndexError",
    "analyze_query",
    "rerank_candidates",
    "reciprocal_rank_fusion",
]
