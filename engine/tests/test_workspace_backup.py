from __future__ import annotations

import json
import zipfile

import pytest

from witness_engine.rpc.service import RpcService, RpcServiceError


_CONFIG = {
    "name": "Backup equivalence",
    "retrieval_mode": "hybrid",
    "top_k": 5,
    "candidate_pool": 12,
    "rerank_pool": 8,
    "rrf_k": 60,
    "rerank": True,
    "chunk_max_chars": 1200,
}


def _empty_workspace_backup(tmp_path):
    workspace = tmp_path / "Empty.witness"
    backup = tmp_path / "empty.witness-backup"
    service = RpcService()
    try:
        service.handle("workspace.open", {"path": str(workspace)})
        result = service.handle(
            "workspace.backup",
            {"path": str(backup)},
        )
        assert result["secrets_persisted"] is False
    finally:
        service.close()
    return backup


def test_backup_restore_preserves_protected_workspace_state(tmp_path):
    workspace = tmp_path / "Research.witness"
    backup = tmp_path / "research.witness-backup"
    restored_workspace = tmp_path / "Restored.witness"

    service = RpcService()
    try:
        service.handle("workspace.open", {"path": str(workspace)})
        demo = service.handle("demo.load", {})

        query = service.handle(
            "query.run",
            {"question": demo["suggested_question"]},
        )
        original_run_id = query["run_id"]

        lab = service.handle(
            "lab.run",
            {
                "dataset_fingerprint": demo["dataset"]["dataset_fingerprint"],
                "config": _CONFIG,
            },
        )
        attack = service.handle(
            "attack.run",
            {
                "manifest_fingerprint": (
                    demo["attack_manifest"]["manifest_fingerprint"]
                ),
                "dataset_fingerprint": demo["dataset"]["dataset_fingerprint"],
                "config": _CONFIG,
            },
        )

        service.handle(
            "source.archive",
            {
                "source_version_id": (
                    demo["source_versions"]["api_2026"]
                )
            },
        )
        sources_before = service.handle("source.list", {})["sources"]
        providers_before = service.handle("providers.get", {})
        health_before = service.handle("workspace.health", {})

        exported = service.handle(
            "workspace.backup",
            {"path": str(backup)},
        )
        assert exported["protected_state_fingerprint"] == (
            health_before["protected_state_fingerprint"]
        )
        assert exported["secrets_persisted"] is False
    finally:
        service.close()

    with zipfile.ZipFile(backup, "r") as archive:
        assert set(archive.namelist()) == {
            "manifest.json",
            "witness.db",
        }
        manifest = json.loads(
            archive.read("manifest.json").decode("utf-8")
        )
    assert manifest["format"] == "witness-workspace-backup"
    assert manifest["format_version"] == 1
    assert manifest["workspace_schema_version"] == 1
    assert manifest["secrets_persisted"] is False

    restored = RpcService()
    try:
        restored_result = restored.handle(
            "workspace.restore",
            {
                "backup_path": str(backup),
                "destination_path": str(restored_workspace),
            },
        )
        assert restored_result["protected_state_fingerprint"] == (
            health_before["protected_state_fingerprint"]
        )
        assert restored_result["secrets_persisted"] is False

        restored.handle(
            "workspace.open",
            {"path": str(restored_workspace)},
        )
        assert restored.handle("source.list", {})["sources"] == sources_before

        providers_after = restored.handle("providers.get", {})
        assert providers_after["settings"] == providers_before["settings"]
        assert (
            providers_after["embedding"]["provider_id"]
            == providers_before["embedding"]["provider_id"]
        )
        assert (
            providers_after["visual"]["provider_id"]
            == providers_before["visual"]["provider_id"]
        )

        health_after = restored.handle("workspace.health", {})
        assert health_after["protected_state_fingerprint"] == (
            health_before["protected_state_fingerprint"]
        )

        trace = restored.handle(
            "query.trace",
            {"run_id": original_run_id},
        )
        assert {
            item["evidence_id"]
            for item in trace["answer"]["citations"]
        } == {
            item["evidence_id"]
            for item in query["answer"]["citations"]
        }

        lab_run_ids = {
            item["run_id"]
            for item in restored.handle("lab.runs", {})["runs"]
        }
        assert lab["run"]["run_id"] in lab_run_ids

        attack_run_ids = {
            item["attack_run_id"]
            for item in restored.handle("attack.runs", {})["runs"]
        }
        assert attack["run"]["attack_run_id"] in attack_run_ids
        attack_detail = restored.handle(
            "attack.run.get",
            {"attack_run_id": attack["run"]["attack_run_id"]},
        )
        assert attack_detail["run"]["completed_at"]

        archived = restored.handle(
            "source.detail",
            {
                "source_version_id": (
                    demo["source_versions"]["api_2026"]
                )
            },
        )
        assert archived["archived"] is True
    finally:
        restored.close()


def test_restore_rejects_tampered_database_without_creating_destination(
    tmp_path,
):
    backup = _empty_workspace_backup(tmp_path)
    tampered = tmp_path / "tampered.witness-backup"

    with (
        zipfile.ZipFile(backup, "r") as source,
        zipfile.ZipFile(
            tampered,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as destination,
    ):
        for item in source.infolist():
            payload = source.read(item.filename)
            if item.filename == "witness.db":
                changed = bytearray(payload)
                changed[-1] ^= 1
                payload = bytes(changed)
            destination.writestr(item.filename, payload)

    restored_path = tmp_path / "TamperedRestore.witness"
    service = RpcService()
    try:
        with pytest.raises(RpcServiceError) as exc_info:
            service.handle(
                "workspace.restore",
                {
                    "backup_path": str(tampered),
                    "destination_path": str(restored_path),
                },
            )
        assert exc_info.value.code == "workspace_restore_failed"
        assert "checksum" in str(exc_info.value).lower()
        assert not restored_path.exists()
    finally:
        service.close()


def test_restore_rejects_unexpected_path_without_extracting_it(tmp_path):
    backup = _empty_workspace_backup(tmp_path)
    malicious = tmp_path / "traversal.witness-backup"
    escaped = tmp_path / "escaped.txt"

    with (
        zipfile.ZipFile(backup, "r") as source,
        zipfile.ZipFile(
            malicious,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as destination,
    ):
        for item in source.infolist():
            destination.writestr(
                item.filename,
                source.read(item.filename),
            )
        destination.writestr("../escaped.txt", b"must-not-extract")

    restored_path = tmp_path / "TraversalRestore.witness"
    service = RpcService()
    try:
        with pytest.raises(RpcServiceError) as exc_info:
            service.handle(
                "workspace.restore",
                {
                    "backup_path": str(malicious),
                    "destination_path": str(restored_path),
                },
            )
        assert exc_info.value.code == "workspace_restore_failed"
        assert not restored_path.exists()
        assert not escaped.exists()
    finally:
        service.close()
