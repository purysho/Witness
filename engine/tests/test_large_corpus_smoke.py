from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from witness_engine.rpc.service import RpcService


def _answer_text(result: dict) -> str:
    return " ".join(
        sentence["text"]
        for sentence in result["answer"]["sentences"]
    )


def test_many_sources_survive_reopen_query_and_projection_repair(
    tmp_path,
):
    workspace = tmp_path / "Corpus.witness"
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    target_token = "WITNESS_CORPUS_000023"
    target_port = "23023"

    service = RpcService()
    imported_ids: list[str] = []
    try:
        service.handle("workspace.open", {"path": str(workspace)})
        for index in range(24):
            source = corpus / f"record-{index:06d}.md"
            source.write_text(
                f"# Record {index}\n\n"
                f"Evidence token WITNESS_CORPUS_{index:06d}. "
                f"Service port is {23000 + index}.\n\n"
                "Generated corpus evidence remains deterministic across "
                "reopen and repair cycles.\n",
                encoding="utf-8",
            )
            imported = service.handle(
                "source.import",
                {"path": str(source)},
            )
            imported_ids.append(imported["source_version_id"])

        sources = service.handle("source.list", {})["sources"]
        assert len(sources) == 24
        assert {
            item["source_version_id"] for item in sources
        } == set(imported_ids)

        health = service.handle("workspace.health", {})
        assert health["status"] == "healthy"

        answer = service.handle(
            "query.run",
            {
                "question": (
                    f"What service port belongs to {target_token}?"
                ),
                "limit": 8,
            },
        )
        assert target_port in _answer_text(answer)
        assert answer["answer"]["citations"]
        assert any(
            citation["source_version_id"] == imported_ids[-1]
            for citation in answer["answer"]["citations"]
        )
    finally:
        service.close()

    reopened = RpcService()
    try:
        reopened.handle("workspace.open", {"path": str(workspace)})
        assert len(reopened.handle("source.list", {})["sources"]) == 24

        answer = reopened.handle(
            "query.run",
            {
                "question": (
                    f"What service port belongs to {target_token}?"
                ),
                "limit": 8,
            },
        )
        assert target_port in _answer_text(answer)
        assert answer["answer"]["citations"]

        before = reopened.handle("workspace.health", {})
        protected_before = before["protected_state_fingerprint"]

        assert reopened.lexical is not None
        with reopened.lexical.connection:
            reopened.lexical.connection.execute(
                "DELETE FROM indexed_chunks_fts"
            )
            reopened.lexical.connection.execute(
                "DELETE FROM graph_claims_fts"
            )

        broken = reopened.handle("workspace.health", {})
        assert broken["status"] == "repairable"
        assert (
            broken["protected_state_fingerprint"]
            == protected_before
        )

        repaired = reopened.handle("workspace.repair", {})
        assert repaired["protected_state_unchanged"] is True
        assert repaired["after"]["status"] == "healthy"
        assert (
            repaired["after"]["protected_state_fingerprint"]
            == protected_before
        )
        assert repaired["actions"]

        sources_after = reopened.handle("source.list", {})["sources"]
        assert {
            item["source_version_id"] for item in sources_after
        } == set(imported_ids)
    finally:
        reopened.close()

    final = RpcService()
    try:
        final.handle("workspace.open", {"path": str(workspace)})
        assert final.handle("workspace.health", {})["status"] == "healthy"
        assert len(final.handle("source.list", {})["sources"]) == 24
    finally:
        final.close()


def test_mixed_format_stress_smoke_preserves_workspace_invariants(
    tmp_path,
):
    root = Path(__file__).resolve().parents[2]
    report_path = tmp_path / "stress-report.json"
    stress_root = tmp_path / "stress-root"

    completed = subprocess.run(
        [
            sys.executable,
            str(root / "tools" / "stress-workspace.py"),
            "--files",
            "18",
            "--paragraphs",
            "2",
            "--large-every",
            "9",
            "--large-multiplier",
            "3",
            "--reopen-cycles",
            "2",
            "--root",
            str(stress_root),
            "--json-out",
            str(report_path),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )
    assert completed.returncode == 0, (
        completed.stdout + "\n" + completed.stderr
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["generated_files"] == 18
    assert report["source_versions"] == 18
    assert report["chunks"] >= 18
    assert report["health_after_import"] == "healthy"
    assert set(report["format_counts"]) == {
        "csv",
        "docx",
        "html",
        "md",
        "pdf",
        "pptx",
        "py",
        "txt",
        "xlsx",
    }
    assert all(
        count == 2
        for count in report["format_counts"].values()
    )

    assert report["query"]["evidence_count"] >= 1
    assert report["query"]["citation_count"] >= 1
    assert report["repair"]["status_before"] == "repairable"
    assert report["repair"]["status_after"] == "healthy"
    assert report["repair"]["protected_state_unchanged"] is True

    assert report["cancellation"]["cancelled"] is True
    assert report["cancellation"]["rolled_back"] is True
    assert report["cancellation"]["health"] == "healthy"

    assert len(report["reopen_cycles"]) == 2
    assert all(
        cycle["health"] == "healthy"
        and cycle["evidence_count"] >= 1
        for cycle in report["reopen_cycles"]
    )

    assert report["import_seconds"] > 0
    assert report["database_bytes"] > 0
    assert report["python_peak_alloc_bytes"] > 0
