from __future__ import annotations

import pytest

from witness_engine.answering import (
    AnswerValidationError,
    GeneratedAnswer,
    GeneratedSentence,
    LocalRunStore,
    validate_generation,
)
from witness_engine.answering.context import build_context_pack
from witness_engine.evidence import EvidenceReconciler, SufficiencyGate, SufficiencyState
from witness_engine.pipeline import ask_evidence, index_document
from witness_engine.retrieval import (
    DeterministicHashEmbeddingProvider,
    LocalEvidenceIndex,
    LocalVectorIndex,
    RoutedRetriever,
)


def test_ask_loop_returns_cited_answer_and_persists_append_only_trace(tmp_path):
    document = tmp_path / "api.md"
    document.write_text("# API\n\nThe API port is 5200.", encoding="utf-8")
    database = tmp_path / "witness.sqlite3"
    provider = DeterministicHashEmbeddingProvider(dimensions=32)

    with LocalEvidenceIndex(database) as lexical, LocalVectorIndex(database) as vectors:
        index_document(
            document,
            lexical,
            vector_index=vectors,
            embedding_provider=provider,
            valid_from="2026-01-01T00:00:00+00:00",
        )
        result = ask_evidence(
            "What is the API port?",
            lexical,
            vectors,
            provider,
            limit=5,
        )

    assert result.answer.state == SufficiencyState.SUFFICIENT
    assert result.answer.citations
    known = {item.evidence_id for item in result.context.evidence}
    assert {
        evidence_id
        for sentence in result.answer.sentences
        for evidence_id in sentence.evidence_ids
    }.issubset(known)

    stages = tuple(event.stage for event in result.trace)
    assert stages == (
        "query.received",
        "query.normalized",
        "route.decided",
        "retrieval.lexical.completed",
        "retrieval.dense.completed",
        "retrieval.temporal.completed",
        "retrieval.hierarchical.completed",
        "retrieval.graph.completed",
        "fusion.completed",
        "rerank.completed",
        "evidence.reconciled",
        "sufficiency.decided",
        "context.built",
        "generation.completed",
        "answer.validated",
        "run.completed",
    )
    assert all(event.event_id for event in result.trace)
    assert all(event.schema_version == 1 for event in result.trace)

    with LocalEvidenceIndex(database) as reopened:
        store = LocalRunStore(reopened)
        persisted = store.load_events(result.run_id)
        persisted_answer = store.load_answer(result.run_id)

    assert tuple(event.stage for event in persisted) == stages
    assert [event.sequence for event in persisted] == list(range(1, len(stages) + 1))
    assert persisted_answer["state"] == SufficiencyState.SUFFICIENT.value


def test_conflicted_ask_does_not_silently_blend_incompatible_values(tmp_path):
    left = tmp_path / "source-a.md"
    right = tmp_path / "source-b.md"
    left.write_text("# API\n\nThe API port is 4100.", encoding="utf-8")
    right.write_text("# API\n\nThe API port is 5200.", encoding="utf-8")
    database = tmp_path / "witness.sqlite3"
    provider = DeterministicHashEmbeddingProvider(dimensions=32)

    with LocalEvidenceIndex(database) as lexical, LocalVectorIndex(database) as vectors:
        for path in (left, right):
            index_document(
                path,
                lexical,
                vector_index=vectors,
                embedding_provider=provider,
                valid_from="2026-01-01T00:00:00+00:00",
            )
        result = ask_evidence(
            "What is the API port?",
            lexical,
            vectors,
            provider,
            limit=10,
        )

    assert result.answer.state == SufficiencyState.CONFLICTED
    assert result.context.unresolved_conflicts
    assert len(result.answer.sentences) == 1
    assert len(result.answer.sentences[0].evidence_ids) == 2
    assert "Conflicting evidence reports" in result.answer.sentences[0].text


def test_validator_rejects_invented_evidence_id(tmp_path):
    document = tmp_path / "api.md"
    document.write_text("# API\n\nThe API port is 5200.", encoding="utf-8")
    database = tmp_path / "witness.sqlite3"
    provider = DeterministicHashEmbeddingProvider(dimensions=16)

    with LocalEvidenceIndex(database) as lexical, LocalVectorIndex(database) as vectors:
        index_document(
            document,
            lexical,
            vector_index=vectors,
            embedding_provider=provider,
        )
        retrieval = RoutedRetriever(lexical, vectors, provider).search(
            "What is the API port?",
            limit=5,
        )
        reconciliation = EvidenceReconciler(lexical).reconcile(retrieval.candidates)
        sufficiency = SufficiencyGate().decide(
            "What is the API port?",
            retrieval.candidates,
            reconciliation,
            temporal_selection=retrieval.trace.temporal_selection,
        )
        context = build_context_pack(
            "What is the API port?",
            retrieval.candidates,
            sufficiency,
            reconciliation,
        )

    generated = GeneratedAnswer(
        state=context.sufficiency_state,
        sentences=(
            GeneratedSentence("The API port is 9999.", ("invented-evidence-id",)),
        ),
    )

    with pytest.raises(AnswerValidationError, match="unknown evidence"):
        validate_generation(context, generated)
