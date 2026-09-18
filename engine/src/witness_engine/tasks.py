"""Persistent long-running task state and cooperative cancellation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

from .retrieval.index import LocalEvidenceIndex


_JOB_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class OperationCancelled(RuntimeError):
    def __init__(self, job_id: str):
        super().__init__(f"Operation cancelled: {job_id}")
        self.job_id = job_id


@dataclass(frozen=True)
class TaskRecord:
    job_id: str
    kind: str
    status: str
    started_at: str
    completed_at: str | None
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TaskStore:
    """Crash-visible task history stored in the workspace database."""

    def __init__(self, index: LocalEvidenceIndex) -> None:
        self.connection = index.connection
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS task_runs (
                job_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                detail TEXT NOT NULL DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_task_runs_started
                ON task_runs(started_at DESC);
            """
        )

    def mark_interrupted(self) -> int:
        with self.connection:
            cursor = self.connection.execute(
                """
                UPDATE task_runs
                SET status = 'interrupted',
                    completed_at = ?,
                    detail = CASE
                        WHEN detail = '' THEN 'Engine stopped before task completion.'
                        ELSE detail
                    END
                WHERE status = 'running'
                """,
                (_now(),),
            )
        return int(cursor.rowcount)

    def start(self, job_id: str, kind: str) -> TaskRecord:
        validate_job_id(job_id)
        started_at = _now()
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO task_runs (
                    job_id, kind, status, started_at, detail
                ) VALUES (?, ?, 'running', ?, '')
                ON CONFLICT(job_id) DO UPDATE SET
                    kind=excluded.kind,
                    status='running',
                    started_at=excluded.started_at,
                    completed_at=NULL,
                    detail=''
                """,
                (job_id, kind, started_at),
            )
        return self.get(job_id)

    def finish(
        self,
        job_id: str,
        status: str,
        detail: str = "",
    ) -> TaskRecord:
        if status not in {
            "completed",
            "cancelled",
            "failed",
            "interrupted",
        }:
            raise ValueError(f"Unsupported task status: {status}")
        with self.connection:
            self.connection.execute(
                """
                UPDATE task_runs
                SET status = ?, completed_at = ?, detail = ?
                WHERE job_id = ?
                """,
                (status, _now(), detail, job_id),
            )
        return self.get(job_id)

    def get(self, job_id: str) -> TaskRecord:
        row = self.connection.execute(
            """
            SELECT job_id, kind, status, started_at, completed_at, detail
            FROM task_runs
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown task: {job_id}")
        return TaskRecord(
            job_id=row["job_id"],
            kind=row["kind"],
            status=row["status"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            detail=row["detail"],
        )

    def list(self, *, limit: int = 50) -> tuple[TaskRecord, ...]:
        rows = self.connection.execute(
            """
            SELECT job_id, kind, status, started_at, completed_at, detail
            FROM task_runs
            ORDER BY started_at DESC, job_id DESC
            LIMIT ?
            """,
            (max(1, min(limit, 500)),),
        ).fetchall()
        return tuple(
            TaskRecord(
                job_id=row["job_id"],
                kind=row["kind"],
                status=row["status"],
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                detail=row["detail"],
            )
            for row in rows
        )


def validate_job_id(job_id: str) -> str:
    normalized = str(job_id).strip()
    if not _JOB_ID_RE.fullmatch(normalized):
        raise ValueError(
            "job_id must be 1-128 characters using letters, numbers, '.', '_' or '-'"
        )
    return normalized


class CancellationProbe:
    """Poll a workspace-local flag that can be written outside engine RPC."""

    def __init__(self, workspace_path: str | Path, job_id: str) -> None:
        self.workspace_path = Path(workspace_path).expanduser().resolve()
        self.job_id = validate_job_id(job_id)
        self.cancel_dir = self.workspace_path / ".witness" / "cancel"
        self.flag_path = self.cancel_dir / f"{self.job_id}.cancel"

    def prepare(self) -> None:
        self.cancel_dir.mkdir(parents=True, exist_ok=True)
        self.flag_path.unlink(missing_ok=True)

    def check(self) -> None:
        if self.flag_path.exists():
            raise OperationCancelled(self.job_id)

    def close(self) -> None:
        self.flag_path.unlink(missing_ok=True)
