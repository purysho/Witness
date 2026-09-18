from __future__ import annotations

import pytest

from witness_engine.evaluation import (
    EvalCase,
    EvalConfig,
    EvalDataset,
    EvalRunner,
    EvalStore,
    RetrievalMode,
)
from witness_engine.pipeline import index_document
from witness_engine.retrieval import (
    DeterministicHashEmbeddingProvider,
    LocalEvidenceIndex,
    LocalVectorIndex,
)
from witness_engine.tasks import (
    CancellationProbe,
    OperationCancelled,
    TaskStore,
)


def test_cancelled_changed_source_rolls_back_new_version_and_temporal_chain(
    tmp_path,
):
    source = tmp_path / "service.md"
    source.write_text(
        "# Service\n\nThe API port is 5200.\n",
        encoding="utf-8",
    )
    database = tmp_path / "witness.sqlite3"
    provider = DeterministicHashEmbeddingProvider(dimensions=32)

    with LocalEvidenceIndex(database) as lexical, LocalVectorIndex(database) as vectors:
        first = index_document(
            source,
            lexical,
            vector_index=vectors,
            embedding_provider=provider,
            valid_from="2026-01-01T00:00:00+00:00",
        )

        source.write_text(
            "# Service\n\nThe API port is 9000.\n",
            encoding="utf-8",
        )

        def cancel_after_registration() -> None:
            count = int(
                lexical.connection.execute(
                    "SELECT COUNT(*) FROM source_version_metadata"
                ).fetchone()[0]
            )
            if count >= 2:
                raise OperationCancelled("import-cancel")

        with pytest.raises(OperationCancelled):
            index_document(
                source,
                lexical,
                vector_index=vectors,
                embedding_provider=provider,
                valid_from="2026-02-01T00:00:00+00:00",
                cancel_check=cancel_after_registration,
            )

        versions = lexical.connection.execute(
            """
            SELECT source_version_id, valid_to, supersedes_source_version_id,
                   superseded_by_source_version_id
            FROM source_version_metadata
            ORDER BY valid_from
            """
        ).fetchall()
        assert len(versions) == 1
        assert versions[0]["source_version_id"] == first.source_version_id
        assert versions[0]["valid_to"] is None
        assert versions[0]["supersedes_source_version_id"] is None
        assert versions[0]["superseded_by_source_version_id"] is None

        chunks = lexical.connection.execute(
            """
            SELECT source_version_id, text
            FROM indexed_chunks
            ORDER BY chunk_id
            """
        ).fetchall()
        assert chunks
        assert {row["source_version_id"] for row in chunks} == {
            first.source_version_id
        }
        assert all("9000" not in row["text"] for row in chunks)
        assert lexical.search("5200", limit=5)
        assert not lexical.search("9000", limit=5)
        assert vectors.count(provider.provider_id) == len(chunks)


def test_cancelled_lab_run_keeps_completed_cases_and_marks_run_cancelled(
    tmp_path,
):
    source = tmp_path / "facts.md"
    source.write_text(
        "# Facts\n\nThe API port is 5200. Authentication uses bearer tokens.\n",
        encoding="utf-8",
    )
    database = tmp_path / "witness.sqlite3"
    provider = DeterministicHashEmbeddingProvider(dimensions=32)

    lexical = LocalEvidenceIndex(database)
    vectors = LocalVectorIndex(database)
    try:
        index_document(
            source,
            lexical,
            vector_index=vectors,
            embedding_provider=provider,
            valid_from="2026-01-01T00:00:00+00:00",
        )
        dataset = EvalDataset(
            dataset_id="cancel-smoke",
            name="Cancellation smoke",
            cases=(
                EvalCase(
                    case_id="one",
                    question="What is the API port?",
                ),
                EvalCase(
                    case_id="two",
                    question="What authentication is used?",
                ),
            ),
        )
        store = EvalStore(lexical)
        runner = EvalRunner(
            lexical,
            vectors,
            provider,
            store=store,
        )
        checks = 0

        def cancel_before_second_case() -> None:
            nonlocal checks
            checks += 1
            if checks >= 3:
                raise OperationCancelled("lab-cancel")

        with pytest.raises(OperationCancelled):
            runner.run(
                dataset,
                EvalConfig(
                    name="cancelled run",
                    retrieval_mode=RetrievalMode.HYBRID,
                    top_k=5,
                ),
                cancel_check=cancel_before_second_case,
            )

        runs = store.list_runs()
        assert len(runs) == 1
        assert runs[0].status == "cancelled"
        assert runs[0].metrics is None
        persisted = store.load_run(runs[0].run_id)
        assert [case.case_id for case in persisted.cases] == ["one"]
        assert persisted.cases[0].query_run_id
    finally:
        vectors.close()
        lexical.close()


def test_task_store_marks_crash_leftovers_interrupted_and_probe_is_file_based(
    tmp_path,
):
    database = tmp_path / "witness.sqlite3"
    workspace = tmp_path / "Workspace.witness"
    workspace.mkdir()

    with LocalEvidenceIndex(database) as lexical:
        tasks = TaskStore(lexical)
        tasks.start("lab-123", "lab.run")
        assert tasks.get("lab-123").status == "running"
        assert tasks.mark_interrupted() == 1
        interrupted = tasks.get("lab-123")
        assert interrupted.status == "interrupted"
        assert interrupted.completed_at is not None

        probe = CancellationProbe(workspace, "import-123")
        probe.prepare()
        probe.flag_path.write_text("cancel\n", encoding="utf-8")
        with pytest.raises(OperationCancelled):
            probe.check()
        probe.close()
        assert not probe.flag_path.exists()
