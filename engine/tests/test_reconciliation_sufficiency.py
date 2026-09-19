from __future__ import annotations

from witness_engine.evidence import (
    EvidenceReconciler,
    EvidenceRelation,
    SufficiencyGate,
    SufficiencyState,
)
from witness_engine.pipeline import index_document
from witness_engine.retrieval import (
    DeterministicHashEmbeddingProvider,
    LocalEvidenceIndex,
    LocalVectorIndex,
    RoutedRetriever,
)


def _retrieve(database, documents, question, *, limit=10):
    provider = DeterministicHashEmbeddingProvider(dimensions=32)
    with LocalEvidenceIndex(database) as lexical, LocalVectorIndex(database) as vectors:
        for path, valid_from in documents:
            index_document(
                path,
                lexical,
                vector_index=vectors,
                embedding_provider=provider,
                valid_from=valid_from,
            )
        retrieval = RoutedRetriever(lexical, vectors, provider).search(
            question,
            limit=limit,
            candidate_pool=max(20, limit),
            rerank_pool=max(20, limit),
        )
        reconciliation = EvidenceReconciler(lexical).reconcile(retrieval.candidates)
        sufficiency = SufficiencyGate().decide(
            question,
            retrieval.candidates,
            reconciliation,
            temporal_selection=retrieval.trace.temporal_selection,
        )
        return retrieval, reconciliation, sufficiency


def test_independent_numeric_claims_produce_visible_conflict(tmp_path):
    left = tmp_path / "left.md"
    right = tmp_path / "right.md"
    left.write_text("# API\n\nThe API port is 4100.", encoding="utf-8")
    right.write_text("# API\n\nThe API port is 5200.", encoding="utf-8")

    retrieval, reconciliation, sufficiency = _retrieve(
        tmp_path / "witness.sqlite3",
        ((left, "2026-01-01T00:00:00+00:00"), (right, "2026-01-01T00:00:00+00:00")),
        "What is the API port?",
    )

    assert retrieval.candidates
    assert reconciliation.unresolved_conflicts
    assert all(
        item.relation == EvidenceRelation.CONTRADICTS
        for item in reconciliation.unresolved_conflicts
    )
    assert reconciliation.independent_source_count == 2
    assert sufficiency.state == SufficiencyState.CONFLICTED


def test_versioned_numeric_claim_is_resolved_as_supersession(tmp_path):
    document = tmp_path / "api.md"
    database = tmp_path / "witness.sqlite3"
    provider = DeterministicHashEmbeddingProvider(dimensions=32)

    with LocalEvidenceIndex(database) as lexical, LocalVectorIndex(database) as vectors:
        document.write_text("# API\n\nThe API port is 4100.", encoding="utf-8")
        index_document(
            document,
            lexical,
            vector_index=vectors,
            embedding_provider=provider,
            valid_from="2024-01-01T00:00:00+00:00",
        )
        document.write_text("# API\n\nThe API port is 5200.", encoding="utf-8")
        index_document(
            document,
            lexical,
            vector_index=vectors,
            embedding_provider=provider,
            valid_from="2025-01-01T00:00:00+00:00",
        )

        retrieval = RoutedRetriever(lexical, vectors, provider).search(
            "How did the API port change?",
            limit=10,
            candidate_pool=20,
            rerank_pool=20,
        )
        reconciliation = EvidenceReconciler(lexical).reconcile(retrieval.candidates)
        sufficiency = SufficiencyGate().decide(
            "How did the API port change?",
            retrieval.candidates,
            reconciliation,
            temporal_selection=retrieval.trace.temporal_selection,
        )

    assert reconciliation.supersessions
    assert reconciliation.unresolved_conflicts == ()
    assert all(
        item.relation == EvidenceRelation.SUPERSEDES
        for item in reconciliation.supersessions
    )
    assert sufficiency.state in {SufficiencyState.SUFFICIENT, SufficiencyState.PARTIAL}


def test_unrelated_evidence_is_insufficient(tmp_path):
    document = tmp_path / "fruit.md"
    document.write_text("# Fruit\n\nBananas are yellow.", encoding="utf-8")

    retrieval, reconciliation, sufficiency = _retrieve(
        tmp_path / "witness.sqlite3",
        ((document, "2026-01-01T00:00:00+00:00"),),
        "What database encryption algorithm is required?",
    )

    assert sufficiency.state == SufficiencyState.INSUFFICIENT
    assert sufficiency.query_coverage < 0.25


def test_exactly_quarter_query_coverage_is_insufficient(tmp_path):
    document = tmp_path / "metadata.md"
    document.write_text(
        "# Metadata\n\nRequest metadata is required.\n",
        encoding="utf-8",
    )

    _retrieval, _reconciliation, sufficiency = _retrieve(
        tmp_path / "witness-quarter.sqlite3",
        ((document, "2026-01-01T00:00:00+00:00"),),
        "What database encryption algorithm is required?",
    )

    assert sufficiency.query_coverage == 0.25
    assert sufficiency.state == SufficiencyState.INSUFFICIENT
