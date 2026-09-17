"""Provider-neutral reranking with deterministic trace output."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Protocol, Sequence

from .models import RetrievalCandidate


_TOKEN_RE = re.compile(r"[A-Za-z0-9_./:#-]+", re.UNICODE)


class RerankProvider(Protocol):
    @property
    def provider_id(self) -> str: ...

    def score(self, query: str, candidates: Sequence[RetrievalCandidate]) -> list[float]: ...


@dataclass(frozen=True)
class RerankTraceItem:
    chunk_id: str
    pre_rank: int
    post_rank: int
    retrieval_score: float
    rerank_score: float
    source_method: str


@dataclass(frozen=True)
class RerankResult:
    candidates: tuple[RetrievalCandidate, ...]
    trace: tuple[RerankTraceItem, ...]
    provider_id: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DeterministicTokenReranker:
    """Offline baseline based on query-token coverage and exact phrases.

    This intentionally modest reranker gives Witness a deterministic reference
    point for Lab. It should be compared against learned cross-encoders rather
    than presented as state-of-the-art relevance scoring.
    """

    exact_phrase_bonus: float = 1.0

    @property
    def provider_id(self) -> str:
        return "deterministic-token-reranker:v1"

    def score(self, query: str, candidates: Sequence[RetrievalCandidate]) -> list[float]:
        query_tokens = [token.casefold() for token in _TOKEN_RE.findall(query)]
        unique_query = tuple(dict.fromkeys(query_tokens))
        normalized_query = " ".join(query.casefold().split())

        scores: list[float] = []
        for candidate in candidates:
            text = candidate.text.casefold()
            candidate_tokens = set(_TOKEN_RE.findall(text))
            if unique_query:
                coverage = sum(token in candidate_tokens for token in unique_query) / len(unique_query)
            else:
                coverage = 0.0
            phrase = self.exact_phrase_bonus if normalized_query and normalized_query in text else 0.0
            scores.append(float(coverage + phrase))
        return scores


class CrossEncoderReranker:
    """Optional local cross-encoder reranker backed by sentence-transformers."""

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        *,
        device: str | None = None,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self._model = None

    @property
    def provider_id(self) -> str:
        return f"cross-encoder:{self.model_name}"

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
            except ImportError as exc:  # pragma: no cover - optional dependency
                raise RuntimeError(
                    "Install witness-engine[embeddings] to use cross-encoder reranking"
                ) from exc
            self._model = CrossEncoder(self.model_name, device=self.device)
        return self._model

    def score(self, query: str, candidates: Sequence[RetrievalCandidate]) -> list[float]:
        if not candidates:
            return []
        model = self._load()
        values = model.predict([(query, candidate.text) for candidate in candidates])
        return [float(value) for value in values]


def rerank_candidates(
    query: str,
    candidates: Sequence[RetrievalCandidate],
    provider: RerankProvider,
    *,
    limit: int | None = None,
) -> RerankResult:
    """Rerank candidates while preserving pre/post ranks for Trace."""

    candidate_list = list(candidates)
    if not candidate_list:
        return RerankResult((), (), provider.provider_id)

    scores = provider.score(query, candidate_list)
    if len(scores) != len(candidate_list):
        raise ValueError("Rerank provider returned a different number of scores than candidates")

    rows = list(zip(candidate_list, scores))
    rows.sort(key=lambda item: (-item[1], item[0].rank, item[0].chunk_id))
    if limit is not None:
        rows = rows[: max(limit, 0)]

    reranked: list[RetrievalCandidate] = []
    traces: list[RerankTraceItem] = []
    for post_rank, (candidate, rerank_score) in enumerate(rows, start=1):
        reranked.append(
            RetrievalCandidate(
                chunk_id=candidate.chunk_id,
                text=candidate.text,
                score=float(rerank_score),
                rank=post_rank,
                method=f"rerank:{provider.provider_id}",
                source_version_id=candidate.source_version_id,
                locator=candidate.locator,
                block_id=candidate.block_id,
            )
        )
        traces.append(
            RerankTraceItem(
                chunk_id=candidate.chunk_id,
                pre_rank=candidate.rank,
                post_rank=post_rank,
                retrieval_score=candidate.score,
                rerank_score=float(rerank_score),
                source_method=candidate.method,
            )
        )

    return RerankResult(tuple(reranked), tuple(traces), provider.provider_id)
