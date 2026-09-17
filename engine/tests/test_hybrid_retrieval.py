from __future__ import annotations

from witness_engine.chunking import Chunk
from witness_engine.retrieval import (
    HybridRetriever,
    LocalEvidenceIndex,
    LocalVectorIndex,
    reciprocal_rank_fusion,
)
from witness_engine.retrieval.models import RetrievalCandidate


class SemanticFixtureProvider:
    provider_id = "fixture:semantic-v1"
    dimensions = 2

    def embed(self, texts):
        vectors = []
        for text in texts:
            lowered = text.casefold()
            if any(term in lowered for term in ("vehicle", "automobile", "car", "engine")):
                vectors.append((1.0, 0.0))
            elif any(term in lowered for term in ("fruit", "banana", "yellow")):
                vectors.append((0.0, 1.0))
            else:
                vectors.append((0.5, 0.5))
        return vectors


def test_rrf_favors_candidates_seen_by_multiple_routes():
    lexical = (
        RetrievalCandidate("a", "A", 9.0, 1, "bm25"),
        RetrievalCandidate("b", "B", 8.0, 2, "bm25"),
    )
    dense = (
        RetrievalCandidate("b", "B", 0.99, 1, "dense"),
        RetrievalCandidate("c", "C", 0.98, 2, "dense"),
    )

    fused, trace = reciprocal_rank_fusion((lexical, dense), limit=3, rrf_k=60)

    assert [candidate.chunk_id for candidate in fused][0] == "b"
    b_trace = next(item for item in trace if item.chunk_id == "b")
    assert len(b_trace.contributions) == 2
    assert {item.method for item in b_trace.contributions} == {"bm25", "dense"}


def test_hybrid_retrieval_surfaces_dense_only_evidence_and_trace(tmp_path):
    database = tmp_path / "witness.sqlite3"
    provider = SemanticFixtureProvider()

    with LocalEvidenceIndex(database) as lexical:
        lexical.index_chunks(
            [
                (
                    Chunk("chunk-car", "block-car", "automobile engine manual", 0, 24),
                    "source-car",
                    "line:1",
                ),
                (
                    Chunk("chunk-fruit", "block-fruit", "banana fruit guide", 0, 18),
                    "source-fruit",
                    "line:1",
                ),
            ]
        )
        with LocalVectorIndex(database) as vectors:
            vectors.sync(provider)
            result = HybridRetriever(lexical, vectors, provider).search(
                "vehicle maintenance",
                limit=2,
                candidate_pool=2,
            )

    assert result.candidates[0].chunk_id == "chunk-car"
    assert result.trace.query == "vehicle maintenance"
    assert result.trace.embedding_provider_id == provider.provider_id
    assert result.trace.lexical_candidates == ()
    assert result.trace.dense_candidates[0].chunk_id == "chunk-car"
    assert result.trace.fused_candidates[0].contributions[0].method.startswith("dense:")
