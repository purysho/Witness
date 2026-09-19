from __future__ import annotations

import sqlite3

from witness_engine.multimodal import (
    DeterministicHashVisualEmbeddingProvider,
    LocalVisualVectorIndex,
    NormalizedRegion,
    VisualEvidenceStore,
    VisualModality,
)
from witness_engine.retrieval import (
    LocalEvidenceGraph,
    LocalEvidenceIndex,
    LocalTemporalIndex,
)
from witness_engine.rpc.service import RpcService


def _citation_source_ids(result: dict) -> set[str]:
    return {
        str(item["source_version_id"])
        for item in result["answer"]["citations"]
    }


def test_archive_hides_current_logical_source_but_preserves_history_and_trace(
    tmp_path,
):
    workspace = tmp_path / "Lifecycle.witness"
    source = tmp_path / "api.md"
    source.write_text(
        "# API Handbook 2025\n\n"
        "The public API port is 4100.\n",
        encoding="utf-8",
    )

    service = RpcService()
    try:
        service.handle("workspace.open", {"path": str(workspace)})
        old = service.handle(
            "source.import",
            {
                "path": str(source),
                "valid_from": "2025-01-01T00:00:00+00:00",
            },
        )

        source.write_text(
            "# API Handbook 2026\n\n"
            "The current public API port is 5200.\n\n"
            "Platform Gateway depends on Token Service.\n",
            encoding="utf-8",
        )
        current = service.handle(
            "source.import",
            {
                "path": str(source),
                "valid_from": "2026-01-01T00:00:00+00:00",
            },
        )

        before = service.handle(
            "query.run",
            {"question": "What port does the current API use?"},
        )
        assert current["source_version_id"] in _citation_source_ids(before)
        original_run_id = before["run_id"]

        assert service.lexical is not None
        visual_store = VisualEvidenceStore(service.lexical)
        visual = visual_store.register(
            source_version_id=current["source_version_id"],
            modality=VisualModality.CHART,
            page_number=1,
            region=NormalizedRegion(
                x0=0.1,
                y0=0.1,
                x1=0.9,
                y1=0.9,
            ),
            payload=b"lifecycle-chart",
            media_type="image/png",
            label_text="API port 5200 architecture chart",
        )
        visual_provider = DeterministicHashVisualEmbeddingProvider(
            dimensions=16
        )
        visual_index = LocalVisualVectorIndex(service.lexical)
        assert visual_index.sync(visual_provider) == 1
        assert visual.visual_evidence_id in {
            item.visual_evidence_id
            for item in visual_index.search(
                "API port architecture chart",
                visual_provider,
                limit=5,
            )
        }

        archived = service.handle(
            "source.archive",
            {"source_version_id": current["source_version_id"]},
        )
        assert archived["archived"] is True
        assert archived["archived_at"]
        assert archived["chunk_count"] > 0
        assert len(archived["version_chain"]) == 2

        listed = {
            item["source_version_id"]: item
            for item in service.handle("source.list", {})["sources"]
        }
        assert listed[current["source_version_id"]]["archived"] is True
        assert listed[old["source_version_id"]]["archived"] is False

        # The archived current tip hides the entire logical source from ordinary
        # retrieval, so an older superseded version cannot silently become current.
        assert service.lexical.search("public API port", limit=10) == []
        assert service.vectors is not None
        assert (
            service.vectors.search(
                "public API port",
                service.embedding_provider,
                limit=10,
            )
            == []
        )
        assert (
            LocalEvidenceGraph(service.lexical)
            .search(
                "What does Platform Gateway depend on?",
                limit=10,
            )
            .candidates
            == ()
        )
        assert (
            visual_index.search(
                "API port architecture chart",
                visual_provider,
                limit=5,
            )
            == []
        )

        graph = service.handle("graph.snapshot", {})
        assert not any(
            node["kind"] == "source"
            and node["metadata"]["source_version_id"]
            in {
                old["source_version_id"],
                current["source_version_id"],
            }
            for node in graph["nodes"]
        )

        after_archive = service.handle(
            "query.run",
            {"question": "What port does the current API use?"},
        )
        assert current["source_version_id"] not in _citation_source_ids(
            after_archive
        )
        assert old["source_version_id"] not in _citation_source_ids(
            after_archive
        )

        # Explicit time travel can still resolve archived canonical evidence.
        temporal = LocalTemporalIndex(service.lexical)
        historical = temporal.search(
            "What port did the API use in 2026?",
            limit=10,
        )
        assert current["source_version_id"] in {
            item.source_version_id
            for item in historical.candidates
        }

        # Archiving cannot invalidate an already-completed trace/citation.
        old_trace = service.handle(
            "query.trace",
            {"run_id": original_run_id},
        )
        assert {
            item["evidence_id"]
            for item in old_trace["answer"]["citations"]
        } == {
            item["evidence_id"]
            for item in before["answer"]["citations"]
        }
        assert [
            item["text"]
            for item in old_trace["answer"]["sentences"]
        ] == [
            item["text"]
            for item in before["answer"]["sentences"]
        ]
        assert current["source_version_id"] in {
            item["source_version_id"]
            for item in old_trace["answer"]["citations"]
        }

        restored = service.handle(
            "source.restore",
            {"source_version_id": current["source_version_id"]},
        )
        assert restored["archived"] is False
        assert restored["archived_at"] is None

        after_restore = service.handle(
            "query.run",
            {"question": "What port does the current API use?"},
        )
        assert current["source_version_id"] in _citation_source_ids(
            after_restore
        )
    finally:
        service.close()

    reopened = RpcService()
    try:
        reopened.handle("workspace.open", {"path": str(workspace)})
        detail = reopened.handle(
            "source.detail",
            {"source_version_id": current["source_version_id"]},
        )
        assert detail["archived"] is False
        assert detail["archived_at"] is None
        assert len(detail["version_chain"]) == 2
        trace = reopened.handle(
            "query.trace",
            {"run_id": original_run_id},
        )
        assert current["source_version_id"] in {
            item["source_version_id"]
            for item in trace["answer"]["citations"]
        }
    finally:
        reopened.close()


def test_v1_workspace_schema_migrates_archived_at_without_rewriting_rows(
    tmp_path,
):
    database = tmp_path / "legacy.sqlite3"
    with LocalEvidenceIndex(database) as lexical:
        lexical.connection.executescript(
            """
            CREATE TABLE source_version_metadata (
                source_version_id TEXT PRIMARY KEY,
                logical_source_id TEXT NOT NULL,
                source_path TEXT NOT NULL,
                title TEXT NOT NULL,
                media_type TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                valid_from TEXT NOT NULL,
                valid_to TEXT,
                supersedes_source_version_id TEXT,
                superseded_by_source_version_id TEXT
            );
            INSERT INTO source_version_metadata (
                source_version_id, logical_source_id, source_path, title,
                media_type, observed_at, valid_from
            ) VALUES (
                'legacy-version', 'legacy-source', 'C:/legacy.txt', 'Legacy',
                'text/plain', '2026-01-01T00:00:00+00:00',
                '2026-01-01T00:00:00+00:00'
            );
            """
        )

        LocalTemporalIndex(lexical)

        columns = {
            row["name"]
            for row in lexical.connection.execute(
                "PRAGMA table_info(source_version_metadata)"
            ).fetchall()
        }
        assert "archived_at" in columns
        row = lexical.connection.execute(
            """
            SELECT source_version_id, title, archived_at
            FROM source_version_metadata
            WHERE source_version_id = 'legacy-version'
            """
        ).fetchone()
        assert tuple(row) == ("legacy-version", "Legacy", None)
