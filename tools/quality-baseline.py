#!/usr/bin/env python
"""Run the fixed V1.1 quality regression dataset through Witness Lab baselines."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

from witness_engine.evaluation import (
    EvalConfig,
    EvalRunner,
    EvalStore,
    RetrievalMode,
    compare_runs,
    load_dataset_file,
)
from witness_engine.evaluation.runner import corpus_fingerprint
from witness_engine.pipeline import index_document
from witness_engine.rpc.service import RpcService


CONFIGS = (
    EvalConfig(
        name="v1.0.0 lexical baseline",
        retrieval_mode=RetrievalMode.LEXICAL,
        top_k=10,
        candidate_pool=30,
        rerank_pool=20,
        rrf_k=60,
        rerank=True,
        chunk_max_chars=1200,
    ),
    EvalConfig(
        name="v1.0.0 dense baseline",
        retrieval_mode=RetrievalMode.DENSE,
        top_k=10,
        candidate_pool=30,
        rerank_pool=20,
        rrf_k=60,
        rerank=True,
        chunk_max_chars=1200,
    ),
    EvalConfig(
        name="v1.0.0 hybrid baseline",
        retrieval_mode=RetrievalMode.HYBRID,
        top_k=10,
        candidate_pool=30,
        rerank_pool=20,
        rrf_k=60,
        rerank=True,
        chunk_max_chars=1200,
    ),
    EvalConfig(
        name="v1.0.0 routed baseline",
        retrieval_mode=RetrievalMode.ROUTED,
        top_k=10,
        candidate_pool=30,
        rerank_pool=20,
        rrf_k=60,
        rerank=True,
        chunk_max_chars=1200,
    ),
)


def _relation_counts(ask_result: dict | None) -> dict[str, int]:
    reconciliation = (ask_result or {}).get("reconciliation") or {}
    return {
        "duplicates": len(reconciliation.get("duplicates") or []),
        "corroborations": len(reconciliation.get("corroborations") or []),
        "conflicts": len(reconciliation.get("unresolved_conflicts") or []),
        "supersessions": len(reconciliation.get("supersessions") or []),
    }


def _route_summary(ask_result: dict | None) -> dict[str, object]:
    retrieval = (ask_result or {}).get("retrieval") or {}
    trace = retrieval.get("trace") or {}
    plan = trace.get("plan") or {}
    routes = plan.get("routes") or []
    return {
        "requested_routes": [
            item.get("route")
            for item in routes
            if item.get("requested")
        ],
        "executed_routes": [
            item.get("route")
            for item in routes
            if item.get("requested") and item.get("executable")
        ],
        "advisory_routes": trace.get("advisory_routes") or [],
    }


def _case_payload(case) -> dict[str, object]:
    metrics = case.metrics.model_dump(mode="json")
    return {
        "case_id": case.case_id,
        "question": case.question,
        "passed": case.metrics.passed,
        "answer_state": (
            case.answer_state.value if case.answer_state is not None else None
        ),
        "query_run_id": case.query_run_id,
        "failure_reasons": list(case.metrics.failure_reasons),
        "metrics": metrics,
        "relations": _relation_counts(case.ask_result),
        "routes": _route_summary(case.ask_result),
    }


def _index_quality_corpus(service: RpcService, repo_root: Path) -> dict[str, str]:
    assert service.lexical is not None
    assert service.vectors is not None

    corpus = repo_root / "fixtures" / "quality-v1.1"
    indexed: dict[str, str] = {}

    def add(
        filename: str,
        *,
        valid_from: str = "2026-01-01T00:00:00+00:00",
        identity_key: str | None = None,
    ) -> None:
        result = index_document(
            corpus / filename,
            service.lexical,
            vector_index=service.vectors,
            embedding_provider=service.embedding_provider,
            visual_index=service.visual_index,
            visual_embedding_provider=service.visual_embedding_provider,
            valid_from=valid_from,
            identity_key=identity_key,
        )
        indexed[filename] = result.source_version_id

    add(
        "api-handbook-2025.md",
        valid_from="2025-01-01T00:00:00+00:00",
        identity_key="quality://api-handbook",
    )
    add(
        "api-handbook-2026.md",
        valid_from="2026-01-01T00:00:00+00:00",
        identity_key="quality://api-handbook",
    )
    add("authentication.md")
    add("authentication-copy.md")
    add("feature-enabled.md")
    add("feature-disabled.md")
    add("services.md")
    add("recovery.md")
    return indexed


def run(output: Path, workspace: Path | None = None) -> dict[str, object]:
    repo_root = Path(__file__).resolve().parents[1]
    dataset_path = (
        repo_root / "fixtures" / "eval" / "v1-1-quality-regression.json"
    )
    dataset = load_dataset_file(dataset_path)

    temporary: tempfile.TemporaryDirectory[str] | None = None
    if workspace is None:
        temporary = tempfile.TemporaryDirectory(prefix="witness-quality-")
        workspace = Path(temporary.name) / "quality.witness"
    else:
        workspace = workspace.expanduser().resolve()
        if workspace.exists() and any(workspace.iterdir()):
            raise ValueError("quality baseline workspace must be empty")

    service = RpcService()
    try:
        service.handle("workspace.open", {"path": str(workspace)})
        source_versions = _index_quality_corpus(service, repo_root)
        assert service.lexical is not None
        assert service.vectors is not None

        store = EvalStore(service.lexical)
        runner = EvalRunner(
            service.lexical,
            service.vectors,
            service.embedding_provider,
            store=store,
            visual_index=(
                service.visual_index
                if service.visual_embedding_provider is not None
                else None
            ),
            visual_embedding_provider=service.visual_embedding_provider,
        )

        results = {}
        by_mode = {}
        for config in CONFIGS:
            result = runner.run(dataset, config)
            metrics = result.run.metrics
            assert metrics is not None
            payload = {
                "run_id": result.run.run_id,
                "config": result.run.config.model_dump(mode="json"),
                "metrics": metrics.model_dump(mode="json"),
                "cases": [_case_payload(case) for case in result.cases],
            }
            results[config.retrieval_mode.value] = payload
            by_mode[config.retrieval_mode] = result

        routed_id = by_mode[RetrievalMode.ROUTED].run.run_id
        comparisons = {}
        for mode in (
            RetrievalMode.LEXICAL,
            RetrievalMode.DENSE,
            RetrievalMode.HYBRID,
        ):
            comparisons[f"{mode.value}_to_routed"] = compare_runs(
                store,
                by_mode[mode].run.run_id,
                routed_id,
            )

        report: dict[str, object] = {
            "schema_version": 1,
            "dataset_id": dataset.dataset_id,
            "dataset_fingerprint": dataset.fingerprint,
            "corpus_fingerprint": corpus_fingerprint(service.lexical),
            "source_versions": source_versions,
            "baseline_config": "v1.0.0 routed baseline",
            "runs": results,
            "comparisons": comparisons,
        }

        output = output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return report
    finally:
        service.close()
        if temporary is not None:
            temporary.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Witness V1.1 fixed quality regression baselines."
    )
    parser.add_argument(
        "--output",
        default="quality-baseline.json",
        help="JSON report destination.",
    )
    parser.add_argument(
        "--workspace",
        help="Optional empty workspace directory to retain after the run.",
    )
    args = parser.parse_args()
    try:
        run(
            Path(args.output),
            Path(args.workspace) if args.workspace else None,
        )
    except Exception as exc:
        print(
            f"quality baseline failed: {type(exc).__name__}: {exc}",
            file=__import__("sys").stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
