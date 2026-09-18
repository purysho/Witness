from __future__ import annotations

from witness_engine.multimodal import (
    NormalizedRegion,
    VisualEvidenceStore,
    VisualModality,
)
from witness_engine.rpc.service import RpcService


def test_workspace_repair_rebuilds_derived_indexes_without_touching_history(
    tmp_path,
):
    workspace = tmp_path / "Recovery.witness"
    source = tmp_path / "architecture.md"
    source.write_text(
        "# Architecture\n\n"
        "The API port is 5200. Authentication Service depends on Token Service.\n",
        encoding="utf-8",
    )

    service = RpcService()
    try:
        service.handle("workspace.open", {"path": str(workspace)})
        imported = service.handle(
            "source.import",
            {"path": str(source)},
        )
        original_source_version = imported["source_version_id"]

        answer = service.handle(
            "query.run",
            {"question": "What is the API port?"},
        )
        original_run_id = answer["run_id"]
        assert answer["answer"]["citations"]

        healthy = service.handle("workspace.health", {})
        assert healthy["status"] == "healthy"
        protected_before = healthy["protected_state_fingerprint"]

        assert service.lexical is not None
        connection = service.lexical.connection
        provider_id = service.embedding_provider.provider_id

        with connection:
            connection.execute("DELETE FROM indexed_chunks_fts")
            connection.execute("DELETE FROM graph_claims_fts")
            connection.execute("DELETE FROM graph_claim_evidence")
            connection.execute(
                """
                UPDATE chunk_embeddings
                SET vector = X'00'
                WHERE provider_id = ?
                """,
                (provider_id,),
            )

        broken = service.handle("workspace.health", {})
        assert broken["status"] == "repairable"
        codes = {item["code"] for item in broken["issues"]}
        assert {
            "lexical_projection",
            "graph_projection",
            "dense_projection",
        }.issubset(codes)
        assert broken["protected_state_fingerprint"] == protected_before

        repaired = service.handle("workspace.repair", {})
        assert repaired["protected_state_unchanged"] is True
        assert repaired["before"]["protected_state_fingerprint"] == protected_before
        assert repaired["after"]["protected_state_fingerprint"] == protected_before
        assert repaired["after"]["status"] == "healthy"
        assert repaired["actions"]

        trace = service.handle(
            "query.trace",
            {"run_id": original_run_id},
        )
        assert trace["events"][0]["stage"] == "query.received"
        assert trace["events"][-1]["stage"] == "run.completed"

        sources = service.handle("source.list", {})
        assert [item["source_version_id"] for item in sources["sources"]] == [
            original_source_version
        ]

        answer_after = service.handle(
            "query.run",
            {"question": "What is the API port?"},
        )
        assert answer_after["answer"]["citations"]
    finally:
        service.close()

    reopened = RpcService()
    try:
        reopened.handle("workspace.open", {"path": str(workspace)})
        health = reopened.handle("workspace.health", {})
        assert health["status"] == "healthy"
        answer = reopened.handle(
            "query.run",
            {"question": "What is the API port?"},
        )
        assert answer["answer"]["citations"]
    finally:
        reopened.close()


def test_workspace_repair_refuses_to_rewrite_corrupt_canonical_visual_asset(
    tmp_path,
):
    workspace = tmp_path / "Canonical.witness"
    source = tmp_path / "evidence.md"
    source.write_text(
        "# Evidence\n\nCanonical evidence remains immutable.\n",
        encoding="utf-8",
    )

    service = RpcService()
    try:
        service.handle("workspace.open", {"path": str(workspace)})
        imported = service.handle(
            "source.import",
            {"path": str(source)},
        )

        assert service.lexical is not None
        store = VisualEvidenceStore(service.lexical)
        evidence = store.register(
            source_version_id=imported["source_version_id"],
            modality=VisualModality.CHART,
            page_number=1,
            region=NormalizedRegion(
                x0=0.1,
                y0=0.1,
                x1=0.9,
                y1=0.9,
            ),
            payload=b"canonical-visual-asset",
            media_type="image/png",
            label_text="Canonical chart evidence",
        )

        connection = service.lexical.connection
        with connection:
            connection.execute(
                """
                UPDATE visual_assets
                SET payload = ?
                WHERE asset_sha256 = ?
                """,
                (
                    b"tampered--visual-asset",
                    evidence.asset_sha256,
                ),
            )

        broken = service.handle("workspace.health", {})
        assert broken["status"] == "attention"
        issue = next(
            item
            for item in broken["issues"]
            if item["code"] == "visual_asset_integrity"
        )
        assert issue["repairable"] is False

        tampered_before = store.asset_bytes(evidence.asset_sha256)
        repaired = service.handle("workspace.repair", {})
        assert repaired["protected_state_unchanged"] is True
        assert repaired["actions"] == []
        assert repaired["after"]["status"] == "attention"
        assert store.asset_bytes(evidence.asset_sha256) == tampered_before
    finally:
        service.close()
