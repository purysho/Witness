"""Hybrid lexical + dense retrieval with inspectable RRF fusion."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .embeddings import EmbeddingProvider
from .index import LocalEvidenceIndex
from .models import RetrievalCandidate
from .vector_index import LocalVectorIndex


@dataclass(frozen=True)
class RouteContribution:
    method: str
    route_rank: int
    route_score: float
    rrf_contribution: float


@dataclass(frozen=True)
class FusedCandidateTrace:
    chunk_id: str
    fused_rank: int
    fused_score: float
    contributions: tuple[RouteContribution, ...]


@dataclass(frozen=True)
class RetrievalTrace:
    query: str
    lexical_candidates: tuple[RetrievalCandidate, ...]
    dense_candidates: tuple[RetrievalCandidate, ...]
    fused_candidates: tuple[FusedCandidateTrace, ...]
    embedding_provider_id: str
    rrf_k: int
    candidate_pool: int

    def to_dict(self) -> dict:
        """Return a JSON-compatible trace payload for desktop IPC/export."""
        return asdict(self)


@dataclass(frozen=True)
class HybridRetrievalResult:
    candidates: tuple[RetrievalCandidate, ...]
    trace: RetrievalTrace


def reciprocal_rank_fusion(
    routes: tuple[tuple[RetrievalCandidate, ...], ...],
    *,
    limit: int,
    rrf_k: int = 60,
) -> tuple[tuple[RetrievalCandidate, ...], tuple[FusedCandidateTrace, ...]]:
    """Fuse route rankings without comparing incomparable raw route scores."""
    if rrf_k < 1:
        raise ValueError("rrf_k must be >= 1")
    if limit <= 0:
        return (), ()

    representatives: dict[str, RetrievalCandidate] = {}
    contributions: dict[str, list[RouteContribution]] = {}
    totals: dict[str, float] = {}

    for route in routes:
        for candidate in route:
            contribution = 1.0 / (rrf_k + candidate.rank)
            totals[candidate.chunk_id] = totals.get(candidate.chunk_id, 0.0) + contribution
            contributions.setdefault(candidate.chunk_id, []).append(
                RouteContribution(
                    method=candidate.method,
                    route_rank=candidate.rank,
                    route_score=candidate.score,
                    rrf_contribution=contribution,
                )
            )
            previous = representatives.get(candidate.chunk_id)
            if previous is None or candidate.rank < previous.rank:
                representatives[candidate.chunk_id] = candidate

    ordered_ids = sorted(totals, key=lambda chunk_id: (-totals[chunk_id], chunk_id))[:limit]

    fused_candidates: list[RetrievalCandidate] = []
    trace_items: list[FusedCandidateTrace] = []
    for fused_rank, chunk_id in enumerate(ordered_ids, start=1):
        representative = representatives[chunk_id]
        fused_score = totals[chunk_id]
        fused_candidates.append(
            RetrievalCandidate(
                chunk_id=representative.chunk_id,
                text=representative.text,
                score=fused_score,
                rank=fused_rank,
                method="rrf-hybrid",
                source_version_id=representative.source_version_id,
                locator=representative.locator,
                block_id=representative.block_id,
            )
        )
        trace_items.append(
            FusedCandidateTrace(
                chunk_id=chunk_id,
                fused_rank=fused_rank,
                fused_score=fused_score,
                contributions=tuple(
                    sorted(
                        contributions[chunk_id],
                        key=lambda item: (item.method, item.route_rank),
                    )
                ),
            )
        )

    return tuple(fused_candidates), tuple(trace_items)


class HybridRetriever:
    """Run lexical and dense routes, then fuse them with RRF."""

    def __init__(
        self,
        lexical_index: LocalEvidenceIndex,
        vector_index: LocalVectorIndex,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self.lexical_index = lexical_index
        self.vector_index = vector_index
        self.embedding_provider = embedding_provider

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        candidate_pool: int = 30,
        rrf_k: int = 60,
    ) -> HybridRetrievalResult:
        if candidate_pool < limit:
            candidate_pool = limit

        lexical = tuple(self.lexical_index.search(query, limit=candidate_pool))
        dense = tuple(
            self.vector_index.search(
                query,
                self.embedding_provider,
                limit=candidate_pool,
            )
        )
        fused, fusion_trace = reciprocal_rank_fusion(
            (lexical, dense),
            limit=limit,
            rrf_k=rrf_k,
        )

        return HybridRetrievalResult(
            candidates=fused,
            trace=RetrievalTrace(
                query=query,
                lexical_candidates=lexical,
                dense_candidates=dense,
                fused_candidates=fusion_trace,
                embedding_provider_id=self.embedding_provider.provider_id,
                rrf_k=rrf_k,
                candidate_pool=candidate_pool,
            ),
        )
