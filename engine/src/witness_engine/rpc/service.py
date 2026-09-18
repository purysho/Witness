"""Allowlisted RPC service backed by one opened local Witness workspace."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..attack import AttackManifest, AttackRunner, AttackStore, export_attack_run
from ..answering import LocalRunStore
from ..evaluation import (
    EvalConfig,
    EvalRunner,
    EvalStore,
    compare_runs,
    export_run,
    load_dataset_file,
)
from ..graph.view import build_graph_snapshot
from ..pipeline import ask_evidence, index_document
from ..retrieval import (
    DeterministicHashEmbeddingProvider,
    LocalEvidenceGraph,
    LocalEvidenceIndex,
    LocalHierarchyIndex,
    LocalTemporalIndex,
    LocalVectorIndex,
)

ALLOWED_METHODS = frozenset(
    {
        "ping",
        "workspace.open",
        "source.import",
        "source.list",
        "query.run",
        "query.trace",
        "graph.snapshot",
        "lab.dataset.load",
        "lab.dataset.list",
        "lab.run",
        "lab.runs",
        "lab.run.get",
        "lab.case",
        "lab.compare",
        "lab.export",
        "attack.manifest.load",
        "attack.manifest.list",
        "attack.run",
        "attack.runs",
        "attack.run.get",
        "attack.export",
    }
)


class RpcServiceError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.details = details


class RpcService:
    def __init__(self) -> None:
        self.workspace_path: Path | None = None
        self.lexical: LocalEvidenceIndex | None = None
        self.vectors: LocalVectorIndex | None = None
        self.embedding_provider = DeterministicHashEmbeddingProvider(
            dimensions=64
        )

    def close(self) -> None:
        if self.vectors is not None:
            self.vectors.close()
            self.vectors = None
        if self.lexical is not None:
            self.lexical.close()
            self.lexical = None
        self.workspace_path = None

    def _require_workspace(
        self,
    ) -> tuple[LocalEvidenceIndex, LocalVectorIndex]:
        if (
            self.lexical is None
            or self.vectors is None
            or self.workspace_path is None
        ):
            raise RpcServiceError(
                "workspace_not_open",
                "Open a workspace before using this method.",
            )
        return self.lexical, self.vectors

    def _lab_store(self) -> EvalStore:
        lexical, _ = self._require_workspace()
        return EvalStore(lexical)

    def _attack_store(self) -> AttackStore:
        lexical, _ = self._require_workspace()
        return AttackStore(lexical)

    def _open_workspace(
        self,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        raw_path = str(params.get("path", "")).strip()
        if not raw_path:
            raise RpcServiceError(
                "invalid_params",
                "workspace.open requires a non-empty path",
            )
        path = Path(raw_path).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        if not path.is_dir():
            raise RpcServiceError(
                "invalid_workspace",
                "Workspace path is not a directory",
            )
        self.close()
        database = path / "witness.db"
        self.workspace_path = path
        self.lexical = LocalEvidenceIndex(database)
        self.vectors = LocalVectorIndex(database)
        LocalHierarchyIndex(self.lexical)
        LocalTemporalIndex(self.lexical)
        LocalEvidenceGraph(self.lexical)
        LocalRunStore(self.lexical)
        EvalStore(self.lexical)
        AttackStore(self.lexical)
        return {
            "path": str(path),
            "database": str(database),
            "source_versions": len(self._source_rows()),
            "embedding_provider_id": self.embedding_provider.provider_id,
        }

    def _source_rows(self) -> list[dict[str, Any]]:
        lexical, _ = self._require_workspace()
        rows = lexical.connection.execute(
            """
            SELECT
                source_version_id, logical_source_id, source_path, title,
                media_type, valid_from, valid_to,
                supersedes_source_version_id,
                superseded_by_source_version_id
            FROM source_version_metadata
            ORDER BY valid_from DESC, source_version_id DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def _import_source(
        self,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        lexical, vectors = self._require_workspace()
        raw_path = str(params.get("path", "")).strip()
        if not raw_path:
            raise RpcServiceError(
                "invalid_params",
                "source.import requires a non-empty file path",
            )
        source_path = Path(raw_path).expanduser().resolve()
        if not source_path.is_file():
            raise RpcServiceError(
                "source_not_found",
                f"Source file does not exist: {source_path}",
            )
        valid_from_raw = params.get("valid_from")
        valid_from: str | datetime | None = (
            str(valid_from_raw).strip()
            if valid_from_raw
            else None
        )
        return asdict(
            index_document(
                source_path,
                lexical,
                vector_index=vectors,
                embedding_provider=self.embedding_provider,
                valid_from=valid_from,
            )
        )

    def _run_query(
        self,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        lexical, vectors = self._require_workspace()
        question = str(params.get("question", "")).strip()
        if not question:
            raise RpcServiceError(
                "invalid_params",
                "query.run requires a non-empty question",
            )
        limit = min(
            max(int(params.get("limit", 10)), 1),
            50,
        )
        return ask_evidence(
            question,
            lexical,
            vectors,
            self.embedding_provider,
            limit=limit,
            candidate_pool=max(30, limit),
            rerank_pool=max(20, limit),
        ).to_dict()

    def _query_trace(
        self,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        lexical, _ = self._require_workspace()
        run_id = str(params.get("run_id", "")).strip()
        if not run_id:
            raise RpcServiceError(
                "invalid_params",
                "query.trace requires run_id",
            )
        store = LocalRunStore(lexical)
        events = store.load_events(run_id)
        answer = store.load_answer(run_id)
        if not events and answer is None:
            raise RpcServiceError(
                "run_not_found",
                f"Unknown query run: {run_id}",
            )
        return {
            "run_id": run_id,
            "events": [
                item.to_dict()
                for item in events
            ],
            "answer": answer,
        }

    @staticmethod
    def _compact_lab_run(result) -> dict[str, Any]:
        return {
            "run": result.run.model_dump(mode="json"),
            "cases": [
                {
                    **case.model_dump(
                        mode="json",
                        exclude={"ask_result"},
                    ),
                    "has_trace": bool(case.query_run_id),
                }
                for case in result.cases
            ],
        }

    def _lab_dataset_load(
        self,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        path = str(params.get("path", "")).strip()
        if not path:
            raise RpcServiceError(
                "invalid_params",
                "lab.dataset.load requires a dataset JSON path",
            )
        try:
            dataset = load_dataset_file(path)
        except (FileNotFoundError, ValidationError, ValueError) as exc:
            raise RpcServiceError(
                "invalid_dataset",
                str(exc),
            ) from exc
        return self._lab_store().register_dataset(
            dataset
        ).model_dump(mode="json")

    def _lab_run(
        self,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        lexical, vectors = self._require_workspace()
        fingerprint = str(
            params.get("dataset_fingerprint", "")
        ).strip()
        if not fingerprint:
            raise RpcServiceError(
                "invalid_params",
                "lab.run requires dataset_fingerprint",
            )
        try:
            store = EvalStore(lexical)
            dataset = store.load_dataset(fingerprint)
            config = EvalConfig.model_validate(
                params.get("config", {})
            )
            result = EvalRunner(
                lexical,
                vectors,
                self.embedding_provider,
                store=store,
            ).run(
                dataset,
                config,
            )
        except (KeyError, ValidationError, ValueError) as exc:
            raise RpcServiceError(
                "invalid_lab_run",
                str(exc),
            ) from exc
        return self._compact_lab_run(result)

    def _lab_export(
        self,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        self._require_workspace()
        assert self.workspace_path is not None
        run_id = str(params.get("run_id", "")).strip()
        format_value = str(
            params.get("format", "json")
        ).strip().casefold()
        if not run_id:
            raise RpcServiceError(
                "invalid_params",
                "lab.export requires run_id",
            )
        requested = str(
            params.get("path", "")
        ).strip()
        output = (
            Path(requested).expanduser().resolve()
            if requested
            else (
                self.workspace_path
                / "exports"
                / f"eval-{run_id[:12]}.{format_value}"
            )
        )
        try:
            path = export_run(
                self._lab_store(),
                run_id,
                output,
                format=format_value,
            )
        except (KeyError, ValueError) as exc:
            raise RpcServiceError(
                "lab_export_failed",
                str(exc),
            ) from exc
        return {
            "path": str(path),
            "format": format_value,
        }

    def _attack_manifest_load(
        self,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        raw_path = str(params.get("path", "")).strip()
        if not raw_path:
            raise RpcServiceError(
                "invalid_params",
                "attack.manifest.load requires a manifest JSON path",
            )
        path = Path(raw_path).expanduser().resolve()
        try:
            manifest = AttackManifest.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, ValueError) as exc:
            raise RpcServiceError(
                "invalid_attack_manifest",
                str(exc),
            ) from exc
        store = self._attack_store()
        store.register_manifest(manifest)
        return {
            "manifest_fingerprint": manifest.fingerprint,
            "attack_id": manifest.attack_id,
            "name": manifest.name,
            "description": manifest.description,
            "mutation_count": len(manifest.mutations),
        }

    def _attack_run(
        self,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        lexical, vectors = self._require_workspace()
        assert self.workspace_path is not None
        manifest_fingerprint = str(
            params.get("manifest_fingerprint", "")
        ).strip()
        dataset_fingerprint = str(
            params.get("dataset_fingerprint", "")
        ).strip()
        if not manifest_fingerprint or not dataset_fingerprint:
            raise RpcServiceError(
                "invalid_params",
                "attack.run requires manifest_fingerprint and dataset_fingerprint",
            )
        try:
            manifest = self._attack_store().load_manifest(
                manifest_fingerprint
            )
            dataset = self._lab_store().load_dataset(
                dataset_fingerprint
            )
            config = EvalConfig.model_validate(
                params.get("config", {})
            )
            result = AttackRunner(
                lexical,
                vectors,
                self.embedding_provider,
                workspace_path=self.workspace_path,
                store=self._attack_store(),
            ).run(manifest, dataset, config)
        except (KeyError, ValidationError, ValueError, OSError) as exc:
            raise RpcServiceError(
                "attack_run_failed",
                str(exc),
            ) from exc
        return result.model_dump(mode="json")

    def handle(
        self,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        if method not in ALLOWED_METHODS:
            raise RpcServiceError(
                "method_not_allowed",
                f"RPC method is not allowlisted: {method}",
            )

        if method == "ping":
            return {
                "ok": True,
                "protocol_version": 1,
            }
        if method == "workspace.open":
            return self._open_workspace(params)
        if method == "source.import":
            return self._import_source(params)
        if method == "source.list":
            return {
                "sources": self._source_rows(),
            }
        if method == "query.run":
            return self._run_query(params)
        if method == "query.trace":
            return self._query_trace(params)
        if method == "graph.snapshot":
            lexical, _ = self._require_workspace()
            return build_graph_snapshot(
                lexical,
                limit=min(
                    max(
                        int(
                            params.get(
                                "limit",
                                160,
                            )
                        ),
                        1,
                    ),
                    400,
                ),
            ).to_dict()
        if method == "lab.dataset.load":
            return self._lab_dataset_load(params)
        if method == "lab.dataset.list":
            return {
                "datasets": [
                    item.model_dump(mode="json")
                    for item in self._lab_store().list_datasets()
                ]
            }
        if method == "lab.run":
            return self._lab_run(params)
        if method == "lab.runs":
            limit = min(
                max(int(params.get("limit", 50)), 1),
                500,
            )
            return {
                "runs": [
                    item.model_dump(mode="json")
                    for item in self._lab_store().list_runs(
                        limit=limit
                    )
                ]
            }
        if method == "lab.run.get":
            run_id = str(
                params.get("run_id", "")
            ).strip()
            if not run_id:
                raise RpcServiceError(
                    "invalid_params",
                    "lab.run.get requires run_id",
                )
            try:
                result = self._lab_store().load_run(
                    run_id
                )
            except KeyError as exc:
                raise RpcServiceError(
                    "lab_run_not_found",
                    str(exc),
                ) from exc
            return self._compact_lab_run(result)
        if method == "lab.case":
            run_id = str(
                params.get("run_id", "")
            ).strip()
            case_id = str(
                params.get("case_id", "")
            ).strip()
            if not run_id or not case_id:
                raise RpcServiceError(
                    "invalid_params",
                    "lab.case requires run_id and case_id",
                )
            try:
                item = self._lab_store().load_case(
                    run_id,
                    case_id,
                )
            except KeyError as exc:
                raise RpcServiceError(
                    "lab_case_not_found",
                    str(exc),
                ) from exc
            return item.model_dump(mode="json")
        if method == "lab.compare":
            run_a = str(
                params.get("run_a", "")
            ).strip()
            run_b = str(
                params.get("run_b", "")
            ).strip()
            if not run_a or not run_b:
                raise RpcServiceError(
                    "invalid_params",
                    "lab.compare requires run_a and run_b",
                )
            try:
                return compare_runs(
                    self._lab_store(),
                    run_a,
                    run_b,
                )
            except (KeyError, ValueError) as exc:
                raise RpcServiceError(
                    "lab_compare_failed",
                    str(exc),
                ) from exc
        if method == "lab.export":
            return self._lab_export(params)
        if method == "attack.manifest.load":
            return self._attack_manifest_load(params)
        if method == "attack.manifest.list":
            return {
                "manifests": list(self._attack_store().list_manifests())
            }
        if method == "attack.run":
            return self._attack_run(params)
        if method == "attack.runs":
            limit = min(max(int(params.get("limit", 50)), 1), 500)
            return {
                "runs": list(self._attack_store().list_runs(limit=limit))
            }
        if method == "attack.run.get":
            run_id = str(params.get("attack_run_id", "")).strip()
            if not run_id:
                raise RpcServiceError(
                    "invalid_params",
                    "attack.run.get requires attack_run_id",
                )
            try:
                result = self._attack_store().load_run(run_id)
            except KeyError as exc:
                raise RpcServiceError(
                    "attack_run_not_found",
                    str(exc),
                ) from exc
            return result.model_dump(mode="json")
        if method == "attack.export":
            assert self.workspace_path is not None
            run_id = str(params.get("attack_run_id", "")).strip()
            format_value = str(params.get("format", "json")).strip().casefold()
            if not run_id:
                raise RpcServiceError(
                    "invalid_params",
                    "attack.export requires attack_run_id",
                )
            requested = str(params.get("path", "")).strip()
            output = (
                Path(requested).expanduser().resolve()
                if requested
                else (
                    self.workspace_path
                    / "exports"
                    / f"attack-{run_id[:12]}.{format_value}"
                )
            )
            try:
                path = export_attack_run(
                    self._attack_store(),
                    run_id,
                    output,
                    format=format_value,
                )
            except (KeyError, ValueError) as exc:
                raise RpcServiceError(
                    "attack_export_failed",
                    str(exc),
                ) from exc
            return {"path": str(path), "format": format_value}

        raise AssertionError(method)
