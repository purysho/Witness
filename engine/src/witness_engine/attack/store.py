"""Canonical persistence for Attack Lab manifests and run metadata."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from ..retrieval.index import LocalEvidenceIndex
from .models import AttackManifest, AttackRunResult


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AttackStore:
    def __init__(self, evidence_index: LocalEvidenceIndex) -> None:
        self.connection = evidence_index.connection
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS attack_manifests (
                manifest_fingerprint TEXT PRIMARY KEY,
                attack_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                schema_version INTEGER NOT NULL,
                manifest_json TEXT NOT NULL,
                registered_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_attack_manifests_id
                ON attack_manifests(attack_id, registered_at DESC);

            CREATE TABLE IF NOT EXISTS attack_runs (
                attack_run_id TEXT PRIMARY KEY,
                manifest_fingerprint TEXT NOT NULL,
                dataset_fingerprint TEXT NOT NULL,
                config_json TEXT NOT NULL,
                canonical_corpus_fingerprint TEXT NOT NULL,
                attacked_corpus_fingerprint TEXT NOT NULL,
                snapshot_id TEXT NOT NULL,
                snapshot_path TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                result_json TEXT,
                FOREIGN KEY (manifest_fingerprint)
                    REFERENCES attack_manifests(manifest_fingerprint)
            );

            CREATE INDEX IF NOT EXISTS idx_attack_runs_started
                ON attack_runs(started_at DESC);
            """
        )

    def register_manifest(self, manifest: AttackManifest) -> str:
        with self.connection:
            self.connection.execute(
                """
                INSERT OR IGNORE INTO attack_manifests (
                    manifest_fingerprint, attack_id, name, description,
                    schema_version, manifest_json, registered_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    manifest.fingerprint,
                    manifest.attack_id,
                    manifest.name,
                    manifest.description,
                    manifest.schema_version,
                    manifest.canonical_json(),
                    _now(),
                ),
            )
        return manifest.fingerprint

    def load_manifest(self, fingerprint: str) -> AttackManifest:
        row = self.connection.execute(
            "SELECT manifest_json FROM attack_manifests WHERE manifest_fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown attack manifest: {fingerprint}")
        return AttackManifest.model_validate_json(row["manifest_json"])

    def list_manifests(self) -> tuple[dict, ...]:
        rows = self.connection.execute(
            """
            SELECT manifest_fingerprint, attack_id, name, description,
                   registered_at, manifest_json
            FROM attack_manifests
            ORDER BY registered_at DESC, attack_id
            """
        ).fetchall()
        return tuple(
            {
                "manifest_fingerprint": row["manifest_fingerprint"],
                "attack_id": row["attack_id"],
                "name": row["name"],
                "description": row["description"],
                "mutation_count": len(
                    AttackManifest.model_validate_json(row["manifest_json"]).mutations
                ),
                "registered_at": row["registered_at"],
            }
            for row in rows
        )

    def start_run(
        self,
        *,
        attack_run_id: str,
        manifest_fingerprint: str,
        dataset_fingerprint: str,
        config_json: str,
        canonical_corpus_fingerprint: str,
        attacked_corpus_fingerprint: str,
        snapshot_id: str,
        snapshot_path: str,
    ) -> str:
        started_at = _now()
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO attack_runs (
                    attack_run_id, manifest_fingerprint, dataset_fingerprint,
                    config_json, canonical_corpus_fingerprint,
                    attacked_corpus_fingerprint, snapshot_id, snapshot_path,
                    status, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running', ?)
                """,
                (
                    attack_run_id,
                    manifest_fingerprint,
                    dataset_fingerprint,
                    config_json,
                    canonical_corpus_fingerprint,
                    attacked_corpus_fingerprint,
                    snapshot_id,
                    snapshot_path,
                    started_at,
                ),
            )
        return started_at

    def complete_run(self, result: AttackRunResult) -> AttackRunResult:
        completed_at = _now()
        completed = result.model_copy(
            update={
                "run": result.run.model_copy(
                    update={"completed_at": completed_at}
                )
            }
        )
        with self.connection:
            self.connection.execute(
                """
                UPDATE attack_runs
                SET status = 'completed', completed_at = ?, result_json = ?
                WHERE attack_run_id = ?
                """,
                (
                    completed_at,
                    completed.model_dump_json(),
                    completed.run.attack_run_id,
                ),
            )
        return completed

    def cancel_run(self, attack_run_id: str) -> None:
        with self.connection:
            self.connection.execute(
                """
                UPDATE attack_runs
                SET status = 'cancelled', completed_at = ?
                WHERE attack_run_id = ?
                """,
                (_now(), attack_run_id),
            )

    def fail_run(self, attack_run_id: str) -> None:
        with self.connection:
            self.connection.execute(
                """
                UPDATE attack_runs
                SET status = 'failed', completed_at = ?
                WHERE attack_run_id = ?
                """,
                (_now(), attack_run_id),
            )

    def load_run(self, attack_run_id: str) -> AttackRunResult:
        row = self.connection.execute(
            "SELECT result_json FROM attack_runs WHERE attack_run_id = ?",
            (attack_run_id,),
        ).fetchone()
        if row is None or not row["result_json"]:
            raise KeyError(f"Unknown or incomplete attack run: {attack_run_id}")
        return AttackRunResult.model_validate_json(row["result_json"])

    def list_runs(self, *, limit: int = 50) -> tuple[dict, ...]:
        rows = self.connection.execute(
            """
            SELECT
                r.attack_run_id,
                r.manifest_fingerprint,
                m.attack_id,
                m.name AS attack_name,
                r.dataset_fingerprint,
                r.canonical_corpus_fingerprint,
                r.attacked_corpus_fingerprint,
                r.snapshot_id,
                r.snapshot_path,
                r.status,
                r.started_at,
                r.completed_at
            FROM attack_runs AS r
            JOIN attack_manifests AS m
              ON m.manifest_fingerprint = r.manifest_fingerprint
            ORDER BY r.started_at DESC, r.attack_run_id DESC
            LIMIT ?
            """,
            (max(1, min(limit, 500)),),
        ).fetchall()
        return tuple(dict(row) for row in rows)


def export_attack_run(
    store: AttackStore,
    attack_run_id: str,
    path: str | Path,
    *,
    format: str = "json",
) -> Path:
    """Export a complete reproducible Attack Lab result."""

    result = store.load_run(attack_run_id)
    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    normalized = format.casefold()

    if normalized == "json":
        output.write_text(
            json.dumps(
                result.model_dump(mode="json"),
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        return output

    if normalized != "csv":
        raise ValueError("Attack export format must be json or csv")

    fieldnames = [
        "record_type",
        "attack_run_id",
        "attack_id",
        "case_id",
        "invariant_id",
        "invariant_kind",
        "invariant_status",
        "clean_state",
        "attacked_state",
        "clean_passed",
        "attacked_passed",
        "recall_delta",
        "precision_delta",
        "citation_coverage_delta",
        "added_evidence_count",
        "removed_evidence_count",
        "rank_changed_count",
        "clean_answer_text",
        "attacked_answer_text",
        "detail",
        "canonical_corpus_fingerprint",
        "attacked_corpus_fingerprint",
        "snapshot_id",
    ]
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        base = {
            "attack_run_id": result.run.attack_run_id,
            "attack_id": result.run.attack_id,
            "canonical_corpus_fingerprint": result.run.canonical_corpus_fingerprint,
            "attacked_corpus_fingerprint": result.run.attacked_corpus_fingerprint,
            "snapshot_id": result.run.snapshot_id,
        }
        for case in result.cases:
            writer.writerow(
                {
                    **base,
                    "record_type": "case",
                    "case_id": case.case_id,
                    "clean_state": (
                        case.clean_state.value if case.clean_state else ""
                    ),
                    "attacked_state": (
                        case.attacked_state.value if case.attacked_state else ""
                    ),
                    "clean_passed": case.clean_passed,
                    "attacked_passed": case.attacked_passed,
                    "recall_delta": case.recall_delta,
                    "precision_delta": case.precision_delta,
                    "citation_coverage_delta": case.citation_coverage_delta,
                    "added_evidence_count": case.added_evidence_count,
                    "removed_evidence_count": case.removed_evidence_count,
                    "rank_changed_count": case.rank_changed_count,
                    "clean_answer_text": case.clean_answer_text,
                    "attacked_answer_text": case.attacked_answer_text,
                }
            )
        for invariant in result.invariants:
            writer.writerow(
                {
                    **base,
                    "record_type": "invariant",
                    "case_id": invariant.case_id or "",
                    "invariant_id": invariant.invariant_id,
                    "invariant_kind": invariant.kind,
                    "invariant_status": invariant.status.value,
                    "detail": invariant.detail,
                }
            )
    return output
