"""Append-only query-run trace persistence."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from ..retrieval.index import LocalEvidenceIndex


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class TraceEvent:
    run_id: str
    sequence: int
    stage: str
    payload: dict
    created_at: str

    def to_dict(self) -> dict:
        return asdict(self)


class LocalRunStore:
    """Persist query runs and append-only structured trace events in SQLite."""

    def __init__(self, evidence_index: LocalEvidenceIndex) -> None:
        self.index = evidence_index
        self.connection = evidence_index.connection
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS query_runs (
                run_id TEXT PRIMARY KEY,
                question TEXT NOT NULL,
                status TEXT NOT NULL,
                sufficiency_state TEXT,
                answer_json TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS query_trace_events (
                run_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                stage TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (run_id, sequence),
                FOREIGN KEY (run_id) REFERENCES query_runs(run_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_query_trace_stage
                ON query_trace_events(run_id, stage);
            """
        )

    def start_run(self, run_id: str, question: str) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO query_runs (
                    run_id, question, status, started_at
                ) VALUES (?, ?, 'running', ?)
                """,
                (run_id, question, _now()),
            )

    def append(self, run_id: str, stage: str, payload: dict) -> TraceEvent:
        row = self.connection.execute(
            """
            SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence
            FROM query_trace_events WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        sequence = int(row["next_sequence"])
        created_at = _now()
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO query_trace_events (
                    run_id, sequence, stage, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, sequence, stage, payload_json, created_at),
            )
        return TraceEvent(
            run_id=run_id,
            sequence=sequence,
            stage=stage,
            payload=payload,
            created_at=created_at,
        )

    def complete(self, run_id: str, sufficiency_state: str, answer: dict) -> None:
        with self.connection:
            self.connection.execute(
                """
                UPDATE query_runs
                SET status = 'completed',
                    sufficiency_state = ?,
                    answer_json = ?,
                    completed_at = ?
                WHERE run_id = ?
                """,
                (
                    sufficiency_state,
                    json.dumps(answer, sort_keys=True, separators=(",", ":")),
                    _now(),
                    run_id,
                ),
            )

    def load_events(self, run_id: str) -> tuple[TraceEvent, ...]:
        rows = self.connection.execute(
            """
            SELECT run_id, sequence, stage, payload_json, created_at
            FROM query_trace_events
            WHERE run_id = ?
            ORDER BY sequence
            """,
            (run_id,),
        ).fetchall()
        return tuple(
            TraceEvent(
                run_id=row["run_id"],
                sequence=int(row["sequence"]),
                stage=row["stage"],
                payload=json.loads(row["payload_json"]),
                created_at=row["created_at"],
            )
            for row in rows
        )

    def load_answer(self, run_id: str) -> dict | None:
        row = self.connection.execute(
            "SELECT answer_json FROM query_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None or row["answer_json"] is None:
            return None
        return json.loads(row["answer_json"])
