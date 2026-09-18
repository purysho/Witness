"""SQLite persistence for RAG Lab datasets, runs, cases, and metrics."""

from __future__ import annotations

from datetime import datetime, timezone

from ..retrieval.index import LocalEvidenceIndex
from .models import (
    EvalCaseResult,
    EvalConfigSnapshot,
    EvalDataset,
    EvalDatasetSummary,
    EvalRunMetrics,
    EvalRunResult,
    EvalRunSummary,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EvalStore:
    def __init__(self, evidence_index: LocalEvidenceIndex) -> None:
        self.index = evidence_index
        self.connection = evidence_index.connection
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS eval_datasets (
                dataset_fingerprint TEXT PRIMARY KEY,
                dataset_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                schema_version INTEGER NOT NULL,
                dataset_json TEXT NOT NULL,
                registered_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_eval_datasets_id
                ON eval_datasets(dataset_id, registered_at DESC);

            CREATE TABLE IF NOT EXISTS eval_runs (
                run_id TEXT PRIMARY KEY,
                dataset_fingerprint TEXT NOT NULL,
                config_id TEXT NOT NULL,
                config_json TEXT NOT NULL,
                corpus_fingerprint TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                metrics_json TEXT,
                FOREIGN KEY (dataset_fingerprint)
                    REFERENCES eval_datasets(dataset_fingerprint)
            );

            CREATE INDEX IF NOT EXISTS idx_eval_runs_dataset
                ON eval_runs(dataset_fingerprint, started_at DESC);

            CREATE TABLE IF NOT EXISTS eval_case_results (
                run_id TEXT NOT NULL,
                case_id TEXT NOT NULL,
                query_run_id TEXT,
                passed INTEGER NOT NULL,
                metrics_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                PRIMARY KEY (run_id, case_id),
                FOREIGN KEY (run_id) REFERENCES eval_runs(run_id) ON DELETE CASCADE
            );
            """
        )

    def register_dataset(self, dataset: EvalDataset) -> EvalDatasetSummary:
        registered_at = _now()
        payload = dataset.canonical_json()
        with self.connection:
            self.connection.execute(
                """
                INSERT OR IGNORE INTO eval_datasets (
                    dataset_fingerprint, dataset_id, name, description,
                    schema_version, dataset_json, registered_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dataset.fingerprint,
                    dataset.dataset_id,
                    dataset.name,
                    dataset.description,
                    dataset.schema_version,
                    payload,
                    registered_at,
                ),
            )
        row = self.connection.execute(
            """
            SELECT dataset_fingerprint, dataset_id, name, description,
                   registered_at, dataset_json
            FROM eval_datasets WHERE dataset_fingerprint = ?
            """,
            (dataset.fingerprint,),
        ).fetchone()
        restored = EvalDataset.model_validate_json(row["dataset_json"])
        return EvalDatasetSummary(
            dataset_fingerprint=row["dataset_fingerprint"],
            dataset_id=row["dataset_id"],
            name=row["name"],
            description=row["description"],
            case_count=len(restored.cases),
            registered_at=row["registered_at"],
        )

    def load_dataset(self, fingerprint: str) -> EvalDataset:
        row = self.connection.execute(
            "SELECT dataset_json FROM eval_datasets WHERE dataset_fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown evaluation dataset: {fingerprint}")
        return EvalDataset.model_validate_json(row["dataset_json"])

    def list_datasets(self) -> tuple[EvalDatasetSummary, ...]:
        rows = self.connection.execute(
            """
            SELECT dataset_fingerprint, dataset_id, name, description,
                   registered_at, dataset_json
            FROM eval_datasets
            ORDER BY registered_at DESC, dataset_id
            """
        ).fetchall()
        return tuple(
            EvalDatasetSummary(
                dataset_fingerprint=row["dataset_fingerprint"],
                dataset_id=row["dataset_id"],
                name=row["name"],
                description=row["description"],
                case_count=len(
                    EvalDataset.model_validate_json(row["dataset_json"]).cases
                ),
                registered_at=row["registered_at"],
            )
            for row in rows
        )

    def start_run(
        self,
        run_id: str,
        dataset_fingerprint: str,
        config: EvalConfigSnapshot,
    ) -> str:
        started_at = _now()
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO eval_runs (
                    run_id, dataset_fingerprint, config_id, config_json,
                    corpus_fingerprint, status, started_at
                ) VALUES (?, ?, ?, ?, ?, 'running', ?)
                """,
                (
                    run_id,
                    dataset_fingerprint,
                    config.config_id,
                    config.model_dump_json(),
                    config.corpus_fingerprint,
                    started_at,
                ),
            )
        return started_at

    def save_case_result(self, run_id: str, result: EvalCaseResult) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT OR REPLACE INTO eval_case_results (
                    run_id, case_id, query_run_id, passed,
                    metrics_json, result_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    result.case_id,
                    result.query_run_id,
                    int(result.metrics.passed),
                    result.metrics.model_dump_json(),
                    result.model_dump_json(),
                ),
            )

    def complete_run(self, run_id: str, metrics: EvalRunMetrics) -> None:
        with self.connection:
            self.connection.execute(
                """
                UPDATE eval_runs
                SET status = 'completed', completed_at = ?, metrics_json = ?
                WHERE run_id = ?
                """,
                (_now(), metrics.model_dump_json(), run_id),
            )

    def _summary_from_row(self, row) -> EvalRunSummary:
        dataset = self.load_dataset(row["dataset_fingerprint"])
        return EvalRunSummary(
            run_id=row["run_id"],
            dataset_fingerprint=row["dataset_fingerprint"],
            dataset_id=dataset.dataset_id,
            dataset_name=dataset.name,
            config=EvalConfigSnapshot.model_validate_json(row["config_json"]),
            status=row["status"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            metrics=(
                EvalRunMetrics.model_validate_json(row["metrics_json"])
                if row["metrics_json"]
                else None
            ),
        )

    def list_runs(self, *, limit: int = 50) -> tuple[EvalRunSummary, ...]:
        rows = self.connection.execute(
            """
            SELECT * FROM eval_runs
            ORDER BY started_at DESC, run_id DESC
            LIMIT ?
            """,
            (max(1, min(limit, 500)),),
        ).fetchall()
        return tuple(self._summary_from_row(row) for row in rows)

    def load_run(
        self,
        run_id: str,
        *,
        include_cases: bool = True,
    ) -> EvalRunResult:
        row = self.connection.execute(
            "SELECT * FROM eval_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown evaluation run: {run_id}")
        case_results: tuple[EvalCaseResult, ...] = ()
        if include_cases:
            case_rows = self.connection.execute(
                """
                SELECT result_json FROM eval_case_results
                WHERE run_id = ?
                ORDER BY case_id
                """,
                (run_id,),
            ).fetchall()
            case_results = tuple(
                EvalCaseResult.model_validate_json(item["result_json"])
                for item in case_rows
            )
        return EvalRunResult(
            run=self._summary_from_row(row),
            cases=case_results,
        )

    def load_case(self, run_id: str, case_id: str) -> EvalCaseResult:
        row = self.connection.execute(
            """
            SELECT result_json FROM eval_case_results
            WHERE run_id = ? AND case_id = ?
            """,
            (run_id, case_id),
        ).fetchone()
        if row is None:
            raise KeyError(
                f"Unknown evaluation case result: {run_id}/{case_id}"
            )
        return EvalCaseResult.model_validate_json(row["result_json"])
