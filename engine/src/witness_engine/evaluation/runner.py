"""RAG Lab execution, A/B comparison, and export."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import sqlite3
from time import perf_counter
from typing import Sequence
from uuid import uuid4

from ..answering import (
    AskEngine,
    DeterministicExtractiveGenerationProvider,
    GenerationProvider,
)
from ..ids import stable_id
from ..multimodal import LocalVisualVectorIndex, VisualEmbeddingProvider
from ..retrieval import (
    DeterministicTokenReranker,
    EmbeddingProvider,
    LocalEvidenceIndex,
    LocalVectorIndex,
    RerankProvider,
    RouteDecision,
    RetrievalPlan,
    RoutedRetriever,
    TransparentRetrievalRouter,
)
from ..retrieval.models import RetrievalCandidate
from ..retrieval.query import analyze_query
from .metrics import aggregate_case_results, score_case
from .models import (
    EvalCaseMetrics,
    EvalCaseResult,
    EvalConfig,
    EvalDataset,
    EvalRunResult,
    RetrievalMode,
)
from .store import EvalStore


@dataclass(frozen=True)
class IdentityReranker:
    @property
    def provider_id(self) -> str:
        return "identity-reranker:v1"

    def score(
        self,
        query: str,
        candidates: Sequence[RetrievalCandidate],
    ) -> list[float]:
        return [1.0 / max(candidate.rank, 1) for candidate in candidates]


class FixedRetrievalRouter:
    """Reproducible lexical, dense, and hybrid Lab baselines."""

    def __init__(self, mode: RetrievalMode) -> None:
        if mode == RetrievalMode.ROUTED:
            raise ValueError("routed mode uses TransparentRetrievalRouter")
        self.mode = mode

    def plan(self, query: str) -> RetrievalPlan:
        features = analyze_query(query)
        enabled = {
            RetrievalMode.LEXICAL: {"lexical"},
            RetrievalMode.DENSE: {"dense"},
            RetrievalMode.HYBRID: {"lexical", "dense"},
        }[self.mode]
        routes = []
        for route in (
            "lexical",
            "dense",
            "temporal",
            "graph",
            "hierarchical",
            "visual",
        ):
            requested = route in enabled and bool(features.normalized_query)
            reason = (
                f"Lab fixed {self.mode.value} baseline"
                if requested
                else f"disabled by Lab {self.mode.value} baseline"
            )
            routes.append(
                RouteDecision(
                    route=route,
                    requested=requested,
                    executable=True,
                    reasons=(reason,),
                )
            )
        return RetrievalPlan(
            query=query,
            features=features,
            routes=tuple(routes),
        )


def load_dataset_file(path: str | Path) -> EvalDataset:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    return EvalDataset.model_validate_json(
        source.read_text(encoding="utf-8")
    )


def corpus_fingerprint(index: LocalEvidenceIndex) -> str:
    digest = sha256()
    rows = index.connection.execute(
        """
        SELECT chunk_id, source_version_id, block_id, locator
        FROM indexed_chunks ORDER BY chunk_id
        """
    ).fetchall()
    for row in rows:
        digest.update(
            "\x1f".join(
                (
                    row["chunk_id"],
                    row["source_version_id"],
                    row["block_id"],
                    row["locator"],
                )
            ).encode("utf-8")
        )
        digest.update(b"\x1e")

    try:
        visual_rows = index.connection.execute(
            """
            SELECT visual_evidence_id, source_version_id, modality,
                   locator, asset_sha256
            FROM visual_evidence
            ORDER BY visual_evidence_id
            """
        ).fetchall()
    except sqlite3.OperationalError:
        visual_rows = ()

    for row in visual_rows:
        digest.update(
            "\x1f".join(
                (
                    row["visual_evidence_id"],
                    row["source_version_id"],
                    row["modality"],
                    row["locator"],
                    row["asset_sha256"],
                )
            ).encode("utf-8")
        )
        digest.update(b"\x1e")
    return digest.hexdigest()


def _source_paths(index: LocalEvidenceIndex) -> dict[str, str]:
    try:
        rows = index.connection.execute(
            """
            SELECT source_version_id, source_path
            FROM source_version_metadata
            """
        ).fetchall()
    except Exception:
        return {}
    return {
        row["source_version_id"]: row["source_path"]
        for row in rows
    }


def _provider_cost(provider) -> float | None:
    value = getattr(provider, "cost_usd", None)
    return float(value) if isinstance(value, (int, float)) else None


class EvalRunner:
    """Execute persisted benchmarks over the same production Ask pipeline."""

    def __init__(
        self,
        lexical_index: LocalEvidenceIndex,
        vector_index: LocalVectorIndex,
        embedding_provider: EmbeddingProvider,
        *,
        reranker: RerankProvider | None = None,
        generator: GenerationProvider | None = None,
        store: EvalStore | None = None,
        visual_index: LocalVisualVectorIndex | None = None,
        visual_embedding_provider: VisualEmbeddingProvider | None = None,
    ) -> None:
        if (visual_index is None) != (visual_embedding_provider is None):
            raise ValueError(
                "visual_index and visual_embedding_provider must be supplied together"
            )
        self.lexical = lexical_index
        self.vectors = vector_index
        self.embedding_provider = embedding_provider
        self.visual_index = visual_index
        self.visual_embedding_provider = visual_embedding_provider
        self.default_reranker = (
            reranker or DeterministicTokenReranker()
        )
        self.generator = (
            generator or DeterministicExtractiveGenerationProvider()
        )
        self.store = store or EvalStore(lexical_index)

    def _router(self, mode: RetrievalMode):
        if mode == RetrievalMode.ROUTED:
            return TransparentRetrievalRouter(
                visual_available=(
                    self.visual_index is not None
                    and self.visual_embedding_provider is not None
                )
            )
        return FixedRetrievalRouter(mode)

    def run(
        self,
        dataset: EvalDataset,
        config: EvalConfig,
    ) -> EvalRunResult:
        dataset_summary = self.store.register_dataset(dataset)
        reranker: RerankProvider = (
            self.default_reranker
            if config.rerank
            else IdentityReranker()
        )
        snapshot = config.snapshot(
            embedding_provider_id=self.embedding_provider.provider_id,
            reranker_provider_id=reranker.provider_id,
            generator_provider_id=self.generator.provider_id,
            corpus_fingerprint=corpus_fingerprint(self.lexical),
            visual_embedding_provider_id=(
                self.visual_embedding_provider.provider_id
                if (
                    config.retrieval_mode == RetrievalMode.ROUTED
                    and self.visual_embedding_provider is not None
                )
                else None
            ),
        )
        run_id = stable_id(
            "eval-run",
            dataset.fingerprint,
            snapshot.config_id,
            uuid4().hex,
        )
        self.store.start_run(
            run_id,
            dataset_summary.dataset_fingerprint,
            snapshot,
        )
        source_paths = _source_paths(self.lexical)
        case_results: list[EvalCaseResult] = []

        for case in dataset.cases:
            started = perf_counter()
            providers = [
                self.embedding_provider,
                reranker,
                self.generator,
            ]
            if (
                config.retrieval_mode == RetrievalMode.ROUTED
                and self.visual_embedding_provider is not None
            ):
                providers.append(self.visual_embedding_provider)
            providers = tuple(providers)
            cost_before = [
                _provider_cost(provider)
                for provider in providers
            ]
            try:
                retriever = RoutedRetriever(
                    self.lexical,
                    self.vectors,
                    self.embedding_provider,
                    router=self._router(config.retrieval_mode),
                    reranker=reranker,
                    visual_index=(
                        self.visual_index
                        if config.retrieval_mode == RetrievalMode.ROUTED
                        else None
                    ),
                    visual_embedding_provider=(
                        self.visual_embedding_provider
                        if config.retrieval_mode == RetrievalMode.ROUTED
                        else None
                    ),
                )
                ask_result = AskEngine(
                    retriever,
                    generator=self.generator,
                ).ask(
                    case.question,
                    limit=config.top_k,
                    candidate_pool=max(
                        config.candidate_pool,
                        config.top_k,
                    ),
                    rerank_pool=max(
                        config.rerank_pool,
                        config.top_k,
                    ),
                    rrf_k=config.rrf_k,
                )
                latency_ms = (
                    perf_counter() - started
                ) * 1000.0
                cost_after = [
                    _provider_cost(provider)
                    for provider in providers
                ]
                cost_available = all(
                    before is not None and after is not None
                    for before, after in zip(
                        cost_before,
                        cost_after,
                    )
                )
                cost_usd = (
                    sum(
                        max(
                            0.0,
                            float(after) - float(before),
                        )
                        for before, after in zip(
                            cost_before,
                            cost_after,
                        )
                    )
                    if cost_available
                    else None
                )
                metrics = score_case(
                    case,
                    ask_result,
                    source_paths=source_paths,
                    latency_ms=latency_ms,
                    cost_usd=cost_usd,
                    cost_available=cost_available,
                    top_k=config.top_k,
                )
                result = EvalCaseResult(
                    case_id=case.case_id,
                    question=case.question,
                    query_run_id=ask_result.run_id,
                    answer_state=ask_result.answer.state,
                    metrics=metrics,
                    ask_result=ask_result.to_dict(),
                )
            except Exception as exc:
                latency_ms = (
                    perf_counter() - started
                ) * 1000.0
                result = EvalCaseResult(
                    case_id=case.case_id,
                    question=case.question,
                    metrics=EvalCaseMetrics(
                        latency_ms=latency_ms,
                        passed=False,
                        failure_reasons=(
                            f"evaluation error: {type(exc).__name__}",
                        ),
                    ),
                    error=f"{type(exc).__name__}: {exc}",
                )
            self.store.save_case_result(
                run_id,
                result,
            )
            case_results.append(result)

        aggregate = aggregate_case_results(case_results)
        self.store.complete_run(run_id, aggregate)
        return self.store.load_run(run_id)


def compare_runs(
    store: EvalStore,
    run_a: str,
    run_b: str,
) -> dict:
    left = store.load_run(run_a)
    right = store.load_run(run_b)
    if (
        left.run.dataset_fingerprint
        != right.run.dataset_fingerprint
    ):
        raise ValueError(
            "A/B comparison requires runs from the same dataset snapshot"
        )
    if left.run.metrics is None or right.run.metrics is None:
        raise ValueError(
            "A/B comparison requires completed runs"
        )

    metric_names = sorted(
        set(left.run.metrics.objective)
        | set(right.run.metrics.objective)
    )
    metrics = []
    for name in metric_names:
        a = left.run.metrics.objective.get(name)
        b = right.run.metrics.objective.get(name)
        metrics.append(
            {
                "metric": name,
                "a": a,
                "b": b,
                "delta": (
                    b - a
                    if a is not None and b is not None
                    else None
                ),
                "kind": "objective",
            }
        )

    left_cases = {
        item.case_id: item
        for item in left.cases
    }
    right_cases = {
        item.case_id: item
        for item in right.cases
    }
    case_rows = []
    for case_id in sorted(
        set(left_cases) | set(right_cases)
    ):
        a = left_cases.get(case_id)
        b = right_cases.get(case_id)
        row = {
            "case_id": case_id,
            "question": (
                a.question
                if a is not None
                else b.question
                if b is not None
                else ""
            ),
            "a_passed": (
                a.metrics.passed
                if a is not None
                else False
            ),
            "b_passed": (
                b.metrics.passed
                if b is not None
                else False
            ),
            "a_state": (
                a.answer_state.value
                if a is not None
                and a.answer_state is not None
                else None
            ),
            "b_state": (
                b.answer_state.value
                if b is not None
                and b.answer_state is not None
                else None
            ),
            "a_query_run_id": (
                a.query_run_id
                if a is not None
                else None
            ),
            "b_query_run_id": (
                b.query_run_id
                if b is not None
                else None
            ),
            "a_failures": (
                list(a.metrics.failure_reasons)
                if a is not None
                else ["missing case"]
            ),
            "b_failures": (
                list(b.metrics.failure_reasons)
                if b is not None
                else ["missing case"]
            ),
        }
        case_rows.append(row)

    return {
        "dataset_fingerprint": (
            left.run.dataset_fingerprint
        ),
        "dataset_id": left.run.dataset_id,
        "dataset_name": left.run.dataset_name,
        "run_a": left.run.model_dump(mode="json"),
        "run_b": right.run.model_dump(mode="json"),
        "metrics": metrics,
        "model_judged_metrics": [],
        "cases": case_rows,
        "failed_cases": [
            item
            for item in case_rows
            if not item["a_passed"]
            or not item["b_passed"]
        ],
    }


def export_run(
    store: EvalStore,
    run_id: str,
    output_path: str | Path,
    *,
    format: str,
) -> Path:
    result = store.load_run(run_id)
    target = Path(output_path).expanduser().resolve()
    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if format == "json":
        target.write_text(
            json.dumps(
                result.model_dump(mode="json"),
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return target

    if format == "csv":
        fieldnames = [
            "run_id",
            "case_id",
            "question",
            "query_run_id",
            "answer_state",
            "passed",
            "recall_at_k",
            "precision_at_k",
            "reciprocal_rank",
            "ndcg_at_k",
            "citation_precision",
            "citation_coverage",
            "unsupported_claim_rate",
            "abstention_correct",
            "contradiction_handling_correct",
            "state_correct",
            "latency_ms",
            "cost_usd",
            "failure_reasons",
        ]
        with target.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=fieldnames,
            )
            writer.writeheader()
            for item in result.cases:
                metric = item.metrics
                writer.writerow(
                    {
                        "run_id": run_id,
                        "case_id": item.case_id,
                        "question": item.question,
                        "query_run_id": (
                            item.query_run_id or ""
                        ),
                        "answer_state": (
                            item.answer_state.value
                            if item.answer_state
                            else ""
                        ),
                        "passed": metric.passed,
                        "recall_at_k": (
                            metric.recall_at_k
                        ),
                        "precision_at_k": (
                            metric.precision_at_k
                        ),
                        "reciprocal_rank": (
                            metric.reciprocal_rank
                        ),
                        "ndcg_at_k": metric.ndcg_at_k,
                        "citation_precision": (
                            metric.citation_precision
                        ),
                        "citation_coverage": (
                            metric.citation_coverage
                        ),
                        "unsupported_claim_rate": (
                            metric.unsupported_claim_rate
                        ),
                        "abstention_correct": (
                            metric.abstention_correct
                        ),
                        "contradiction_handling_correct": (
                            metric.contradiction_handling_correct
                        ),
                        "state_correct": (
                            metric.state_correct
                        ),
                        "latency_ms": metric.latency_ms,
                        "cost_usd": metric.cost_usd,
                        "failure_reasons": " | ".join(
                            metric.failure_reasons
                        ),
                    }
                )
        return target

    raise ValueError(
        "format must be json or csv"
    )
