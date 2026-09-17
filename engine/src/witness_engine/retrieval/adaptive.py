"""Adaptive retrieval orchestration with routing, specialized routes, fusion, and reranking traces."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .embeddings import EmbeddingProvider
from .graph import GraphTraceItem, LocalEvidenceGraph
from .hierarchical import HierarchyTraceItem, LocalHierarchyIndex
from .hybrid import FusedCandidateTrace, reciprocal_rank_fusion
from .index import LocalEvidenceIndex
from .models import RetrievalCandidate
from .rerank import (
    DeterministicTokenReranker,
    RerankProvider,
    RerankTraceItem,
    rerank_candidates,
)
from .routing import RetrievalPlan, TransparentRetrievalRouter
from .temporal import LocalTemporalIndex, TemporalSelection
from .vector_index import LocalVectorIndex


@dataclass(frozen=True)
class AdaptiveRetrievalTrace:
    query: str
    plan: RetrievalPlan
    lexical_candidates: tuple[RetrievalCandidate, ...]
    dense_candidates: tuple[RetrievalCandidate, ...]
    temporal_candidates: tuple[RetrievalCandidate, ...]
    hierarchical_candidates: tuple[RetrievalCandidate, ...]
    graph_candidates: tuple[RetrievalCandidate, ...]
    temporal_selection: TemporalSelection | None
    hierarchy_trace: tuple[HierarchyTraceItem, ...]
    graph_trace: tuple[GraphTraceItem, ...]
    fusion_candidates: tuple[FusedCandidateTrace, ...]
    pre_rerank_candidates: tuple[RetrievalCandidate, ...]
    rerank_trace: tuple[RerankTraceItem, ...]
    reranker_provider_id: str
    embedding_provider_id: str
    candidate_pool: int
    rerank_pool: int
    rrf_k: int
    advisory_routes: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AdaptiveRetrievalResult:
    candidates: tuple[RetrievalCandidate, ...]
    trace: AdaptiveRetrievalTrace


class RoutedRetriever:
    """Execute the transparent plan and preserve route artifacts for Trace."""

    def __init__(
        self,
        lexical_index: LocalEvidenceIndex,
        vector_index: LocalVectorIndex,
        embedding_provider: EmbeddingProvider,
        *,
        router: TransparentRetrievalRouter | None = None,
        reranker: RerankProvider | None = None,
        temporal_index: LocalTemporalIndex | None = None,
        hierarchy_index: LocalHierarchyIndex | None = None,
        evidence_graph: LocalEvidenceGraph | None = None,
    ) -> None:
        self.lexical_index = lexical_index
        self.vector_index = vector_index
        self.embedding_provider = embedding_provider
        self.router = router or TransparentRetrievalRouter()
        self.reranker = reranker or DeterministicTokenReranker()
        self.temporal_index = temporal_index or LocalTemporalIndex(lexical_index)
        self.hierarchy_index = hierarchy_index or LocalHierarchyIndex(lexical_index)
        self.evidence_graph = evidence_graph or LocalEvidenceGraph(lexical_index)

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        candidate_pool: int = 30,
        rerank_pool: int = 20,
        rrf_k: int = 60,
    ) -> AdaptiveRetrievalResult:
        if limit <= 0:
            limit = 0
        candidate_pool = max(candidate_pool, limit)
        rerank_pool = max(rerank_pool, limit)

        plan = self.router.plan(query)
        lexical: tuple[RetrievalCandidate, ...] = ()
        dense: tuple[RetrievalCandidate, ...] = ()
        temporal: tuple[RetrievalCandidate, ...] = ()
        hierarchical: tuple[RetrievalCandidate, ...] = ()
        graph: tuple[RetrievalCandidate, ...] = ()
        temporal_selection: TemporalSelection | None = None
        hierarchy_trace: tuple[HierarchyTraceItem, ...] = ()
        graph_trace: tuple[GraphTraceItem, ...] = ()

        if plan.should_run("lexical"):
            lexical = tuple(self.lexical_index.search(query, limit=candidate_pool))
        if plan.should_run("dense"):
            dense = tuple(
                self.vector_index.search(
                    query,
                    self.embedding_provider,
                    limit=candidate_pool,
                )
            )
        if plan.should_run("temporal"):
            temporal_result = self.temporal_index.search(query, limit=candidate_pool)
            temporal = temporal_result.candidates
            temporal_selection = temporal_result.selection
        if plan.should_run("hierarchical"):
            hierarchical_result = self.hierarchy_index.search(
                query,
                limit=candidate_pool,
                seed_pool=candidate_pool,
            )
            hierarchical = hierarchical_result.candidates
            hierarchy_trace = hierarchical_result.trace
        if plan.should_run("graph"):
            graph_result = self.evidence_graph.search(
                query,
                limit=candidate_pool,
                claim_pool=candidate_pool,
            )
            graph = graph_result.candidates
            graph_trace = graph_result.trace

        active_routes = tuple(
            route
            for route in (lexical, dense, temporal, hierarchical, graph)
            if route
        )

        fusion_trace: tuple[FusedCandidateTrace, ...] = ()
        if len(active_routes) > 1:
            fused, fusion_trace = reciprocal_rank_fusion(
                active_routes,
                limit=rerank_pool,
                rrf_k=rrf_k,
            )
            pre_rerank = fused
        elif active_routes:
            pre_rerank = active_routes[0][:rerank_pool]
        else:
            pre_rerank = ()

        reranked = rerank_candidates(
            query,
            pre_rerank,
            self.reranker,
            limit=limit,
        )

        return AdaptiveRetrievalResult(
            candidates=reranked.candidates,
            trace=AdaptiveRetrievalTrace(
                query=query,
                plan=plan,
                lexical_candidates=lexical,
                dense_candidates=dense,
                temporal_candidates=temporal,
                hierarchical_candidates=hierarchical,
                graph_candidates=graph,
                temporal_selection=temporal_selection,
                hierarchy_trace=hierarchy_trace,
                graph_trace=graph_trace,
                fusion_candidates=fusion_trace,
                pre_rerank_candidates=tuple(pre_rerank),
                rerank_trace=reranked.trace,
                reranker_provider_id=reranked.provider_id,
                embedding_provider_id=self.embedding_provider.provider_id,
                candidate_pool=candidate_pool,
                rerank_pool=rerank_pool,
                rrf_k=rrf_k,
                advisory_routes=plan.advisory_routes,
            ),
        )
