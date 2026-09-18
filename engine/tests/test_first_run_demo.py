from __future__ import annotations

from witness_engine.rpc.service import RpcService


def _answer_text(result: dict) -> str:
    return " ".join(
        sentence["text"]
        for sentence in result["answer"]["sentences"]
    )


def test_first_run_demo_is_idempotent_and_opens_real_evidence_flow(
    tmp_path,
):
    workspace = tmp_path / "Demo.witness"
    service = RpcService()
    try:
        service.handle(
            "workspace.open",
            {"path": str(workspace)},
        )
        first = service.handle("demo.load", {})

        assert first["suggested_question"] == (
            "What port does the current API use?"
        )
        assert first["dataset"]["dataset_id"] == (
            "witness-first-run-demo-v1"
        )
        assert first["dataset"]["case_count"] == 3
        assert first["attack_manifest"]["mutation_count"] == 1

        assert service.lexical is not None
        rows = service.lexical.connection.execute(
            """
            SELECT source_version_id, logical_source_id, valid_from, valid_to,
                   supersedes_source_version_id,
                   superseded_by_source_version_id
            FROM source_version_metadata
            ORDER BY logical_source_id, valid_from, source_version_id
            """
        ).fetchall()
        assert len(rows) == 3

        api_rows = [
            row
            for row in rows
            if row["source_version_id"]
            in {
                first["source_versions"]["api_2025"],
                first["source_versions"]["api_2026"],
            }
        ]
        assert len(api_rows) == 2
        assert api_rows[0]["logical_source_id"] == api_rows[1]["logical_source_id"]
        assert api_rows[0]["source_version_id"] == first["source_versions"]["api_2025"]
        assert api_rows[1]["source_version_id"] == first["source_versions"]["api_2026"]
        assert api_rows[0]["superseded_by_source_version_id"] == (
            first["source_versions"]["api_2026"]
        )
        assert api_rows[1]["supersedes_source_version_id"] == (
            first["source_versions"]["api_2025"]
        )
        assert api_rows[1]["superseded_by_source_version_id"] is None

        answer = service.handle(
            "query.run",
            {"question": first["suggested_question"]},
        )
        assert answer["answer"]["citations"]
        assert "5200" in _answer_text(answer)
        assert any(
            citation["source_version_id"]
            == first["source_versions"]["api_2026"]
            for citation in answer["answer"]["citations"]
        )

        trace = service.handle(
            "query.trace",
            {"run_id": answer["run_id"]},
        )
        stages = [event["stage"] for event in trace["events"]]
        assert "route.decided" in stages
        assert "evidence.reconciled" in stages
        assert "sufficiency.decided" in stages
        assert "answer.validated" in stages
        assert stages[-1] == "run.completed"

        lab = service.handle(
            "lab.run",
            {
                "dataset_fingerprint": first["dataset"]["dataset_fingerprint"],
                "config": {
                    "name": "First-run hybrid",
                    "retrieval_mode": "hybrid",
                    "top_k": 5,
                    "candidate_pool": 12,
                    "rerank_pool": 8,
                    "rrf_k": 60,
                    "rerank": True,
                    "chunk_max_chars": 1200,
                },
            },
        )
        assert lab["run"]["status"] == "completed"
        assert len(lab["cases"]) == 3

        manifests = service.handle(
            "attack.manifest.list",
            {},
        )["manifests"]
        assert any(
            item["manifest_fingerprint"]
            == first["attack_manifest"]["manifest_fingerprint"]
            for item in manifests
        )

        source_count_before = int(
            service.lexical.connection.execute(
                "SELECT COUNT(*) FROM source_version_metadata"
            ).fetchone()[0]
        )
        second = service.handle("demo.load", {})
        source_count_after = int(
            service.lexical.connection.execute(
                "SELECT COUNT(*) FROM source_version_metadata"
            ).fetchone()[0]
        )
        assert source_count_before == source_count_after == 3
        assert second["source_versions"] == first["source_versions"]
        assert (
            second["dataset"]["dataset_fingerprint"]
            == first["dataset"]["dataset_fingerprint"]
        )
        assert (
            second["attack_manifest"]["manifest_fingerprint"]
            == first["attack_manifest"]["manifest_fingerprint"]
        )
    finally:
        service.close()

    reopened = RpcService()
    try:
        reopened.handle(
            "workspace.open",
            {"path": str(workspace)},
        )
        sources = reopened.handle("source.list", {})["sources"]
        assert len(sources) == 3
        datasets = reopened.handle("lab.dataset.list", {})["datasets"]
        assert any(
            item["dataset_id"] == "witness-first-run-demo-v1"
            for item in datasets
        )
        manifests = reopened.handle(
            "attack.manifest.list",
            {},
        )["manifests"]
        assert any(
            item["attack_id"]
            == "witness-first-run-prompt-injection-v1"
            for item in manifests
        )
    finally:
        reopened.close()
