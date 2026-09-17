"""Adaptive retrieval orchestration with routing, fusion, and reranking traces."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .embeddings import EmbeddingProvider
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
from .vector_index import LocalVectorIndex


@dataclass(frozen=True)
class AdaptiveRetrievalTrace:
    query: str
    plan: RetrievalPlan
    lexical_candidates: tuple[RetrievalCandidate, ...]
    dense_candidates: tuple[RetrievalCandidate, ...]
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
    """Execute only the routes requested by the transparent query plan.

    Temporal, graph, and hierarchical requests are currently advisory: their
    need is made visible in Trace, but the engine does not pretend those routes
    executed before their implementations exist.
    """

    def __init__(
        self,
        lexical_index: LocalEvidenceIndex,
        vector_index: LocalVectorIndex,
        embedding_provider: EmbeddingProvider,
        *,
        router: TransparentRetrievalRouter | None = None,
        reranker: RerankProvider | None = None,
    ) -> None:
        self.lexical_index = lexical_index
        self.vector_index = vector_index
        self.embedding_provider = embedding_provider
        self.router = router or TransparentRetrievalRouter()
        self.reranker = reranker or DeterministicTokenReranker()

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

        fusion_trace: tuple[FusedCandidateTrace, ...] = ()
        if lexical and dense:
            fused, fusion_trace = reciprocal_rank_fusion(
                (lexical, dense),
                limit=rerank_pool,
                rrf_k=rrf_k,
            )
            pre_rerank = fused
        elif lexical:
            pre_rerank = lexical[:rerank_pool]
        elif dense:
            pre_rerank = dense[:rerank_pool]
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
