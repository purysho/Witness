"""Canonical persistence for Attack Lab manifests and run metadata."""

from __future__ import annotations

from datetime import datetime, timezone

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

    def complete_run(self, result: AttackRunResult) -> None:
        with self.connection:
            self.connection.execute(
                """
                UPDATE attack_runs
                SET status = 'completed', completed_at = ?, result_json = ?
                WHERE attack_run_id = ?
                """,
                (
                    _now(),
                    result.model_dump_json(),
                    result.run.attack_run_id,
                ),
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
            SELECT attack_run_id, manifest_fingerprint, dataset_fingerprint,
                   canonical_corpus_fingerprint, attacked_corpus_fingerprint,
                   snapshot_id, snapshot_path, status, started_at, completed_at
            FROM attack_runs
            ORDER BY started_at DESC, attack_run_id DESC
            LIMIT ?
            """,
            (max(1, min(limit, 500)),),
        ).fetchall()
        return tuple(dict(row) for row in rows)
