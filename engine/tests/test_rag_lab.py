from __future__ import annotations

import csv
import json

from witness_engine.evaluation import (
    EvalCase,
    EvalConfig,
    EvalDataset,
    EvalRunner,
    EvalStore,
    GoldEvidenceRef,
    RetrievalMode,
    compare_runs,
    export_run,
)
from witness_engine.evidence import SufficiencyState
from witness_engine.pipeline import index_document
from witness_engine.retrieval import (
    DeterministicHashEmbeddingProvider,
    LocalEvidenceIndex,
    LocalVectorIndex,
)


def _dataset() -> EvalDataset:
    return EvalDataset(
        dataset_id="core-smoke",
        name="Core smoke benchmark",
        description="Deterministic Phase 5 fixture.",
        cases=(
            EvalCase(
                case_id="api-port",
                question="What is the API port?",
                gold_evidence=(
                    GoldEvidenceRef(
                        source_path="api.md",
                        locator="line:3",
                    ),
                ),
                expected_state=SufficiencyState.SUFFICIENT,
                expected_answer_contains=("5200",),
            ),
            EvalCase(
                case_id="missing-encryption",
                question="What database encryption algorithm is required?",
                gold_evidence=(),
                expected_state=SufficiencyState.INSUFFICIENT,
            ),
        ),
    )


def _build_workspace(tmp_path):
    api = tmp_path / "api.md"
    auth = tmp_path / "auth.md"
    api.write_text(
        "# API\n\nThe API port is 5200.\n",
        encoding="utf-8",
    )
    auth.write_text(
        "# Authentication\n\nAuthentication uses bearer tokens.\n",
        encoding="utf-8",
    )
    database = tmp_path / "witness.sqlite3"
    provider = DeterministicHashEmbeddingProvider(dimensions=32)
    lexical = LocalEvidenceIndex(database)
    vectors = LocalVectorIndex(database)
    for path in (api, auth):
        index_document(
            path,
            lexical,
            vector_index=vectors,
            embedding_provider=provider,
            valid_from="2026-01-01T00:00:00+00:00",
        )
    return database, provider, lexical, vectors


def test_dataset_fingerprint_is_content_addressed():
    first = _dataset()
    second = _dataset()
    assert first.fingerprint == second.fingerprint

    changed = second.model_copy(
        update={"name": "Changed benchmark name"}
    )
    assert changed.fingerprint != first.fingerprint


def test_lab_runner_persists_metrics_and_case_trace_links(tmp_path):
    database, provider, lexical, vectors = _build_workspace(tmp_path)
    try:
        store = EvalStore(lexical)
        runner = EvalRunner(
            lexical,
            vectors,
            provider,
            store=store,
        )
        result = runner.run(
            _dataset(),
            EvalConfig(
                name="Hybrid baseline",
                retrieval_mode=RetrievalMode.HYBRID,
                top_k=5,
            ),
        )

        assert result.run.status == "completed"
        assert result.run.metrics is not None
        assert result.run.metrics.case_count == 2
        assert "recall_at_k" in result.run.metrics.objective
        assert "abstention_correctness" in result.run.metrics.objective
        assert result.run.metrics.model_judged == {}

        by_id = {case.case_id: case for case in result.cases}
        assert by_id["api-port"].metrics.recall_at_k == 1.0
        assert by_id["api-port"].query_run_id
        assert by_id["api-port"].ask_result is not None
        assert by_id["missing-encryption"].answer_state == SufficiencyState.INSUFFICIENT

        query_run_id = by_id["api-port"].query_run_id
        trace_count = lexical.connection.execute(
            "SELECT COUNT(*) FROM query_trace_events WHERE run_id = ?",
            (query_run_id,),
        ).fetchone()[0]
        assert trace_count > 0
    finally:
        vectors.close()
        lexical.close()

    with LocalEvidenceIndex(database) as reopened:
        persisted = EvalStore(reopened).list_runs()
        assert len(persisted) == 1
        assert persisted[0].status == "completed"
        assert persisted[0].metrics is not None


def test_lab_compares_retrieval_modes_and_exports_json_csv(tmp_path):
    _database, provider, lexical, vectors = _build_workspace(tmp_path)
    try:
        store = EvalStore(lexical)
        runner = EvalRunner(
            lexical,
            vectors,
            provider,
            store=store,
        )
        dataset = _dataset()
        lexical_run = runner.run(
            dataset,
            EvalConfig(
                name="Lexical",
                retrieval_mode=RetrievalMode.LEXICAL,
                top_k=5,
            ),
        )
        routed_run = runner.run(
            dataset,
            EvalConfig(
                name="Routed",
                retrieval_mode=RetrievalMode.ROUTED,
                top_k=5,
            ),
        )

        comparison = compare_runs(
            store,
            lexical_run.run.run_id,
            routed_run.run.run_id,
        )
        assert comparison["dataset_id"] == dataset.dataset_id
        assert comparison["metrics"]
        assert all(
            item["kind"] == "objective"
            for item in comparison["metrics"]
        )
        assert comparison["model_judged_metrics"] == []

        json_path = export_run(
            store,
            routed_run.run.run_id,
            tmp_path / "exports" / "run.json",
            format="json",
        )
        csv_path = export_run(
            store,
            routed_run.run.run_id,
            tmp_path / "exports" / "run.csv",
            format="csv",
        )
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["run"]["run_id"] == routed_run.run.run_id

        with csv_path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        assert {row["case_id"] for row in rows} == {
            "api-port",
            "missing-encryption",
        }
    finally:
        vectors.close()
        lexical.close()
