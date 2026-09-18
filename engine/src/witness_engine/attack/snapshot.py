"""Filesystem and SQLite isolation for Attack Lab."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ..evaluation.runner import corpus_fingerprint
from ..ids import stable_id
from ..retrieval.index import LocalEvidenceIndex


@dataclass(frozen=True)
class AttackSnapshot:
    snapshot_id: str
    root: Path
    database: Path
    artifacts: Path
    canonical_corpus_fingerprint: str


def create_attack_snapshot(
    canonical: LocalEvidenceIndex,
    workspace_path: str | Path,
    *,
    manifest_fingerprint: str,
    attack_run_id: str,
) -> AttackSnapshot:
    """Create a transactionally consistent clone without writing canonical evidence.

    sqlite3.Connection.backup is used instead of copying witness.db directly so
    WAL-backed workspaces are cloned from a coherent committed database image.
    """

    workspace = Path(workspace_path).expanduser().resolve()
    canonical_fingerprint = corpus_fingerprint(canonical)
    snapshot_id = stable_id(
        "attack-snapshot",
        canonical_fingerprint,
        manifest_fingerprint,
    )
    root = workspace / ".witness" / "attacks" / attack_run_id
    root.mkdir(parents=True, exist_ok=False)
    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=False)
    database = root / "witness.db"

    destination = sqlite3.connect(database)
    try:
        canonical.connection.backup(destination)
        destination.commit()
    finally:
        destination.close()

    return AttackSnapshot(
        snapshot_id=snapshot_id,
        root=root,
        database=database,
        artifacts=artifacts,
        canonical_corpus_fingerprint=canonical_fingerprint,
    )
