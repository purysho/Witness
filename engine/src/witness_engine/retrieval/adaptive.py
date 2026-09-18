"""Adaptive retrieval orchestration with routing, specialized routes, fusion, and reranking traces."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ..multimodal.index import LocalVisualVectorIndex
from ..multimodal.providers import VisualEmbeddingProvider
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
    visual_candidates: tuple[RetrievalCandidate, ...]
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
    visual_embedding_provider_id: str | None
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


def _should_run(plan: RetrievalPlan, route: str) -> bool:
    """Allow older/fixed Lab routers to omit newer optional routes."""

    try:
        return plan.should_run(route)
    except KeyError:
        return False


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
        visual_index: LocalVisualVectorIndex | None = None,
        visual_embedding_provider: VisualEmbeddingProvider | None = None,
    ) -> None:
        if (visual_index is None) != (visual_embedding_provider is None):
            raise ValueError(
                "visual_index and visual_embedding_provider must be supplied together"
            )
        self.lexical_index = lexical_index
        self.vector_index = vector_index
        self.embedding_provider = embedding_provider
        self.visual_index = visual_index
        self.visual_embedding_provider = visual_embedding_provider
        self.router = router or TransparentRetrievalRouter(
            visual_available=visual_index is not None
            and visual_embedding_provider is not None
        )
        self.reranker = reranker or DeterministicTokenReranker()
        self.temporal_index = temporal_index or LocalTemporalIndex(lexical_index)
        self.hierarchy_index = hierarchy_index or LocalHierarchyIndex(lexical_index)
        self.evidence_graph = evidence_graph or LocalEvidenceGraph(lexical_index)

    def _visual_search(
        self,
        query: str,
        *,
        limit: int,
    ) -> tuple[RetrievalCandidate, ...]:
        if self.visual_index is None or self.visual_embedding_provider is None:
            return ()
        items = self.visual_index.search(
            query,
            self.visual_embedding_provider,
            limit=limit,
        )
        return tuple(
            RetrievalCandidate(
                chunk_id=f"visual:{item.visual_evidence_id}",
                text=(
                    f"{item.modality.value}: {item.label_text.strip()}"
                    if item.label_text.strip()
                    else f"{item.modality.value} visual evidence at {item.locator}"
                ),
                score=item.score,
                rank=item.rank,
                method=item.method,
                source_version_id=item.source_version_id,
                locator=item.locator,
                evidence_kind="visual",
                visual_evidence_id=item.visual_evidence_id,
                modality=item.modality.value,
            )
            for item in items
        )

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
        visual: tuple[RetrievalCandidate, ...] = ()
        temporal: tuple[RetrievalCandidate, ...] = ()
        hierarchical: tuple[RetrievalCandidate, ...] = ()
        graph: tuple[RetrievalCandidate, ...] = ()
        temporal_selection: TemporalSelection | None = None
        hierarchy_trace: tuple[HierarchyTraceItem, ...] = ()
        graph_trace: tuple[GraphTraceItem, ...] = ()

        if _should_run(plan, "lexical"):
            lexical = tuple(self.lexical_index.search(query, limit=candidate_pool))
        if _should_run(plan, "dense"):
            dense = tuple(
                self.vector_index.search(
                    query,
                    self.embedding_provider,
                    limit=candidate_pool,
                )
            )
        if _should_run(plan, "visual"):
            visual = self._visual_search(query, limit=candidate_pool)
        if _should_run(plan, "temporal"):
            temporal_result = self.temporal_index.search(query, limit=candidate_pool)
            temporal = temporal_result.candidates
            temporal_selection = temporal_result.selection
        if _should_run(plan, "hierarchical"):
            hierarchical_result = self.hierarchy_index.search(
                query,
                limit=candidate_pool,
                seed_pool=candidate_pool,
            )
            hierarchical = hierarchical_result.candidates
            hierarchy_trace = hierarchical_result.trace
        if _should_run(plan, "graph"):
            graph_result = self.evidence_graph.search(
                query,
                limit=candidate_pool,
                claim_pool=candidate_pool,
            )
            graph = graph_result.candidates
            graph_trace = graph_result.trace

        active_routes = tuple(
            route
            for route in (
                lexical,
                dense,
                visual,
                temporal,
                hierarchical,
                graph,
            )
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
                visual_candidates=visual,
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
                visual_embedding_provider_id=(
                    self.visual_embedding_provider.provider_id
                    if self.visual_embedding_provider is not None
                    else None
                ),
                candidate_pool=candidate_pool,
                rerank_pool=rerank_pool,
                rrf_k=rrf_k,
                advisory_routes=plan.advisory_routes,
            ),
        )
