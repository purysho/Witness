"""Allowlisted RPC service backed by one opened local Witness workspace."""

from __future__ import annotations
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ..answering import LocalRunStore
from ..graph.view import build_graph_snapshot
from ..pipeline import ask_evidence, index_document
from ..retrieval import DeterministicHashEmbeddingProvider, LocalEvidenceGraph, LocalEvidenceIndex, LocalHierarchyIndex, LocalTemporalIndex, LocalVectorIndex

ALLOWED_METHODS = frozenset({"ping","workspace.open","source.import","source.list","query.run","query.trace","graph.snapshot"})

class RpcServiceError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details

class RpcService:
    def __init__(self) -> None:
        self.workspace_path: Path | None = None
        self.lexical: LocalEvidenceIndex | None = None
        self.vectors: LocalVectorIndex | None = None
        self.embedding_provider = DeterministicHashEmbeddingProvider(dimensions=64)

    def close(self) -> None:
        if self.vectors is not None:
            self.vectors.close()
            self.vectors = None
        if self.lexical is not None:
            self.lexical.close()
            self.lexical = None
        self.workspace_path = None

    def _require_workspace(self) -> tuple[LocalEvidenceIndex, LocalVectorIndex]:
        if self.lexical is None or self.vectors is None or self.workspace_path is None:
            raise RpcServiceError("workspace_not_open", "Open a workspace before using this method.")
        return self.lexical, self.vectors

    def _open_workspace(self, params: dict[str, Any]) -> dict[str, Any]:
        raw_path = str(params.get("path", "")).strip()
        if not raw_path:
            raise RpcServiceError("invalid_params", "workspace.open requires a non-empty path")
        path = Path(raw_path).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        if not path.is_dir():
            raise RpcServiceError("invalid_workspace", "Workspace path is not a directory")
        self.close()
        database = path / "witness.db"
        self.workspace_path = path
        self.lexical = LocalEvidenceIndex(database)
        self.vectors = LocalVectorIndex(database)
        LocalHierarchyIndex(self.lexical)
        LocalTemporalIndex(self.lexical)
        LocalEvidenceGraph(self.lexical)
        LocalRunStore(self.lexical)
        return {
            "path": str(path), "database": str(database),
            "source_versions": len(self._source_rows()),
            "embedding_provider_id": self.embedding_provider.provider_id,
        }

    def _source_rows(self) -> list[dict[str, Any]]:
        lexical, _ = self._require_workspace()
        rows = lexical.connection.execute(
            """SELECT source_version_id, logical_source_id, source_path, title,
                      media_type, valid_from, valid_to,
                      supersedes_source_version_id, superseded_by_source_version_id
               FROM source_version_metadata
               ORDER BY valid_from DESC, source_version_id DESC"""
        ).fetchall()
        return [dict(row) for row in rows]

    def _import_source(self, params: dict[str, Any]) -> dict[str, Any]:
        lexical, vectors = self._require_workspace()
        raw_path = str(params.get("path", "")).strip()
        if not raw_path:
            raise RpcServiceError("invalid_params", "source.import requires a non-empty file path")
        source_path = Path(raw_path).expanduser().resolve()
        if not source_path.is_file():
            raise RpcServiceError("source_not_found", f"Source file does not exist: {source_path}")
        valid_from_raw = params.get("valid_from")
        valid_from: str | datetime | None = str(valid_from_raw).strip() if valid_from_raw else None
        return asdict(index_document(
            source_path, lexical, vector_index=vectors,
            embedding_provider=self.embedding_provider, valid_from=valid_from
        ))

    def _run_query(self, params: dict[str, Any]) -> dict[str, Any]:
        lexical, vectors = self._require_workspace()
        question = str(params.get("question", "")).strip()
        if not question:
            raise RpcServiceError("invalid_params", "query.run requires a non-empty question")
        limit = min(max(int(params.get("limit", 10)), 1), 50)
        return ask_evidence(
            question, lexical, vectors, self.embedding_provider, limit=limit,
            candidate_pool=max(30, limit), rerank_pool=max(20, limit)
        ).to_dict()

    def _query_trace(self, params: dict[str, Any]) -> dict[str, Any]:
        lexical, _ = self._require_workspace()
        run_id = str(params.get("run_id", "")).strip()
        if not run_id:
            raise RpcServiceError("invalid_params", "query.trace requires run_id")
        store = LocalRunStore(lexical)
        events, answer = store.load_events(run_id), store.load_answer(run_id)
        if not events and answer is None:
            raise RpcServiceError("run_not_found", f"Unknown query run: {run_id}")
        return {"run_id": run_id, "events": [item.to_dict() for item in events], "answer": answer}

    def handle(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method not in ALLOWED_METHODS:
            raise RpcServiceError("method_not_allowed", f"RPC method is not allowlisted: {method}")
        if method == "ping":
            return {"ok": True, "protocol_version": 1}
        if method == "workspace.open":
            return self._open_workspace(params)
        if method == "source.import":
            return self._import_source(params)
        if method == "source.list":
            return {"sources": self._source_rows()}
        if method == "query.run":
            return self._run_query(params)
        if method == "query.trace":
            return self._query_trace(params)
        if method == "graph.snapshot":
            lexical, _ = self._require_workspace()
            return build_graph_snapshot(lexical, limit=min(max(int(params.get("limit", 160)), 1), 400)).to_dict()
        raise AssertionError(method)
